"""LibraryAnnotationWorkflow: raw samples, 10X 3' GEX with oligo (CMO) multiplexing and antibody capture."""

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import (
    AnnotationWorkflow, HUMAN, libraries_by_name, linked_samples, spreadsheet,
    assert_features_only_on_abc_libraries,
)

L = C.LibraryType


def test_raw_10x_3p_oligo_mux_abc_annotation(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    project_title = "10X 3' oligo mux + ABC raw samples"
    wf.project(project_title)

    samples = ["Sample_1", "Sample_2", "Sample_3", "Sample_4"]
    wf.samples([[s, HUMAN] for s in samples])
    wf.attributes(samples)

    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME,
        next_step="define-multiplexed-samples",
        optional_assays__antibody_capture="on",
        optional_assays__antibody_capture_kit="TotalSeq-B Human",
        additional_services__oligo_multiplexing="on",
        additional_services__oligo_multiplexing_kit="3' CellPlex",
    )

    mux_columns = ["Sample Name", "Multiplexing Pool"]
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [
        ["Sample_1", "Pool_A"],
        ["Sample_1", "Pool_A"],
        ["Sample_2", "Pool_A"],
        ["Sample_3", "Pool_B"],
        ["Sample_4", "Pool_B"],
    ]), status=202)  # same sample assigned to the same pool twice
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [
        ["Sample_1", "Pool_A"],
        ["Sample_2", "PA"],
        ["Sample_3", "Pool_B"],
        ["Sample_4", "Pool_B"],
    ]), status=202)  # pool name shorter than 4 characters
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [
        ["Sample_1", "Pool_A"],
        ["Sample_2", ""],
        ["Sample_3", "Pool_B"],
        ["Sample_4", "Pool_B"],
    ]), status=202)  # pool missing while others are set
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [
        ["Sample_1", "Pool_A"],
        ["Unknown_Sample", "Pool_A"],
        ["Sample_3", "Pool_B"],
        ["Sample_4", "Pool_B"],
    ]), status=202)  # sample not annotated in a previous step
    wf.post("define-multiplexed-samples", spreadsheet(mux_columns, [
        ["Sample_1", "Pool_A"],
        ["Sample_2", "Pool_A"],
        ["Sample_3", "Pool_B"],
        ["Sample_4", "Pool_B"],
    ]), next_step="oligo-mux-annotation")

    oligo_columns = ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"]

    def oligo_row(sample: str, pool: str, seq: str = "", pattern: str = "", read: str = "", feature: str = "", kit: str = "") -> list[str]:
        return [sample, pool, kit, feature, seq, pattern, read]

    # Custom oligos are Sequence + Pattern + Read; 'Feature' is an optional label (needed only for kit lookups).
    valid_oligo_rows = [
        oligo_row("Sample_1", "Pool_A", "atgagg aattcctgc", "5PNNNNNNNNNN(BC)", "R2", feature="CMO301"),  # normalised to upper case
        oligo_row("Sample_2", "Pool_A", "CATGCCAATAGAGCG", "5PNNNNNNNNNN(BC)", "R2"),
        oligo_row("Sample_3", "Pool_B", "ATGAGGAATTCCTGC", "5PNNNNNNNNNN(BC)", "R2"),
        oligo_row("Sample_4", "Pool_B", "CATGCCAATAGAGCG", "5PNNNNNNNNNN(BC)", "R2"),
    ]
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        oligo_row("Sample_1", "Pool_A"),
        *valid_oligo_rows[1:],
    ]), status=202)  # neither kit nor custom sequence/pattern/read
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        oligo_row("Sample_1", "Pool_A", "ATGAGGAATTCCTGC", "", "R2"),
        *valid_oligo_rows[1:],
    ]), status=202)  # custom oligo missing pattern
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        oligo_row("Sample_1", "Pool_A", "ATGAGGAATTCCTGC", "5PNNNNNNNNNN(BC)", "R2", feature="CMO301", kit="[NO-KIT] Unknown"),
        *valid_oligo_rows[1:],
    ]), status=202)  # unknown kit
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        oligo_row("Sample_1", "Pool_A", "ATGAGGXXTTCCTGC", "5PNNNNNNNNNN(BC)", "R2"),
        *valid_oligo_rows[1:],
    ]), status=202)  # sequence with non-DNA bases
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        oligo_row("Sample_1", "Pool_A", "", "", "", feature="CMO301"),
        *valid_oligo_rows[1:],
    ]), status=202)  # a feature name alone is not an oligo definition
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, [
        valid_oligo_rows[0],
        oligo_row("Sample_2", "Pool_A", "ATGAGGAATTCCTGC", "5PNNNNNNNNNN(BC)", "R2"),
        *valid_oligo_rows[2:],
    ]), status=202)  # same oligo used twice in one pool
    wf.post("oligo-mux-annotation", spreadsheet(oligo_columns, valid_oligo_rows), next_step="feature-annotation")

    feature_columns = ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"]
    valid_feature_rows = [
        ["", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
        ["", "", "", "CD4", "TGTTCCCGCTCAACT", "5PNNNNNNNNNN(BC)", "R2"],
    ]
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["", "", "", "CD3", "", "", ""],
        valid_feature_rows[1],
    ]), status=202)  # custom feature without sequence/pattern/read
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        valid_feature_rows[0],
        valid_feature_rows[0],
    ]), status=202)  # duplicate feature definition
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["Pool_A", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
    ]), status=202)  # sample-specific features must cover every ABC library (Pool_B missing)
    wf.post("feature-annotation", spreadsheet(feature_columns, [
        ["Sample_1", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
        ["Pool_B", "", "", "CD3", "CTCATTGTAACTCCT", "5PNNNNNNNNNN(BC)", "R2"],
    ]), status=202)  # sample name must be an ABC library's pool, not an individual sample
    wf.post("feature-annotation", spreadsheet(feature_columns, valid_feature_rows), next_step="complete-s-a-s")

    wf.complete()
    wf.assert_cleaned_up()

    session.expire_all()
    project = session.first(Q.project.select(title=project_title))
    assert project is not None
    assert sorted(s.name for s in session.get_all(Q.sample.select(project_id=project.id), limit=None)) == samples

    libraries = libraries_by_name(session, seq_request.id)
    expected = {
        f"{pool}_{library_type.identifier}": library_type
        for pool in ["Pool_A", "Pool_B"]
        for library_type in [L.TENX_SC_GEX_3PRIME, L.TENX_ANTIBODY_CAPTURE, L.TENX_MUX_OLIGO]
    }
    assert set(libraries) == set(expected)
    for name, library in libraries.items():
        assert library.type == expected[name]
        assert library.mux_type == C.MUXType.TENX_OLIGO
        assert library.service_type == C.ServiceType.TENX_SC_GEX_3PRIME
        assert library.genome_ref == C.GenomeRef.HUMAN
        assert library.pool_id is None
        assert library.status == C.LibraryStatus.DRAFT

    cmo = {
        "Sample_1": "ATGAGGAATTCCTGC", "Sample_2": "CATGCCAATAGAGCG",
        "Sample_3": "ATGAGGAATTCCTGC", "Sample_4": "CATGCCAATAGAGCG",
    }
    for pool, pool_samples in [("Pool_A", ["Sample_1", "Sample_2"]), ("Pool_B", ["Sample_3", "Sample_4"])]:
        for library_type in [L.TENX_SC_GEX_3PRIME, L.TENX_ANTIBODY_CAPTURE, L.TENX_MUX_OLIGO]:
            links = linked_samples(libraries[f"{pool}_{library_type.identifier}"])
            assert set(links) == set(pool_samples)
            for sample_name, mux in links.items():
                assert mux == {"barcode": cmo[sample_name], "pattern": "5PNNNNNNNNNN(BC)", "read": "R2"}

    for pool in ["Pool_A", "Pool_B"]:
        abc = libraries[f"{pool}_{L.TENX_ANTIBODY_CAPTURE.identifier}"]
        assert sorted(f.name for f in abc.features) == ["CD3", "CD4"]
    # One feature row per custom definition, shared by both ABC libraries.
    assert len({f.id for lib in libraries.values() for f in lib.features}) == 2

    session.refresh(seq_request)
    comments = [c.text for c in seq_request.comments]
    assert any("TotalSeq-B Human" in c for c in comments)
    assert any("3' CellPlex" in c for c in comments)

    assert_features_only_on_abc_libraries(libraries)
