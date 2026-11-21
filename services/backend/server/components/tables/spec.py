"""Declarative building blocks of an htmx table (see docs/tables.md).

A table is a subclass of ``Table`` (table.py) listing its fields:

    Col("name", "Name", sort=True, search=Text(models.Library.name))            # shown column
    Col("owner", "Owner", display=False, search=Text(full_name(User), via=...))  # search/filter-only field

``via`` is a path of relationship attributes from the table's model to the model the columns belong to,
e.g. ``(models.Library.seq_request, models.SeqRequest.group)``. Conditions through a path are compiled to
correlated EXISTS (``rel.has``/``rel.any``), so a one-to-many path never duplicates rows or breaks the count.
"""
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import InstrumentedAttribute

Path = tuple[InstrumentedAttribute, ...]


def as_path(via: InstrumentedAttribute | Sequence[InstrumentedAttribute] | None) -> Path:
    if via is None:
        return ()
    if isinstance(via, (list, tuple)):
        return tuple(via)
    return (via,)


def through(path: Path, clause: sa.ColumnElement[bool]) -> sa.ColumnElement[bool]:
    """``clause`` on the model at the end of ``path``, as a condition on the model at its start."""
    for rel in reversed(path):
        clause = rel.any(clause) if rel.property.uselist else rel.has(clause)
    return clause


def target_model(path: Path, default: type) -> type:
    return path[-1].property.mapper.class_ if path else default


def related(rel: InstrumentedAttribute, column: Any) -> sa.ScalarSelect:
    """``column`` of the object a many-to-one relationship points to, as a correlated scalar subquery
    (to sort by a joined column, e.g. the pool name of a library)."""
    pairs = rel.property.local_remote_pairs
    clauses = [remote == local for local, remote in pairs]
    return sa.select(column).where(*clauses).correlate(rel.class_).scalar_subquery()


# ---------------------------------------------------------------------------------------------------------------
# Search kinds
# ---------------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Text:
    """Free-text search in one or more text columns, ranked like the navbar search
    (exact > prefix > substring > fuzzy, see opengsync_db.queries.search)."""
    columns: tuple[Any, ...]
    via: Path = ()
    compact: bool = False
    weight: float = 1.0

    def __init__(self, *columns: Any, via=None, compact: bool = False, weight: float = 1.0):
        self.columns = columns
        self.via = as_path(via)
        self.compact = compact
        self.weight = weight


@dataclass(eq=False)
class Exact:
    """Integer equality, for ids: matches a bare number, ``#123`` or a number after one of ``prefixes``
    (case-insensitive, separators allowed: ``P123``, ``BSR_0012``)."""
    column: Any
    prefixes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------------------------------------------
# Filter kinds
# ---------------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Enum:
    """Filter by values of a DB enum column (checkbox list of all choices)."""
    enum: Any
    column: Any = None
    via: Path = ()
    choices: list | None = None     # members to offer, ``None`` (not set) allowed; defaults to all members
    nullable: bool = False          # offer "Not set"

    def __init__(self, enum: Any, column: Any = None, via=None, choices: list | None = None, nullable: bool = False):
        self.enum = enum
        self.column = column
        self.via = as_path(via)
        self.choices = choices
        self.nullable = nullable

    def options(self) -> list:
        members = list(self.choices) if self.choices is not None else list(self.enum.as_list())
        if self.nullable and None not in members:
            members = [None] + members
        return members

    def get(self, raw: str) -> Any:
        """The member for a raw id from the URL; ``KeyError`` if it is not one of the options."""
        if raw in ("null", "none", ""):
            if None in self.options():
                return None
            raise KeyError(raw)
        member = self.enum.get(int(raw))
        if member not in self.options():
            raise KeyError(raw)
        return member

    def find(self, text: str) -> list:
        """Members whose label or name starts with ``text`` (for ``status:pooled`` in the search box)."""
        text = text.lower().replace("_", " ")
        return [
            m for m in self.options() if m is not None
            and (m.label.lower().startswith(text) or m.name.lower().replace("_", " ").startswith(text))
        ]


@dataclass(eq=False)
class Entity:
    """Filter by chosen related objects (e.g. the owners of libraries), picked in a type-ahead list.

    Options are the objects that occur in the rows the viewer can see, restricted again by
    ``visibility.visible``, and ids from the URL are validated the same way."""
    model: type
    via: Path
    option: Callable[[Any], dict]
    search: tuple[Any, ...] = ()
    load: Any = None
    from_rows: bool = False

    def __init__(
        self, model: type, via, option: Callable[[Any], dict], search: Sequence[Any] = (), load: Any = None,
        from_rows: bool = False,
    ):
        """``from_rows``: the objects may be seen exactly when they occur in a row the viewer can see (e.g. the
        staff assigned to a customer's requests, whom the model's own rule would hide); options and ids from the
        URL are then restricted to the base rows instead of ``visibility.visible``."""
        self.model = model
        self.via = as_path(via)
        self.option = option
        self.search = tuple(search)
        self.load = load
        self.from_rows = from_rows


# ---------------------------------------------------------------------------------------------------------------
# Columns and variants
# ---------------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Col:
    key: str
    title: str
    sort: Any = None                   # None: not sortable; True: getattr(model, key); else a SQL expression
    search: Text | Exact | None = None
    filter: Enum | Entity | None = None
    display: bool = True               # False: search/filter-only field, never a column
    hideable: bool = True              # can be hidden with the column picker
    size: int | None = None            # bootstrap col-N width hint
    index_toggle: bool = False         # header gets the barcode Name | Sequence switch
    align: str | None = None

    @property
    def sortable(self) -> bool:
        return self.sort is not None

    @property
    def searchable(self) -> bool:
        return self.search is not None

    @property
    def filterable(self) -> bool:
        return self.filter is not None

    @property
    def entity(self) -> bool:
        return isinstance(self.filter, Entity)


def Field(key: str, title: str, **kwargs) -> Col:
    """A search/filter-only field (not a column)."""
    return Col(key, title, display=False, hideable=False, **kwargs)


@dataclass(eq=False)
class Variant:
    """One way to show the table, usually per page context (e.g. libraries of a request)."""
    columns: Sequence[str]
    row_template: str
    dom_id: str | None = None          # container id, defaults to "<key>-table"
    actions: bool = False              # last column holds the row's ⋯ menu
    url_state: bool = True             # mirror the state in the address bar (off for browse tables in forms)
    fields: Sequence[str] | None = None  # search/filter fields offered, defaults to all
    prelude: str | None = None         # template rendered above the table (e.g. capacity bars)
    toolbar: str | None = None         # template with buttons at the end of the toolbar (e.g. "Add Assignee")
    extra: dict = dc_field(default_factory=dict)
