"""LibraryAnnotationWorkflow: raw samples, 10X 5' GEX + VDJ-B + VDJ-T + antibody capture from a feature kit."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, MOUSE, libraries_by_name, linked_samples, spreadsheet, spreadsheet_rows,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType


def test_raw_10x_5p_vdj_abc_kit_annotation(
    client, session: SyncSession, user, user_token,
):
    kit = session.save(Q.feature_kit.create(name="TotalSeq-C Test Panel", identifier="TSC-TEST", type=C.FeatureType.ANTIBODY), flush=True)
    for identifier, name, sequence in [("C0001", "CD3", "CTCATTGTAACTCCT"), ("C0002", "CD4", "TGTTCCCGCTCAACT"), ("C0003", "CD8", "GCTGCGCTTTCCATT")]:
        session.save(Q.feature.create(
            identifier=identifier, name=name, sequence=sequence, pattern="5PNNNNNNNNNN(BC)", read="R2",
            type=C.FeatureType.ANTIBODY, feature_kit_id=kit.id,
        ), flush=True)
    session.commit()

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    project_title = "10X 5' VDJ + ABC raw samples"
    wf.project(project_title)

    wf.samples([["Donor_1", HUMAN], ["Donor_2", HUMAN], ["Mouse_1", MOUSE]])
    wf.attributes(["Donor_1", "Donor_2", "Mouse_1"])

    wf.service(
        C.ServiceType.TENX_SC_GEX_5PRIME,
        next_step="feature-annotation",
        optional_assays__vdj_b="on",
        optional_assays__vdj_t="on",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-C",
        additional_services__nuclei_isolation="on",
    )

    feature_columns = ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"]
    kit_label = "[TSC-TEST] TotalSeq-C Test Panel"  # the dropdown submits the display label
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["", "NOT-A-KIT", "", "", "", "", ""],
    ]), status=202)  # unknown kit identifier
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["", kit_label, "C9999", "", "", "", ""],
    ]), status=202)  # identifier not in kit
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["", kit_label, "", "CD999", "", "", ""],
    ]), status=202)  # feature name not in kit

    # Donors get the whole kit, the mouse sample gets one kit feature by identifier + a custom one.
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["Donor_1", kit_label, "", "", "", "", ""],
        ["Donor_2", kit_label, "", "", "", "", ""],
        ["Mouse_1", kit_label, "C0002", "", "", "", ""],
        ["Mouse_1", "", "", "Mouse_CD19", "AAGGCAGACGGTGCA", "5PNNNNNNNNNN(BC)", "R2"],
    ]), next_step="complete-s-a-s")

    # 'Back' shows one row per resolved feature, keyed by sample; re-submitting it gives the same result.
    back_rows = [row[:7] for row in spreadsheet_rows(wf.back("feature-annotation"))]
    assert sorted((row[0], row[3]) for row in back_rows) == sorted([
        ("Donor_1", "CD3"), ("Donor_1", "CD4"), ("Donor_1", "CD8"),
        ("Donor_2", "CD3"), ("Donor_2", "CD4"), ("Donor_2", "CD8"),
        ("Mouse_1", "CD4"), ("Mouse_1", "Mouse_CD19"),
    ])
    wf.post("feature-annotation", spreadsheet(feature_columns, back_rows), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    libraries = libraries_by_name(session, seq_request.id)
    library_types = [L.TENX_SC_GEX_5PRIME, L.TENX_ANTIBODY_CAPTURE, L.TENX_VDJ_B, L.TENX_VDJ_T]
    expected = {
        f"{sample}_{library_type.identifier}": (sample, library_type)
        for sample in ["Donor_1", "Donor_2", "Mouse_1"]
        for library_type in library_types
    }
    assert set(libraries) == set(expected)
    for name, library in libraries.items():
        sample, library_type = expected[name]
        assert library.type == library_type
        assert library.sample_name == sample
        assert library.mux_type is None
        assert library.nuclei_isolation is True
        assert library.genome_ref == (C.GenomeRef.MOUSE if sample == "Mouse_1" else C.GenomeRef.HUMAN)
        assert linked_samples(library) == {sample: None}

    def features(sample: str) -> list[str]:
        return sorted(f.name for f in libraries[f"{sample}_{L.TENX_ANTIBODY_CAPTURE.identifier}"].features)

    assert features("Donor_1") == ["CD3", "CD4", "CD8"]
    assert features("Donor_2") == ["CD3", "CD4", "CD8"]
    assert features("Mouse_1") == ["CD4", "Mouse_CD19"]

    # Kit features are reused, only the custom one is created.
    session.expire_all()
    assert session.count(Q.feature.select(feature_kit_id=kit.id)) == 3
    custom = [f for f in libraries[f"Mouse_1_{L.TENX_ANTIBODY_CAPTURE.identifier}"].features if f.name == "Mouse_CD19"]
    assert len(custom) == 1 and custom[0].feature_kit_id is None
    assert custom[0].type == C.FeatureType.ANTIBODY

    assert_features_only_on_abc_libraries(libraries)
