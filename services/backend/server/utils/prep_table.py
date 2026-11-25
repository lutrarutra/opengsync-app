"""Barcode cells of the lab prep table (``prep_table`` sheet).

The prep table has one row per library. A library with several index combinations
holds one value per combination in each barcode cell, separated by ``;``
(e.g. ``index_well = "A1;B1"``, ``name_i7 = "N701;N702"``).

A kit or name column with a single value applies to every combination, e.g. one kit for
all wells, or one name for the four sequences of a 10x set. Wells and sequences
identify one combination each, so they are given once per combination.
"""

import re
from dataclasses import dataclass, field

import pandas as pd

from opengsync_db import models

from . import barcodes

SEPARATOR = ";"

BARCODE_COLUMNS = ["index_well", "kit_i7", "name_i7", "sequence_i7", "kit_i5", "name_i5", "sequence_i5"]

# Columns whose single value applies to every combination of the library
BROADCAST_COLUMNS = {"kit_i7", "kit_i5", "name_i7", "name_i5"}

# Wells of 96- and 384-well plates, optionally zero-padded (A1, A01, P24), or the tube number
# some kits (e.g. NEB E7335) use as well
WELL_PATTERN = re.compile(r"^([A-P]0*([1-9]|1[0-9]|2[0-4])|[1-9][0-9]{0,2})$")


def _clean_number_text(value: str) -> str:
    """Excel reads whole numbers as floats when the column has blanks: '12.0' -> '12'."""
    return re.sub(r"^(\d+)\.0$", r"\1", value)


def clean_kit_identifier(value: str) -> str | None:
    """Same as legacy ``CommonBarcodeInputForm.kit_identifier_clean_up``."""
    value = _clean_number_text(value.strip().removeprefix("#").strip())
    if not value:
        return None
    try:
        float(value)
        value = value.replace(",", ".")  # regional Excel may use a comma as decimal separator
    except ValueError:
        pass
    return value


def clean_well(value: str) -> str | None:
    """Upper-cased and without zero padding, as the barcode step matches kit wells: 'a01' -> 'A1'."""
    value = value.strip().upper()
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", value) or None


def clean_name(value: str) -> str | None:
    return _clean_number_text(value.strip()) or None


CLEANERS = {
    "index_well": clean_well,
    "kit_i7": clean_kit_identifier,
    "kit_i5": clean_kit_identifier,
    "name_i7": clean_name,
    "name_i5": clean_name,
    "sequence_i7": barcodes.clean_sequence,
    "sequence_i5": barcodes.clean_sequence,
}


@dataclass
class CellError:
    columns: list[str]
    message: str


@dataclass
class ParsedBarcodes:
    """The barcode cells of one prep table row, split into one value per combination."""
    values: dict[str, list[str | None]]
    num_combinations: int
    errors: list[CellError] = field(default_factory=list)

    def rows(self) -> list[dict[str, str | None]]:
        """One dict per combination; a column with a single value applies to every combination."""
        rows = []
        for i in range(self.num_combinations):
            row: dict[str, str | None] = {}
            for col, parts in self.values.items():
                if len(parts) == 1:
                    row[col] = parts[0]
                else:
                    row[col] = parts[i] if i < len(parts) else None
            if any(v is not None for v in row.values()):
                rows.append(row)
        return rows


def joined_names(library: models.Library, read: str) -> str:
    """The ``name_<read>`` cell for a library's stored indices, matching ``sequences_<read>_str(';')``.

    One name when all indices share it (e.g. the four sequences of a 10x set), else one per
    index. Empty when an index has no name, as a blank part would not be readable.
    """
    names = [
        getattr(index, f"name_{read}") for index in library.indices
        if getattr(index, f"sequence_{read}")
    ]
    if not names or any(not name for name in names):
        return ""
    if len(set(names)) == 1:
        return names[0]
    return SEPARATOR.join(names)


OTHER_SEPARATORS = re.compile(r"[\s,|/]")


def _has_other_separator(col: str, part: str) -> bool:
    """Whether a value looks like several values joined by something other than ';'."""
    if col.startswith("kit_"):
        part = part.removeprefix("#").strip()
        if re.fullmatch(r"\d+,\d+", part):
            return False  # a numeric kit identifier with a regional decimal comma, e.g. '1,5'
    return OTHER_SEPARATORS.search(part) is not None


def _split(value) -> list[str] | None:
    """The ';'-separated parts of a cell, a trailing ';' ignored. None for an empty cell."""
    if value is None or pd.isna(value):
        return None
    text = _clean_number_text(str(value).strip())
    if not text:
        return None
    parts = [part.strip() for part in text.split(SEPARATOR)]
    if len(parts) > 1 and parts[-1] == "":
        parts = parts[:-1]
    return parts


def parse_barcodes(row: pd.Series | dict) -> ParsedBarcodes:
    """Split and clean the barcode cells of a prep table row and check that they can be read.

    Only the format is checked: whether a kit, well or name exists is checked in the barcode step.
    """
    errors: list[CellError] = []
    values: dict[str, list[str | None]] = {}

    for col in BARCODE_COLUMNS:
        parts = _split(row.get(col))
        if parts is None:
            values[col] = []
            continue
        if any(part == "" for part in parts):
            errors.append(CellError([col], f"'{col}' has an empty value between '{SEPARATOR}'."))
        if other := [part for part in parts if _has_other_separator(col, part)]:
            errors.append(CellError(
                [col], f"'{col}' value '{other[0]}' contains a space or other separator. "
                f"Separate several values with semicolons '{SEPARATOR}', e.g. 'A1{SEPARATOR}B1'.",
            ))
            values[col] = []
            continue
        cleaned = [CLEANERS[col](part) if part else None for part in parts]
        values[col] = cleaned

        for raw, value in zip(parts, cleaned):
            if value is None:
                continue
            if col == "index_well" and not WELL_PATTERN.match(value):
                errors.append(CellError([col], f"Invalid index well '{raw}', must be a plate well like A1 or a tube number."))
            elif col.startswith("sequence_"):
                if (error := barcodes.check_sequence(value)) is not None:
                    errors.append(CellError([col], f"Invalid sequence '{raw}' in '{col}': {error}"))
                elif len(value) > getattr(models.LibraryIndex, col).type.length:
                    errors.append(CellError([col], f"Sequence '{raw}' in '{col}' is too long."))
            elif col.startswith("name_") and len(value) > getattr(models.LibraryIndex, col).type.length:
                errors.append(CellError([col], f"Name '{raw}' in '{col}' is too long."))

    counts = {col: len(parts) for col, parts in values.items() if parts}
    num_combinations = max(counts.values(), default=0)
    if num_combinations > 1:
        mismatched = [
            col for col, n in counts.items()
            if n != num_combinations and not (n == 1 and col in BROADCAST_COLUMNS)
        ]
        if mismatched:
            counted = ", ".join(f"'{col}': {n}" for col, n in counts.items())
            errors.append(CellError(
                list(counts.keys()),
                f"Barcode cells have different numbers of '{SEPARATOR}'-separated values ({counted}). "
                f"Give one value per index combination (a kit or name can be given once for all).",
            ))

    parsed = ParsedBarcodes(values=values, num_combinations=num_combinations, errors=errors)
    if not errors:
        parsed.errors.extend(_check_combinations(parsed.rows()))
    return parsed


def _check_combinations(rows: list[dict[str, str | None]]) -> list[CellError]:
    """Each combination must say how its i7 is found: a kit with a well or name, or a sequence."""
    for row in rows:
        has_i7 = row["sequence_i7"] is not None or row["kit_i7"] is not None or row["name_i7"] is not None
        if row["kit_i7"] is not None and row["index_well"] is None and row["name_i7"] is None:
            return [CellError(["kit_i7", "index_well", "name_i7"], "'index_well' or 'name_i7' must be given with 'kit_i7'.")]
        if row["name_i7"] is not None and row["kit_i7"] is None and row["sequence_i7"] is None:
            return [CellError(["name_i7", "kit_i7", "sequence_i7"], "'name_i7' needs 'kit_i7' or 'sequence_i7'.")]
        if not has_i7 and any(row[col] is not None for col in ("kit_i5", "name_i5", "sequence_i5")):
            return [CellError(["kit_i7", "name_i7", "sequence_i7"], "i5 is given without an i7 ('kit_i7' with 'index_well'/'name_i7', or 'sequence_i7').")]
    return []
