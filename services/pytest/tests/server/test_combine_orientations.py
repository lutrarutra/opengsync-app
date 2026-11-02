"""combine_orientations: one library index orientation from independently matched i7 and i5 orientations."""

import numpy as np
import pandas as pd
import pytest

from opengsync_db import categories as C

from server.utils.barcodes import combine_orientations, combined_orientation_ids

I5 = "ACGTACGT"
O = C.BarcodeOrientation
F, RC, F_NV, RC_NV = O.FORWARD, O.REVERSE_COMPLEMENT, O.FORWARD_NOT_VALIDATED, O.REVERSE_COMPLEMENT_NOT_VALIDATED


@pytest.mark.parametrize("i7, i5, expected", [
    (None, None, None),
    # one index unknown (e.g. kit i7, "I don't know" i5): not validated until checked manually
    (F, None, F_NV),
    (None, F, F_NV),
    (RC, None, RC_NV),
    (F_NV, None, F_NV),
    (F, F, F),
    (F_NV, F_NV, F_NV),
    # i7 from a kit, i5 custom (or the other way round): not validated
    (F, F_NV, F_NV),
    (F_NV, F, F_NV),
    (RC, RC_NV, RC_NV),
])
def test_combine(i7, i5, expected):
    assert combine_orientations(i7.id if i7 else None, i5.id if i5 else None, I5) == expected


@pytest.mark.parametrize("sequence_i5", [None, np.nan, pd.NA])
def test_without_i5_the_i7_orientation_is_used(sequence_i5):
    assert combine_orientations(F.id, None, sequence_i5) == F
    assert combine_orientations(None, None, sequence_i5) is None


@pytest.mark.parametrize("i7, i5", [(F, RC), (F_NV, RC), (RC_NV, F_NV)])
def test_opposite_directions_conflict(i7, i5):
    with pytest.raises(ValueError, match="Conflicting orientations"):
        combine_orientations(i7.id, i5.id, I5)


def test_nan_is_unset():
    assert combine_orientations(np.nan, np.nan, I5) is None
    assert combine_orientations(float(F.id), float(F.id), I5) == F
    assert combine_orientations(float(F.id), np.nan, I5) == F_NV


def test_combined_orientation_ids_for_display():
    df = pd.DataFrame({
        "orientation_i7_id": [F.id, F.id, F.id, F.id, None],
        "orientation_i5_id": [F.id, F_NV.id, RC.id, None, None],
        "sequence_i5": [I5, I5, I5, I5, I5],
    })
    assert combined_orientation_ids(df).tolist() == [F.id, F_NV.id, None, F_NV.id, None]
    single = pd.DataFrame({"orientation_i7_id": [F.id], "orientation_i5_id": [None], "sequence_i5": [None]})
    assert combined_orientation_ids(single).tolist() == [F.id]
    assert combined_orientation_ids(df.iloc[:0]).tolist() == []
