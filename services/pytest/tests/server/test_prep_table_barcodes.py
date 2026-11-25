"""Barcode cells of the lab prep table: one row per library, ';' between index combinations."""

import pytest

from server.utils import prep_table


def _rows(**cells):
    parsed = prep_table.parse_barcodes(cells)
    assert parsed.errors == []
    return parsed.rows()


def _errors(**cells) -> list[str]:
    return [error.message for error in prep_table.parse_barcodes(cells).errors]


def _row(**values):
    return {col: values.get(col) for col in prep_table.BARCODE_COLUMNS}


def test_empty_cells_have_no_combinations():
    assert _rows() == []


def test_one_combination_per_value_and_kit_applies_to_all():
    assert _rows(index_well="a01; B1;", kit_i7="#TT") == [
        _row(index_well="A1", kit_i7="TT"),
        _row(index_well="B1", kit_i7="TT"),
    ]


def test_one_name_applies_to_every_sequence():
    """E.g. the four sequences of a 10x single-index set."""
    assert _rows(name_i7="SI-GA-A1", sequence_i7="aaaa;CCCC;GGGG;TTTT") == [
        _row(name_i7="SI-GA-A1", sequence_i7=seq) for seq in ["AAAA", "CCCC", "GGGG", "TTTT"]
    ]


def test_manual_dual_sequences():
    assert _rows(sequence_i7="AAAA;CCCC", sequence_i5="GGGG;TTTT") == [
        _row(sequence_i7="AAAA", sequence_i5="GGGG"),
        _row(sequence_i7="CCCC", sequence_i5="TTTT"),
    ]


def test_numeric_values_read_as_floats_are_whole_numbers():
    assert _rows(index_well=12.0, kit_i7=7.0) == [_row(index_well="12", kit_i7="7")]


def test_tube_number_wells_are_accepted():
    assert _rows(index_well="1;24", kit_i7="E7335") == [
        _row(index_well="1", kit_i7="E7335"), _row(index_well="24", kit_i7="E7335"),
    ]


def test_regional_decimal_kit_identifier_is_not_a_separator():
    assert len(_rows(index_well="A1", kit_i7="1,5")) == 1


def test_well_alone_is_no_barcode_yet():
    """The template fills a well in every row; the barcode is given later in the barcode step."""
    assert prep_table.parse_barcodes({"index_well": "A1"}).errors == []


@pytest.mark.parametrize("cell", ["A1 B1", "A1,B1", "A1, B1", "A1|B1", "A1/B1", "A1\nB1"])
def test_other_separators_ask_for_semicolons(cell):
    errors = _errors(index_well=cell, kit_i7="TT")
    assert len(errors) == 1
    assert "semicolons ';'" in errors[0]


def test_comma_separated_sequences_are_not_glued_together():
    errors = _errors(sequence_i7="AAAA,CCCC")
    assert len(errors) == 1 and "semicolons ';'" in errors[0]


def test_empty_value_between_semicolons():
    assert _errors(index_well="A1;;B1", kit_i7="TT") == ["'index_well' has an empty value between ';'."]


def test_mismatched_counts():
    errors = _errors(index_well="A1;B1", kit_i7="TT", name_i7="X;Y;Z")
    assert len(errors) == 1
    assert "different numbers" in errors[0]


def test_single_well_does_not_apply_to_several_names():
    assert any("different numbers" in e for e in _errors(index_well="A1", kit_i7="TT", name_i7="X;Y"))


def test_single_sequence_does_not_apply_to_several_wells():
    assert any("different numbers" in e for e in _errors(index_well="A1;B1", sequence_i7="AAAA"))


def test_invalid_well():
    assert _errors(index_well="Z99", kit_i7="TT") == ["Invalid index well 'Z99', must be a plate well like A1 or a tube number."]


def test_invalid_sequence():
    errors = _errors(sequence_i7="ACGX")
    assert len(errors) == 1 and "Invalid sequence 'ACGX'" in errors[0]


def test_too_long_name():
    assert _errors(name_i7="X" * 17, sequence_i7="ACGT") == ["Name '" + "X" * 17 + "' in 'name_i7' is too long."]


def test_kit_without_well_or_name():
    assert _errors(kit_i7="TT") == ["'index_well' or 'name_i7' must be given with 'kit_i7'."]


def test_name_without_kit_or_sequence():
    assert _errors(name_i7="N701") == ["'name_i7' needs 'kit_i7' or 'sequence_i7'."]


def test_i5_without_i7():
    assert len(_errors(sequence_i5="ACGT")) == 1


def test_names_are_not_checked_against_the_kit():
    assert _errors(kit_i7="NO-SUCH-KIT", name_i7="NO-SUCH-NAME") == []
