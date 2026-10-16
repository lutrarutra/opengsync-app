"""LibraryAnnotationWorkflow: kits are QueryColumns (cells hold kit ids), samples DBObjectColumns ("name [id]" / "name [new]").

For every step with such a column: submitting ids / options is accepted, 'Back' refills the spreadsheet exactly as it
was submitted, and an invalid submission is rendered again unchanged, whether the error is found by the spreadsheet
validation or by the route after it. Plain names / kit identifiers (pasted or uploaded) are resolved to the option.
"""

import uuid
from typing import Any

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ....db.create_units import create_seq_request
from .._spreadsheet import query_labels
from ._workflow import (
    AnnotationWorkflow, HUMAN, BARCODE_COLUMNS, ATAC_BARCODE_COLUMNS,
    create_dual_index_kit, create_tenx_atac_index_kit, pool_mapping,
    libraries_by_name, linked_samples, spreadsheet, spreadsheet_records,
)

L = C.LibraryType
PATTERN = "5PNNNNNNNNNN(BC)"
UNKNOWN_ID = 999_999_999
CMOS = {"CMO301": "ATGAGGAATTCCTGC", "CMO302": "CATGCCAATAGAGCG"}
ATAC_A1 = ["AAACGGCG", "CCTACCAT", "GGCGTTTC", "TTGTAAGA"]
ATAC_A2 = ["AGCCCTTT", "CAAGTCCA", "GTGAGAAG", "TCTTAGGC"]


def _records(columns: list[str], rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row)) for row in rows]


def _assert_rerendered(wf: AnnotationWorkflow, step: str, columns: list[str], rows: list[list[Any]], data: dict | None = None, error: str | None = None):
    """An invalid submission is rendered again with the cells as submitted (and the error)."""
    response = wf.post(step, {**spreadsheet(columns, rows), **(data or {})}, status=202)
    assert wf.rendered_step(response) == step
    if error is not None:
        assert error in response.text, error
    records = spreadsheet_records(response)
    assert [{title: record[title] for title in columns} for record in records] == _records(columns, rows)
    return response


def _assert_refilled(wf: AnnotationWorkflow, step: str, columns: list[str], rows: list[list[Any]]):
    """'Back' shows the spreadsheet as it was submitted."""
    response = wf.back(step)
    records = spreadsheet_records(response)
    assert [{title: record[title] for title in columns} for record in records] == _records(columns, rows)
    return response


def _cmo_kit(session: SyncSession) -> models.FeatureKit:
    suffix = uuid.uuid4().hex[:8]
    kit = session.save(Q.feature_kit.create(name=f"CellPlex {suffix}", identifier=f"CMO-{suffix}", type=C.FeatureType.CMO), flush=True)
    for name, sequence in CMOS.items():
        session.save(Q.feature.create(
            identifier=None, name=name, sequence=sequence, pattern=PATTERN, read="R2",
            type=C.FeatureType.CMO, feature_kit_id=kit.id,
        ), flush=True)
    session.commit()
    return kit


# ── Multiplexed samples (DBObjectColumn) and oligo mux (kit QueryColumn) ───


def test_define_multiplexed_samples_and_oligo_mux_columns(client, session: SyncSession, user, user_token):
    project = session.save(Q.project.create(title="Mux Columns Project", description="existing", owner_id=user.id), flush=True)
    existing = session.save(Q.sample.create(name="Mux_Existing", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    kit = _cmo_kit(session)
    label = f"[{kit.identifier}] {kit.name}"
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.post("project-select", {"project": str(project.id)}, next_step="sample-annotation")
    wf.post("sample-annotation", spreadsheet(["Sample Name", "Organism"], [[existing.id, HUMAN], ["Mux_New", HUMAN]]), next_step="sample-attribute-annotation")
    wf.attributes(["Mux_Existing", "Mux_New"])
    step = wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME, next_step="define-multiplexed-samples",
        additional_services__oligo_multiplexing="on", additional_services__oligo_multiplexing_kit="CellPlex",
    )

    # Existing samples are offered by id, new ones as new
    sample_existing, sample_new = f"Mux_Existing [{existing.id}]", "Mux_New [new]"
    mux_columns = ["Sample Name", "Multiplexing Pool"]
    assert [record["Sample Name"] for record in spreadsheet_records(step)] == [sample_existing, sample_new]

    # Invalid: an unknown option (validation), a pool name too short (route), the same sample twice in a pool (route)
    _assert_rerendered(wf, "define-multiplexed-samples", mux_columns, [[sample_existing, "Pool_A"], ["Mux_Other [new]", "Pool_A"]], error="Invalid value")
    _assert_rerendered(wf, "define-multiplexed-samples", mux_columns, [[sample_existing, "Pool_A"], [sample_new, "PA"]], error="at least 4 characters")
    _assert_rerendered(wf, "define-multiplexed-samples", mux_columns, [[sample_existing, "Pool_A"], [sample_existing, "Pool_A"], [sample_new, "Pool_A"]], error="multiple times")

    # Plain names (e.g. uploaded) are resolved to the options
    valid_mux = [[sample_existing, "Pool_A"], [sample_new, "Pool_A"]]
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [["Mux_Existing", "Pool_A"], ["Mux_New", "Pool_A"]]), next_step="oligo-mux-annotation")
    _assert_refilled(wf, "define-multiplexed-samples", mux_columns, valid_mux)
    oligo_step = wf.post("define-multiplexed-samples", spreadsheet(mux_columns, valid_mux), next_step="oligo-mux-annotation")

    # The kits are searched on the backend, cells hold kit ids
    assert f"/htmx/feature_kits/query?type_in=%5B{C.FeatureType.CMO.id}%5D" in oligo_step.text
    oligo_columns = ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"]
    valid_oligo = [
        ["Mux_Existing", "Pool_A", kit.id, "CMO301", "", "", ""],
        ["Mux_New", "Pool_A", kit.id, "CMO302", "", "", ""],
    ]
    _assert_rerendered(wf, "oligo-mux-annotation", oligo_columns, [valid_oligo[0], ["Mux_New", "Pool_A", UNKNOWN_ID, "CMO302", "", "", ""]], error="Unknown kit")
    _assert_rerendered(wf, "oligo-mux-annotation", oligo_columns, [valid_oligo[0], ["Mux_New", "Pool_A", kit.id, "CMO399", "", "", ""]], error="not found in kit")
    _assert_rerendered(wf, "oligo-mux-annotation", oligo_columns, [valid_oligo[0], ["Mux_New", "Pool_A", "", "", "", "", ""]], error="must have either")

    # The kit label (as pasted) is resolved to the kit
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [[*row[:2], label, *row[3:]] for row in valid_oligo]), next_step="complete-s-a-s")
    back = _assert_refilled(wf, "oligo-mux-annotation", oligo_columns, valid_oligo)
    assert query_labels(back, "Kit") == {kit.id: label}
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, valid_oligo), next_step="complete-s-a-s")


# ── Barcode input and 10X ATAC barcode input (index kit QueryColumns) ──────


def test_barcode_input_kit_columns(client, session: SyncSession, user, user_token):
    suffix = uuid.uuid4().hex[:8]
    dual = create_dual_index_kit(session, f"TT-{suffix}", f"Dual Index Kit {suffix}", {
        "A1": ("SI-TT-A1", "GTAACATGCG", "SI-TT-A1", "AGGTAACACT"),
        "A2": ("SI-TT-A2", "GTGGATCAAA", "SI-TT-A2", "CAGGGTTGGC"),
    })
    atac = create_tenx_atac_index_kit(session, f"NA-{suffix}", f"ATAC Index Kit {suffix}", {
        "A1": ("SI-NA-A1", ATAC_A1),
        "A2": ("SI-NA-A2", ATAC_A2),
    })
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Barcode Columns")
    wf.samples([["Nuclei_1", HUMAN], ["Nuclei_2", HUMAN]])
    wf.attributes(["Nuclei_1", "Nuclei_2"])
    wf.service(C.ServiceType.TENX_SC_MULTIOME, next_step="pooled-library-annotation")
    gex, atac_type = L.TENX_SC_GEX_3PRIME.identifier, L.TENX_SC_ATAC.identifier
    library_names = [f"{s}_{t}" for s in ["Nuclei_1", "Nuclei_2"] for t in [gex, atac_type]]
    wf.post("pooled-library-annotation", spreadsheet(["Library Name", "Pool"], [[name, "Multiome_Pool"] for name in library_names]), next_step="pool-mapping")
    step = wf.post("pool-mapping", pool_mapping(["Multiome_Pool"]), next_step="barcode-input")
    assert "/htmx/index_kits/query?type_in=" in step.text

    valid = [
        [f"Nuclei_1_{gex}", "A1", dual.id, "", "", dual.id, "", ""],
        [f"Nuclei_2_{gex}", "A2", dual.id, "", "", "", "", ""],
    ]
    # Unknown kit (validation), an ATAC kit is no i7 kit (validation), a well that is not in the kit (route)
    _assert_rerendered(wf, "barcode-input", BARCODE_COLUMNS, [valid[0], [f"Nuclei_2_{gex}", "A2", UNKNOWN_ID, "", "", "", "", ""]], error="Unknown i7 kit")
    _assert_rerendered(wf, "barcode-input", BARCODE_COLUMNS, [valid[0], [f"Nuclei_2_{gex}", "A2", atac.id, "", "", "", "", ""]], error="Unknown i7 kit")
    _assert_rerendered(wf, "barcode-input", BARCODE_COLUMNS, [valid[0], [f"Nuclei_2_{gex}", "H12", dual.id, "", "", "", "", ""]], error="not found in kit")

    # The kit identifier (as in an uploaded prep table) is resolved to the kit
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, [
        [*valid[0][:2], dual.identifier, *valid[0][3:5], dual.identifier, *valid[0][6:]], [*valid[1][:2], dual.identifier, *valid[1][3:]],
    ]), next_step="t-e-n-x-a-t-a-c-barcode-input")
    # 'Back' shows the kits by id; the second row's i5 kit was filled in from its i7 kit
    back = wf.back("barcode-input")
    back_rows = [{title: record[title] for title in BARCODE_COLUMNS} for record in spreadsheet_records(back)]
    assert [[row["Library Name"], row["Index Well"], row["i7 Kit"], row["i5 Kit"]] for row in back_rows] == [
        [f"Nuclei_1_{gex}", "A1", dual.id, dual.id], [f"Nuclei_2_{gex}", "A2", dual.id, dual.id],
    ]
    assert query_labels(back, "i7 Kit") == {dual.id: f"[{dual.identifier}] {dual.name}"}
    wf.post("barcode-input", spreadsheet(BARCODE_COLUMNS, valid), next_step="t-e-n-x-a-t-a-c-barcode-input")

    valid_atac = [
        [f"Nuclei_1_{atac_type}", "A1", atac.id, "", "", "", "", ""],
        [f"Nuclei_2_{atac_type}", "", atac.id, "SI-NA-A2", "", "", "", ""],
    ]
    _assert_rerendered(wf, "t-e-n-x-a-t-a-c-barcode-input", ATAC_BARCODE_COLUMNS, [valid_atac[0], [f"Nuclei_2_{atac_type}", "A2", dual.id, "", "", "", "", ""]], error="Unknown kit")
    _assert_rerendered(wf, "t-e-n-x-a-t-a-c-barcode-input", ATAC_BARCODE_COLUMNS, [valid_atac[0], [f"Nuclei_2_{atac_type}", "", atac.id, "", "", "", "", ""]], error="must be defined when kit is defined")

    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, valid_atac), next_step="complete-s-a-s")
    back = wf.back("t-e-n-x-a-t-a-c-barcode-input")
    assert [[record["Library Name"], record["Kit"], record["Barcode Name"]] for record in spreadsheet_records(back)] == [
        [f"Nuclei_1_{atac_type}", atac.id, "SI-NA-A1"], [f"Nuclei_2_{atac_type}", atac.id, "SI-NA-A2"],
    ]
    assert query_labels(back, "Kit") == {atac.id: f"[{atac.identifier}] {atac.name}"}
    wf.post("t-e-n-x-a-t-a-c-barcode-input", spreadsheet(ATAC_BARCODE_COLUMNS, valid_atac), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert [(i.name_i7, i.sequence_i5) for i in libraries[f"Nuclei_1_{gex}"].indices] == [("SI-TT-A1", "AGGTAACACT")]
    assert [i.sequence_i7 for i in libraries[f"Nuclei_2_{atac_type}"].indices] == ATAC_A2


# ── Visium and Open-ST (sample DBObjectColumn) ─────────────────────────────


def test_visium_sample_column(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Visium Columns")
    wf.samples([["Section_1", HUMAN], ["Section_2", HUMAN]])
    wf.attributes(["Section_1", "Section_2"])
    wf.service(C.ServiceType.CUSTOM, next_step="custom-assay-annotation")
    label = dict(C.LibraryType.as_selectable())[L.TENX_VISIUM_FFPE.id]
    step = wf.post("custom-assay-annotation", spreadsheet(["Sample Name (Pool)", "Library Type"], [
        ["Section_1", label], ["Section_2", label],
    ]), next_step="visium-annotation")
    assert [record["Sample Name"] for record in spreadsheet_records(step)] == ["Section_1 [new]", "Section_2 [new]"]

    columns = ["Sample Name", "Image", "Slide", "Area", "H&E Image"]
    instructions = {"instructions": "//share/visium"}
    valid = [["Section_1 [new]", "s1.tif", "V1", "A1", ""], ["Section_2 [new]", "s2.tif", "V1", "C1", "s2_he.tif"]]
    _assert_rerendered(wf, "visium-annotation", columns, [valid[0], ["Section_1 [new]", "s1b.tif", "V1", "B1", ""]], instructions, error="not unique")
    _assert_rerendered(wf, "visium-annotation", columns, [valid[0], ["Section_3 [new]", "s3.tif", "V1", "B1", ""]], instructions, error="Invalid value")
    _assert_rerendered(wf, "visium-annotation", columns, valid)  # instructions missing: the validated cells

    wf.post("visium-annotation", {**spreadsheet(columns, valid), **instructions}, next_step="complete-s-a-s")
    _assert_refilled(wf, "visium-annotation", columns, valid)
    wf.post("visium-annotation", {**spreadsheet(columns, valid), **instructions}, next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    library = libraries[f"Section_2_{L.TENX_VISIUM_FFPE.identifier}"]
    assert library.properties == {"image": "s2.tif", "slide": "V1", "area": "C1", "he_image": "s2_he.tif"}
    assert linked_samples(library) == {"Section_2": None}


def test_openst_sample_column(client, session: SyncSession, user, user_token):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Open-ST Columns")
    wf.samples([["Brain_1", HUMAN], ["Brain_2", HUMAN]])
    wf.attributes(["Brain_1", "Brain_2"])
    wf.service(C.ServiceType.OPENST, next_step="open-s-t-annotation")

    columns = ["Sample Name", "Image"]
    instructions = {"instructions": "//share/openst"}
    valid = [["Brain_1 [new]", "b1.tif"], ["Brain_2 [new]", "b2.tif"]]
    _assert_rerendered(wf, "open-s-t-annotation", columns, [valid[0], ["Brain_1 [new]", "b2.tif"]], instructions, error="not unique")
    _assert_rerendered(wf, "open-s-t-annotation", columns, [valid[0], ["Brain_2 [new]", ""]], instructions, error="Missing value")

    wf.post("open-s-t-annotation", {**spreadsheet(columns, [["Brain_1", "b1.tif"], ["Brain_2", "b2.tif"]]), **instructions}, next_step="complete-s-a-s")
    _assert_refilled(wf, "open-s-t-annotation", columns, valid)
    wf.post("open-s-t-annotation", {**spreadsheet(columns, valid), **instructions}, next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    assert libraries[f"Brain_2_{L.OPENST.identifier}"].properties == {"image": "b2.tif"}
