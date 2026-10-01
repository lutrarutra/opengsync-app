"""LibraryAnnotationWorkflow: antibody feature input is validated and normalised before it is stored."""

from opengsync_db import SyncSession, models, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, spreadsheet

L = C.LibraryType
PATTERN = "5PNNNNNNNNNN(BC)"


def test_input_features(
    client, session: SyncSession, user, user_token,
):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.project("Feature input validation")
    wf.samples([["Feat_1", HUMAN]])
    wf.attributes(["Feat_1"])
    wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME, next_step="feature-annotation",
        optional_assays__antibody_capture="on", optional_assays__antibody_capture_kit="  TotalSeq-B  ",
    )

    columns = ["Sample Name", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"]
    cd4 = ["", "", "", "CD4", "TGTTCCCGCTCAACT", PATTERN, "R2"]
    invalid = [
        (["", "", "", "CD3", "CTCATTGTAACTCCZ", PATTERN, "R2"], "non-DNA base in sequence"),
        (["", "", "", "CD3", "CTCATTGTAACTCCT", PATTERN, "R3"], "read must be R1 or R2"),
        (["", "", "", "", "CTCATTGTAACTCCT", PATTERN, "R2"], "antibody feature needs a name"),
        (["", "", "", "CD3", "CTCATTGTAACTCCT", "", "R2"], "missing pattern"),
        (["", "", "", "C" * (models.Feature.name.type.length + 1), "CTCATTGTAACTCCT", PATTERN, "R2"], "name too long"),
        (["", "", "", "CD3", "A" * (models.Feature.sequence.type.length + 1), PATTERN, "R2"], "sequence too long"),
        (["Feat_2", "", "", "CD3", "CTCATTGTAACTCCT", PATTERN, "R2"], "unknown sample"),
        (["", "", "", "CD3", "TGTTCCCGCTCAACT", PATTERN, "R2"], "same sequence as CD4"),
    ]
    for row, reason in invalid:
        response = wf.post("feature-annotation", spreadsheet(columns, [row, cd4]), status=202)
        assert wf.rendered_step(response) == "feature-annotation", reason

    wf.post("feature-annotation", spreadsheet(columns, [
        [" Feat_1 ", "", "", "  CD3 ", "ctcatt gtaactcct", f"  {PATTERN} ", "R2"],
        cd4,
    ]), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)
    abc = libraries[f"Feat_1_{L.TENX_ANTIBODY_CAPTURE.identifier}"]
    features = {f.name: f for f in abc.features}
    assert set(features) == {"CD3", "CD4"}
    assert (features["CD3"].sequence, features["CD3"].pattern, features["CD3"].read) == ("CTCATTGTAACTCCT", PATTERN, "R2")
    assert libraries[f"Feat_1_{L.TENX_SC_GEX_3PRIME.identifier}"].features == []

    session.refresh(seq_request)
    assert any(c.text.endswith(": TotalSeq-B") for c in seq_request.comments)  # comment text is stripped
