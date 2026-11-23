"""Base class of the htmx tables (see docs/tables.md).

A route builds the base statement (context filters, permission checks), picks a variant and renders:

    @router.get("/render-table-page")
    def render_library_table(seq_request_id: int | None = None, state: TableState = Depends(LibraryTable.params), ...):
        stmt = Q.library.select(seq_request_id=seq_request_id)
        table = LibraryTable(state, route="render_library_table", user=current_user)
        table.use("seq_request", seq_request_id=seq_request_id, seq_request=seq_request)
        return table.render(session, stmt)

``render`` applies the filters, the search box and the sort, pages the rows and renders
components/tables/_table.html, which includes the variant's row template. With ``?options=<field>`` it answers
with the options of that entity filter instead.
"""
import math
import re
from typing import Any, ClassVar, Sequence

import sqlalchemy as sa
from fastapi import Request, Response
from starlette.datastructures import URL

from opengsync_db import SyncSession, queries as Q

from ...core import responses
from ...core.context import ctx
from . import query as table_query
from .spec import Col, Enum, Entity, Variant, through
from .state import TableState, parse
from .visibility import visible, offered

OPTIONS_PAGE_SIZE = 20
PAGE_WINDOW = 7


class Table:
    key: ClassVar[str] = ""
    model: ClassVar[type]
    noun: ClassVar[str] = "rows"                      # plural, for counts and empty states
    columns: ClassVar[list[Col]] = []
    variants: ClassVar[dict[str, Variant]] = {}
    default_sort: ClassVar[tuple[str, str]] = ("id", "desc")
    tie_break: ClassVar[Sequence[Any]] = ()            # orders equal rows; defaults to model.id desc
    load: ClassVar[Sequence[Any]] = ()                 # loader options for the rows
    template: ClassVar[str] = "components/tables/_table.html"
    model_backed: ClassVar[bool] = True                # False: rows don't come from `model` (render is overridden)

    @classmethod
    def params(cls, request: Request) -> TableState:
        """FastAPI dependency: ``state: TableState = Depends(MyTable.params)``."""
        return parse(cls, request.query_params)

    @classmethod
    def col(cls, key: str) -> Col:
        for col in cls.columns:
            if col.key == key:
                return col
        raise KeyError(f"{cls.__name__} has no field '{key}'")

    def __init__(self, state: TableState, *, route: str, user: Any, variant: str = "default"):
        self.state = state
        self.route = route
        self.user = user
        self.variant_name = variant
        self.url_params: dict[str, Any] = {}
        self.context: dict[str, Any] = {}
        self.dom_id_override: str | None = None
        # a second copy of the same table on one page (?instance=<name>) gets its own address bar key and id
        instance = ctx.request.query_params.get("instance") if getattr(ctx, "request", None) is not None else None
        if instance and re.fullmatch(r"[a-z0-9_]{1,20}", instance):
            self.url_params["instance"] = instance
            self.key = f"{self.key}_{instance}"
            self.instance: str | None = instance
        else:
            self.instance = None
        # filled by render()
        self.rows: Sequence[Any] = []
        self.fuzzy = False                             # rows came from the typo-tolerant search
        self.total = 0
        self.unfiltered_total: int | None = None
        self.page = 1
        self.num_pages = 1
        self._filter_values: dict[str, list[Any]] = {}

    # -- configuration -------------------------------------------------------------------------------------------

    def use(self, variant: str, /, **params: Any) -> "Table":
        """Pick a variant; keyword arguments that are not ``None`` and are plain values become context
        query parameters of the table's url (kept on every request), the rest template context."""
        if variant not in self.variants:
            raise KeyError(f"{type(self).__name__} has no variant '{variant}'")
        self.variant_name = variant
        for name, value in params.items():
            if value is None:
                continue
            if isinstance(value, (int, str, bool, float)):
                self.url_params[name] = value
            else:
                self.context[name] = value
        return self

    @property
    def variant(self) -> Variant:
        return self.variants[self.variant_name]

    @property
    def dom_id(self) -> str:
        dom_id = self.dom_id_override or self.variant.dom_id or f"{type(self).key}-table"
        return f"{dom_id}-{self.instance}" if self.instance else dom_id

    @property
    def shown_columns(self) -> list[Col]:
        return [self.col(key) for key in self.variant.columns]

    @property
    def fields(self) -> list[Col]:
        """The fields offered in the search box and the filter panel of this variant."""
        if self.variant.fields is not None:
            return [self.col(key) for key in self.variant.fields]
        return list(self.columns)

    @property
    def search_fields(self) -> list[Col]:
        return [c for c in self.fields if c.searchable]

    @property
    def filter_fields(self) -> list[Col]:
        # entity filters on insider-only objects (experiments, lab preps, ...) are hidden from customers
        return [
            c for c in self.fields
            if c.filterable and (not isinstance(c.filter, Entity) or offered(c.filter.model, self.user))
        ]

    # -- rendering -----------------------------------------------------------------------------------------------

    def render(self, session: SyncSession, stmt: sa.Select, *, load: Sequence[Any] | None = None) -> Response:
        filter_clauses = self._resolve_filters(session, stmt)
        if self.state.options is not None:
            return self._options_response(session, stmt)

        offered = self.fields
        scope = self.state.scope if any(c.key == self.state.scope for c in offered) else None
        search_clauses, score = table_query.search(self.state.q, offered, self.model, scope)
        filtered = stmt.where(*filter_clauses, *search_clauses)
        self.total = session.count(filtered)
        self.fuzzy = False

        if self.total == 0 and self.state.q:
            # nothing matches literally: try again with typo tolerance
            session.execute(Q.search.threshold_statement())
            fuzzy_clauses, fuzzy_score = table_query.search(self.state.q, offered, self.model, scope, fuzzy=True)
            fuzzy_filtered = stmt.where(*filter_clauses, *fuzzy_clauses)
            if (fuzzy_total := session.count(fuzzy_filtered)) > 0:
                filtered, score, self.total, self.fuzzy = fuzzy_filtered, fuzzy_score, fuzzy_total, True

        self.num_pages = max(1, math.ceil(self.total / self.state.limit))
        self.page = min(self.state.page, self.num_pages)

        ordered = filtered.order_by(*self._ordering(score)).offset((self.page - 1) * self.state.limit).limit(self.state.limit)
        loaders = list(load if load is not None else self.load)
        if loaders:
            ordered = ordered.options(*loaders)
        self.rows = session.execute(ordered).scalars().all()

        if self.total == 0 and self.state.has_query:
            self.unfiltered_total = session.count(stmt)

        return responses.htmx_response(template=self.template, table=self, rows=self.rows, **self.context)

    def _ordering(self, score: sa.ColumnElement[float] | None) -> list[Any]:
        ties = list(self.tie_break) or [self.model.id.desc()]
        if self.state.order_by is None and score is not None:
            return [score.desc(), *ties]
        key, direction = self.state.order_by or self.default_sort
        expr = self.sort_expression(self.col(key))
        return [sa.nulls_last(expr.desc() if direction == "desc" else expr.asc()), *ties]

    def sort_expression(self, col: Col) -> Any:
        return getattr(self.model, col.key) if col.sort is True else col.sort

    # -- filters -------------------------------------------------------------------------------------------------

    def _related_ids(self, entity: Entity, stmt: sa.Select) -> sa.Select:
        """Ids of the related objects that occur in the rows of the base statement (viewer-scoped by the route)."""
        ids = sa.select(entity.model.id).select_from(self.model)
        for rel in entity.via:
            ids = ids.join(rel)
        return ids.where(self.model.id.in_(stmt.with_only_columns(self.model.id).order_by(None)))

    def _visible(self, entity: Entity, stmt: sa.Select) -> sa.ColumnElement[bool] | None:
        if entity.from_rows:
            return entity.model.id.in_(self._related_ids(entity, stmt))
        return visible(entity.model, self.user)

    def _resolve_filters(self, session: SyncSession, stmt: sa.Select) -> list[sa.ColumnElement[bool]]:
        """Validate the ``<key>_in`` values and turn them into WHERE clauses; invalid or invisible values are
        dropped (and so never shown as chips)."""
        clauses: list[sa.ColumnElement[bool]] = []
        offered = {c.key for c in self.filter_fields}
        for key, raw_values in self.state.filters.items():
            if key not in offered:
                continue
            col = self.col(key)
            if isinstance(col.filter, Enum):
                members = []
                for raw in raw_values:
                    try:
                        member = col.filter.get(raw)
                    except (KeyError, ValueError):
                        continue
                    if member not in members:
                        members.append(member)
                if not members:
                    continue
                column = col.filter.column if col.filter.column is not None else getattr(self.model, col.key)
                present = [m for m in members if m is not None]
                parts = []
                if present:
                    parts.append(column.in_(present))
                if None in members:
                    parts.append(column.is_(None))
                clauses.append(through(col.filter.via, sa.or_(*parts)))
                self._filter_values[key] = members
            elif isinstance(col.filter, Entity):
                ids = [int(raw) for raw in raw_values if raw.isdigit() and len(raw) <= 9]
                if not ids:
                    continue
                model = col.filter.model
                lookup = sa.select(model).where(model.id.in_(ids))
                if (vis := self._visible(col.filter, stmt)) is not None:
                    lookup = lookup.where(vis)
                objects = session.execute(lookup).scalars().all()
                if not objects:
                    continue
                objects = sorted(objects, key=lambda o: ids.index(o.id))
                clauses.append(through(col.filter.via, model.id.in_([o.id for o in objects])))
                self._filter_values[key] = list(objects)
        return clauses

    def _options_response(self, session: SyncSession, stmt: sa.Select) -> Response:
        col = self.col(self.state.options)  # type: ignore[arg-type]
        if col not in self.filter_fields:
            return responses.query_options_response([], has_more=False)
        entity = col.filter
        assert isinstance(entity, Entity)
        model = entity.model

        options = sa.select(model).where(model.id.in_(self._related_ids(entity, stmt)))
        if not entity.from_rows and (vis := visible(model, self.user)) is not None:
            options = options.where(vis)

        order: list[Any] = []
        if self.state.word and entity.search and (sq := Q.search.SearchQuery.parse(self.state.word)) is not None:
            session.execute(Q.search.threshold_statement())
            matches = [Q.search.match(c, sq) for c in entity.search]
            options = options.where(sa.or_(*(m[0] for m in matches)))
            order.append((matches[0][1] if len(matches) == 1 else sa.func.greatest(*(m[1] for m in matches))).desc())
        if entity.search:
            order.append(entity.search[0].asc())
        order.append(model.id.desc())

        page = self.state.options_page
        total = session.count(options)
        statement = options.order_by(*order).offset((page - 1) * OPTIONS_PAGE_SIZE).limit(OPTIONS_PAGE_SIZE)
        if entity.load is not None:
            statement = statement.options(entity.load)
        objects = session.execute(statement).scalars().all()
        return responses.query_options_response(
            (entity.option(o) for o in objects), has_more=page * OPTIONS_PAGE_SIZE < total,
        )

    # -- template helpers ----------------------------------------------------------------------------------------

    @property
    def url(self) -> URL:
        """The route with the context parameters, without the state (the form adds it)."""
        return ctx.request.url_for(self.route).include_query_params(**self.url_params)

    def options_url(self, col: Col) -> str:
        return str(self.url.include_query_params(options=col.key))

    def is_selected(self, col: Col, value: Any) -> bool:
        values = self._filter_values.get(col.key, [])
        if isinstance(col.filter, Entity):
            return any(o.id == value for o in values)
        return value in values

    def selected(self, col: Col) -> list[Any]:
        return self._filter_values.get(col.key, [])

    @staticmethod
    def value_id(value: Any) -> str:
        if value is None:
            return "null"
        return str(value.id)

    def value_label(self, col: Col, value: Any) -> str:
        if value is None:
            return "Not set"
        if isinstance(col.filter, Entity):
            return col.filter.option(value)["name"]
        # status enums' display_name already ends in the icon: with an icon, use the bare label
        if icon := getattr(value, "icon", None):
            return f"{icon} {value.label}"
        return getattr(value, "display_name", None) or value.label

    @property
    def chips(self) -> list[dict[str, Any]]:
        chips = []
        for col in self.filter_fields:
            if values := self._filter_values.get(col.key):
                chips.append({
                    "key": col.key, "title": col.title,
                    "labels": [self.value_label(col, v) for v in values],
                })
        return chips

    @property
    def has_filters(self) -> bool:
        return bool(self._filter_values)

    @property
    def has_query(self) -> bool:
        return bool(self.state.q) or self.has_filters

    def sort_direction(self, col: Col) -> str | None:
        """Direction the column is sorted in, by an explicit or the default sort."""
        if self.state.order_by is not None:
            key, direction = self.state.order_by
            return direction if key == col.key else None
        if self.state.q:
            return None  # relevance
        key, direction = self.default_sort
        return direction if key == col.key else None

    def next_sort(self, col: Col) -> str:
        """``order_by`` value a click on the column header sets: asc -> desc -> off (default)."""
        explicit = self.state.order_by[1] if self.state.order_by and self.state.order_by[0] == col.key else None
        if explicit is None:
            return f"{col.key}:asc"
        if explicit == "asc":
            return f"{col.key}:desc"
        return ""

    # -- column widths: from the spec, never from the rows, so they don't jump between pages -------------------

    ACTIONS_WIDTH_PX: ClassVar[int] = 48
    MIN_PX_PER_SIZE: ClassVar[int] = 48

    def header_min_px(self, col: Col) -> int:
        """Room the header needs (title, sort arrow, funnel, barcode switch), from the spec, not the rows.
        Measured on table.css: 20px cell padding, ~7.6px per title character (13px semibold) or 16px for an icon, the sort button
        adds 18px (padding, gap, arrow), the funnel 18px, the barcode switch 92px."""
        width = 30 + (16 if col.icon else round(len(col.title) * 7.6))  # 26px measured + 4px margin
        if col.sortable:
            width += 18
        if col.filterable and col in self.filter_fields:
            width += 18
        if col.index_toggle:
            width += 92
        return width

    def col_weight(self, col: Col) -> float:
        """The column's ``size`` (default 1), raised so its header fits at the table's minimum width."""
        size = self.variant.sizes.get(col.key, col.size)
        return max(float(size or 1), self.header_min_px(col) / self.MIN_PX_PER_SIZE)

    def col_width(self, col: Col) -> str:
        """Share of the table width: weights of the shown columns, the same on every page."""
        total = sum(self.col_weight(c) for c in self.shown_columns)
        return f"{100 * self.col_weight(col) / total:.3f}%"

    @property
    def min_width(self) -> int:
        """Below this the table scrolls sideways instead of squeezing columns (narrow screens); at this width
        every header fits, and wider tables keep the proportions."""
        width = round(sum(self.col_weight(c) for c in self.shown_columns) * self.MIN_PX_PER_SIZE)
        return width + (self.ACTIONS_WIDTH_PX if self.variant.actions else 0)

    @property
    def count_label(self) -> str:
        """``1 library``, ``12 libraries``."""
        if self.total != 1:
            return f"{self.total} {self.noun}"
        noun = self.noun
        singular = noun[:-3] + "y" if noun.endswith("ies") else noun[:-1] if noun.endswith("s") else noun
        return f"1 {singular}"

    @property
    def first_row(self) -> int:
        return 0 if self.total == 0 else (self.page - 1) * self.state.limit + 1

    @property
    def last_row(self) -> int:
        return min(self.page * self.state.limit, self.total)

    def page_numbers(self) -> list[int | None]:
        """Pages to link, ``None`` for a gap: 1 … 4 5 [6] 7 8 … 20."""
        n, p = self.num_pages, self.page
        if n <= PAGE_WINDOW + 2:
            return list(range(1, n + 1))
        start = max(2, min(p - PAGE_WINDOW // 2, n - PAGE_WINDOW))
        end = min(n - 1, start + PAGE_WINDOW - 1)
        pages: list[int | None] = [1]
        if start > 2:
            pages.append(None)
        pages.extend(range(start, end + 1))
        if end < n - 1:
            pages.append(None)
        pages.append(n)
        return pages

    @property
    def url_state(self) -> dict[str, str]:
        """The non-default state, as the address bar carries it (without the table prefix)."""
        state: dict[str, str] = {}
        if self.state.q:
            state["q"] = self.state.q
        if self.state.scope:
            state["scope"] = self.state.scope
        if self.state.order_by is not None:
            state["order_by"] = ":".join(self.state.order_by)
        for key, values in self._filter_values.items():
            state[f"{key}_in"] = ",".join(self.value_id(v) for v in values)
        if self.page > 1:
            state["page"] = str(self.page)
        return state

    @property
    def state_params(self) -> dict[str, str]:
        """Context parameters plus the non-default state: the request that renders this exact table."""
        return {**{k: str(v) for k, v in self.url_params.items()}, **self.url_state}
