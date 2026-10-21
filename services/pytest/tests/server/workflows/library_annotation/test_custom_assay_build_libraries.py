"""CustomAssayAnnotationForm.build_libraries: one library per pool and annotated type, linked to every sample of the pool."""

import pandas as pd

from opengsync_db import categories as C

from server.forms.workflows.library_annotation.CustomAssayAnnotationForm import CustomAssayAnnotationForm

L = C.LibraryType


def _library_types(rows: list[tuple[str, C.LibraryType]]) -> pd.DataFrame:
    return pd.DataFrame({
        "sample_pool": [pool for pool, _ in rows],
        "library_type_id": [library_type.id for _, library_type in rows],
    })


def _links(sample_pooling_table: pd.DataFrame) -> set[tuple[str, str, str]]:
    return set(sample_pooling_table[["sample_name", "library_name", "sample_pool"]].itertuples(index=False, name=None))


def test_several_library_types_per_sample():
    sample_pooling_table = pd.DataFrame({"sample_pool": ["sample_1", "sample_2"], "sample_name": ["sample_1", "sample_2"]})
    library_table, pooling = CustomAssayAnnotationForm.build_libraries(sample_pooling_table, _library_types([
        ("sample_1", L.TENX_SC_GEX_FLEX),
        ("sample_1", L.TENX_SC_ABC_FLEX),
        ("sample_2", L.BULK_RNA_SEQ),
    ]))

    gex, abc = f"sample_1_{L.TENX_SC_GEX_FLEX.identifier}", f"sample_1_{L.TENX_SC_ABC_FLEX.identifier}"
    bulk = f"sample_2_{L.BULK_RNA_SEQ.identifier}"
    assert library_table.to_dict("records") == [
        {"library_name": gex, "sample_name": "sample_1", "library_type": L.TENX_SC_GEX_FLEX.name, "library_type_id": L.TENX_SC_GEX_FLEX.id},
        {"library_name": abc, "sample_name": "sample_1", "library_type": L.TENX_SC_ABC_FLEX.name, "library_type_id": L.TENX_SC_ABC_FLEX.id},
        {"library_name": bulk, "sample_name": "sample_2", "library_type": L.BULK_RNA_SEQ.name, "library_type_id": L.BULK_RNA_SEQ.id},
    ]
    assert len(pooling) == 3
    assert _links(pooling) == {("sample_1", gex, "sample_1"), ("sample_1", abc, "sample_1"), ("sample_2", bulk, "sample_2")}


def test_multiplexed_pool_has_one_library_per_type():
    # Two samples in one pool: each library exists once and is linked to both samples
    sample_pooling_table = pd.DataFrame({"sample_pool": ["Pool", "Pool"], "sample_name": ["S1", "S2"]})
    library_table, pooling = CustomAssayAnnotationForm.build_libraries(sample_pooling_table, _library_types([
        ("Pool", L.TENX_SC_GEX_3PRIME),
        ("Pool", L.TENX_ANTIBODY_CAPTURE),
    ]))

    gex, abc = f"Pool_{L.TENX_SC_GEX_3PRIME.identifier}", f"Pool_{L.TENX_ANTIBODY_CAPTURE.identifier}"
    assert library_table["library_name"].tolist() == [gex, abc]
    assert len(pooling) == 4
    assert _links(pooling) == {("S1", gex, "Pool"), ("S2", gex, "Pool"), ("S1", abc, "Pool"), ("S2", abc, "Pool")}


def test_resubmit_with_per_library_pooling_table():
    # After 'Back', the stored sample_pooling_table already has a row per (sample, library)
    gex_3p = f"Pool_{L.TENX_SC_GEX_3PRIME.identifier}"
    sample_pooling_table = pd.DataFrame({
        "sample_pool": ["Pool"] * 4,
        "sample_name": ["S1", "S2", "S1", "S2"],
        "library_name": [gex_3p, gex_3p, "Pool_OLD", "Pool_OLD"],
    })
    library_table, pooling = CustomAssayAnnotationForm.build_libraries(sample_pooling_table, _library_types([
        ("Pool", L.TENX_SC_GEX_3PRIME),
    ]))

    assert library_table["library_name"].tolist() == [gex_3p]
    assert _links(pooling) == {("S1", gex_3p, "Pool"), ("S2", gex_3p, "Pool")}
    assert len(pooling) == 2
