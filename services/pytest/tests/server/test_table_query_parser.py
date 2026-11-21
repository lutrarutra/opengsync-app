"""The search box of the htmx tables splits its text into terms (server/components/tables/query.py).

Terms are AND-ed; ``field:value`` targets one field, but only a field the table knows (``10:30`` or
``http://x`` stay text); quotes keep spaces in one term; ``#123`` and bare numbers are ids. The state of a
table is parsed leniently: unknown sort/filter keys, bad pages and limits are dropped or clamped, never 400.
"""
import pytest

from ..conftest import _ensure_backend_on_path

_ensure_backend_on_path()

from server.components.tables import query, state as table_state  # noqa: E402
from server.routes.htmx.libraries import LibraryTable  # noqa: E402
from starlette.datastructures import QueryParams  # noqa: E402

FIELDS = ["id", "name", "owner", "group", "status"]


def terms(q: str) -> list[tuple[str | None, str]]:
    return [(t.field, t.text) for t in query.parse_terms(q, FIELDS)]


def test_bare_terms_and_quotes():
    assert terms("pbmc  d04") == [(None, "pbmc"), (None, "d04")]
    assert terms('"liver organoid" d1') == [(None, "liver organoid"), (None, "d1")]
    assert terms('"unclosed quote') == [(None, "unclosed quote")]
    assert terms("   ") == []


def test_field_prefixes_only_for_known_fields():
    assert terms("owner:chen") == [("owner", "chen")]
    assert terms('group:"Immuno Lab" x') == [("group", "Immuno Lab"), (None, "x")]
    assert terms("OWNER:chen") == [("owner", "chen")]
    assert terms("color:red") == [(None, "color:red")]
    assert terms("10:30") == [(None, "10:30")]
    assert terms("http://example.org") == [(None, "http://example.org")]
    assert terms("owner:") == [(None, "owner:")]


def test_ids():
    assert terms("#1291") == [(None, "#1291")]
    assert query._ID.match("#1291").group(1) == "1291"
    assert query._ID.match("1291").group(1) == "1291"
    assert query._ID.match("12a") is None
    # more digits than fit an integer id are text
    assert query._ID.match("1234567890") is None


def test_enum_terms_match_labels_by_prefix():
    status = LibraryTable.col("status").filter
    assert [m.name for m in status.find("pool")] == ["POOLED"]
    assert [m.name for m in status.find("qc pend")] == ["QC_PENDING"]
    assert status.find("nonsense") == []


@pytest.mark.parametrize("params, expected", [  # type: ignore[attr-defined]
    ({"order_by": "name:asc"}, ("name", "asc")),
    ({"order_by": "name:sideways"}, None),
    ({"order_by": "no_such_column:asc"}, None),
    ({"order_by": "index:asc"}, None),  # not sortable
    ({"order_by": "garbage"}, None),
])
def test_state_order_by_is_validated(params, expected):
    assert table_state.parse(LibraryTable, QueryParams(params)).order_by == expected


def test_state_page_limit_and_filters_are_lenient():
    state = table_state.parse(LibraryTable, QueryParams(
        "page=-3&limit=100000&status_in=5,6&status_in=[7]&type_in=&no_such_in=1&scope=nope&q=" + "x" * 400
    ))
    assert state.page == 1
    assert state.limit == table_state.PAGE_LIMIT_MAX
    assert state.filters == {"status": ["5", "6", "7"]}
    assert state.scope is None
    assert len(state.q) == table_state.MAX_QUERY_LENGTH

    assert table_state.parse(LibraryTable, QueryParams("page=abc&limit=0")).page == 1
    assert table_state.parse(LibraryTable, QueryParams("limit=0")).limit == table_state.PAGE_LIMIT_MIN
    assert table_state.parse(LibraryTable, QueryParams("browse=x&limit=50")).limit == table_state.PAGE_LIMIT_DEFAULT


def test_state_options_only_for_entity_filters():
    assert table_state.parse(LibraryTable, QueryParams("options=owner&word=chen")).options == "owner"
    assert table_state.parse(LibraryTable, QueryParams("options=status")).options is None
    assert table_state.parse(LibraryTable, QueryParams("options=nope")).options is None


def test_split_values():
    assert table_state.split_values(["1,4", "[5, null]", " 7 ", "", "1"]) == ["1", "4", "5", "null", "7"]
    assert table_state.split_values(["[broken"]) == ["[broken"]
