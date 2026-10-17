"""Spreadsheet columns: texts pasted or uploaded into object columns are resolved to their option.

A DBObjectColumn accepts a plain name for the "name [id]" / "name [new]" option it names, if it names exactly one.
A QueryColumn with ``resolve`` replaces the texts it recognizes by their ids, the other texts stay (and are rejected).
"""

from server.components.tables.spreadsheet import DBObjectColumn, QueryColumn


def _samples() -> DBObjectColumn:
    column = DBObjectColumn(("sample_id", "sample_name"), "Sample", 100, categories={})
    column.set_categories({1: "Liver [1]", 2: "Twin [2]", 3: "Twin [3]"}, new_names=["Brain"])
    return column


def test_object_column_resolves_unique_plain_names():
    column = _samples()

    assert column.resolve_name("Liver") == "Liver [1]"
    assert column.resolve_name(" Brain ") == "Brain [new]"


def test_object_column_keeps_options_ambiguous_and_unknown_names():
    column = _samples()

    assert column.resolve_name("Liver [1]") == "Liver [1]"
    assert column.resolve_name("Twin") == "Twin"  # two samples of that name
    assert column.resolve_name("Kidney") == "Kidney"
    assert column.resolve_name(None) is None


def test_query_column_resolves_recognized_texts():
    column = QueryColumn(
        "kit_id", "Kit", 100, url=None, lookup=lambda ids: {},
        resolve=lambda texts: {text: 7 for text in texts if text == "KIT-A"},
    )

    assert column.resolve_texts([5, " KIT-A ", "KIT-B", None, ""]) == [5, 7, "KIT-B", None, ""]


def test_query_column_without_resolve_keeps_texts():
    column = QueryColumn("kit_id", "Kit", 100, url=None, lookup=lambda ids: {})

    assert column.resolve_texts([5, "KIT-A"]) == [5, "KIT-A"]


def test_object_column_offers_names_with_option_ids():
    """The editor shows the names and adds the id only where names are shared (disambiguate)."""
    column = _samples()

    assert column.source == [
        {"id": "Liver [1]", "name": "Liver"},
        {"id": "Twin [2]", "name": "Twin"},
        {"id": "Twin [3]", "name": "Twin"},
        {"id": "Brain [new]", "name": "Brain"},
    ]
    constructed = DBObjectColumn(("sample_id", "sample_name"), "Sample", 100, categories={4: "Lung [4]"})
    assert constructed.source == [{"id": "Lung [4]", "name": "Lung"}]
