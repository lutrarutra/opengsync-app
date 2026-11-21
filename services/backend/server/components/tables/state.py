"""The state of a table, parsed from the request's query parameters.

Parameters (the address bar carries them with a per-table prefix, e.g. ``lib.q``, see static/js/table.js):

    q          free-text search, see query.py for the syntax
    scope      restrict bare search terms to one field
    order_by   ``<key>:asc|desc``
    page       1-based page number
    limit      rows per page (clamped; not mirrored in the address bar)
    <key>_in   filter values, comma separated (``1,4``), repeated or as a JSON list (``[1, 4]``)
    options    with ``word`` and ``options_page``: answer with the options of the entity filter ``<options>``

Unknown or invalid values are dropped instead of answered with an error, so old or hand-edited links still open.
"""
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.datastructures import QueryParams

if TYPE_CHECKING:
    from .table import Table

PAGE_LIMIT_DEFAULT = 10
PAGE_LIMIT_MIN = 1
PAGE_LIMIT_MAX = 100
MAX_QUERY_LENGTH = 256


@dataclass
class TableState:
    q: str = ""
    scope: str | None = None
    order_by: tuple[str, str] | None = None
    page: int = 1
    limit: int = PAGE_LIMIT_DEFAULT
    filters: dict[str, list[str]] = field(default_factory=dict)
    options: str | None = None
    word: str | None = None
    options_page: int = 1

    @property
    def has_query(self) -> bool:
        return bool(self.q) or any(self.filters.values())


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def split_values(raw_values: list[str]) -> list[str]:
    """``["1,4", "[5, null]", "7"]`` -> ``["1", "4", "5", "null", "7"]``."""
    values: list[str] = []
    for raw in raw_values:
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("["):
            try:
                values.extend("null" if v is None else str(v) for v in json.loads(raw))
                continue
            except (ValueError, TypeError):
                pass
        values.extend(v.strip() for v in raw.split(",") if v.strip())
    return list(dict.fromkeys(values))


def parse(table: "type[Table]", params: QueryParams) -> TableState:
    fields = {col.key: col for col in table.columns}
    state = TableState()

    state.q = " ".join((params.get("q") or "").split())[:MAX_QUERY_LENGTH]

    scope = params.get("scope")
    if scope in fields and fields[scope].searchable:
        state.scope = scope

    if (order_by := params.get("order_by")) and ":" in order_by:
        key, _, direction = order_by.partition(":")
        if key in fields and fields[key].sortable and direction in ("asc", "desc"):
            state.order_by = (key, direction)

    state.page = max(1, _int(params.get("page"), 1))

    if params.get("browse") is not None:
        state.limit = PAGE_LIMIT_DEFAULT
    else:
        state.limit = min(PAGE_LIMIT_MAX, max(PAGE_LIMIT_MIN, _int(params.get("limit"), PAGE_LIMIT_DEFAULT)))

    for key, col in fields.items():
        if col.filter is None:
            continue
        if values := split_values(params.getlist(f"{key}_in")):
            state.filters[key] = values

    if (options := params.get("options")) in fields and fields[options].entity:
        state.options = options
        state.word = (params.get("word") or "").strip()[:MAX_QUERY_LENGTH] or None
        state.options_page = max(1, _int(params.get("options_page"), 1))

    return state
