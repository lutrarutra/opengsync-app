"""index_badge_class: one color rule for index badges, for LibraryIndex objects and barcode table rows."""

import numpy as np
import pandas as pd
import pytest

from opengsync_db import models, categories as C

from server.utils.barcodes import index_badge_class

KIT, VALIDATED, NOT_VALIDATED, NOT_SPECIFIED = "badge-success", "badge-primary", "badge-warning", "badge-danger"


def _index(**kwargs) -> models.LibraryIndex:
    defaults = dict(name_i7=None, name_i5=None, sequence_i7="ACGTACGT", sequence_i5=None, index_kit_i7_id=None, index_kit_i5_id=None, orientation=None)
    return models.LibraryIndex(**{**defaults, **kwargs})


@pytest.mark.parametrize("index, expected", [
    (_index(index_kit_i7_id=1, name_i7="A1", orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED), KIT),
    (_index(index_kit_i7_id=1, name_i7="A1", sequence_i5="TTTT", index_kit_i5_id=1, name_i5="A1"), KIT),
    # Kit i7 with a custom i5 is not a kit index
    (_index(index_kit_i7_id=1, name_i7="A1", sequence_i5="TTTT", orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED), NOT_VALIDATED),
    # A kit id without a name is not a kit index
    (_index(index_kit_i7_id=1, orientation=C.BarcodeOrientation.FORWARD), VALIDATED),
    (_index(orientation=C.BarcodeOrientation.FORWARD), VALIDATED),
    (_index(orientation=C.BarcodeOrientation.FORWARD_NOT_VALIDATED), NOT_VALIDATED),
    (_index(orientation=C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED), NOT_VALIDATED),
    (_index(orientation=None), NOT_SPECIFIED),
])
def test_library_index(index: models.LibraryIndex, expected: str):
    assert index_badge_class(index) == expected


@pytest.mark.parametrize("row, expected", [
    # Query tables: orientation enum, missing values as NaN / pd.NA
    ({"kit_i7_id": 1.0, "name_i7": "A1", "sequence_i5": np.nan, "orientation": C.BarcodeOrientation.FORWARD}, KIT),
    ({"kit_i7_id": np.nan, "name_i7": pd.NA, "sequence_i5": pd.NA, "orientation": C.BarcodeOrientation.FORWARD}, VALIDATED),
    ({"kit_i7_id": np.nan, "name_i7": None, "sequence_i5": None, "orientation": None}, NOT_SPECIFIED),
    # Workflow tables: orientation id (int, float or numpy)
    ({"kit_i7_id": None, "name_i7": None, "orientation_id": C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id}, NOT_VALIDATED),
    ({"kit_i7_id": None, "name_i7": None, "orientation_id": float(C.BarcodeOrientation.FORWARD.id)}, VALIDATED),
    ({"kit_i7_id": None, "name_i7": None, "orientation_id": np.int64(C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED.id)}, NOT_VALIDATED),
    ({"kit_i7_id": None, "name_i7": None, "orientation_id": np.nan}, NOT_SPECIFIED),
    # 10x ATAC kit barcode: single i7 from a kit, whatever the library index type
    ({"kit_i7_id": 7, "name_i7": "SI-NA-A1", "sequence_i5": None, "index_type_id": C.IndexType.TENX_ATAC_INDEX.id, "orientation_id": C.BarcodeOrientation.FORWARD.id}, KIT),
    # No orientation column at all
    ({"kit_i7_id": None, "name_i7": None, "sequence_i7": "ACGT"}, NOT_SPECIFIED),
])
def test_table_row(row: dict, expected: str):
    assert index_badge_class(pd.Series(row)) == expected
