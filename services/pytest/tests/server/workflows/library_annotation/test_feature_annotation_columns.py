"""LibraryAnnotationWorkflow feature annotation: samples are picked as "name [id]" / "name [new]", kits by id."""

import uuid

from opengsync_db import SyncSession, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ._workflow import AnnotationWorkflow, HUMAN, libraries_by_name, spreadsheet, spreadsheet_rows

L = C.LibraryType
PATTERN = "5PNNNNNNNNNN(BC)"
COLUMNS = ["Sample", "Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"]


def _kit(session: SyncSession, type: C.FeatureType):
    _uuid = uuid.uuid4().hex
    kit = session.save(Q.feature_kit.create(name=f"Kit {_uuid[:8]}", identifier=f"K{_uuid[:12]}", type=type), flush=True)
    for identifier, name, sequence in [("A0001", "CD3", "CTCATTGTAACTCCT"), ("A0002", "CD4", "TGTTCCCGCTCAACT")]:
        session.save(Q.feature.create(
            identifier=identifier, name=name, sequence=sequence, pattern=PATTERN, read="R2",
            type=type, feature_kit_id=kit.id,
        ), flush=True)
    return kit


def test_feature_annotation_sample_and_kit_columns(client, session: SyncSession, user, user_token):
    project = session.save(Q.project.create(title="Feature Columns Project", description="existing", owner_id=user.id), flush=True)
    existing = session.save(Q.sample.create(name="Feat_Existing", project_id=project.id, owner_id=user.id, status=C.SampleStatus.DRAFT), flush=True)
    kit = _kit(session, C.FeatureType.ANTIBODY)
    cmo_kit = _kit(session, C.FeatureType.CMO)
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()

    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    wf.post("project-select", {"existing_project": str(project.id)}, next_step="sample-annotation")
    wf.post("sample-annotation", spreadsheet(["Sample Name", "Organism"], [[existing.id, HUMAN], ["Feat_New", HUMAN]]), next_step="sample-attribute-annotation")
    wf.attributes(["Feat_Existing", "Feat_New"])
    step = wf.service(
        C.ServiceType.TENX_SC_GEX_3PRIME, next_step="feature-annotation",
        optional_assays__antibody_capture="on", optional_assays__antibody_capture_kit="TotalSeq-B",
    )

    # Existing samples are offered by id, new ones by name; the kits are searched on the backend
    sample_existing, sample_new = f"Feat_Existing [{existing.id}]", "Feat_New [new]"
    assert sample_existing in step.text and sample_new in step.text
    assert "/htmx/feature_kits/query?type_in=" in step.text

    custom = [sample_new, "", "", "CD45", "TCCCTTGCGATTTAC", PATTERN, "R2"]
    invalid = [
        ([sample_existing, cmo_kit.id, "", "", "", "", ""], "not an antibody kit"),
        ([sample_existing, 999_999_999, "", "", "", "", ""], "unknown kit id"),
        ([sample_existing, "NOT-A-KIT", "", "", "", "", ""], "kit text instead of id"),
        (["Feat_Existing [new]", kit.id, "", "", "", "", ""], "existing sample shown as new"),
        ([f"Feat_New [{existing.id}]", kit.id, "", "", "", "", ""], "id of another sample"),
        (["Feat_Other [new]", kit.id, "", "", "", "", ""], "not a sample of an antibody capture library"),
        ([sample_existing, kit.id, "A9999", "", "", "", ""], "identifier not in kit"),
        ([sample_existing, kit.id, "", "CD999", "", "", ""], "feature not in kit"),
    ]
    for row, reason in invalid:
        response = wf.post("feature-annotation", spreadsheet(COLUMNS, [row, custom]), status=202)
        assert wf.rendered_step(response) == "feature-annotation", reason

    wf.post("feature-annotation", spreadsheet(COLUMNS, [
        [sample_existing, kit.id, "", "", "", "", ""],
        [sample_new, kit.id, "A0002", "", "", "", ""],
        custom,
    ]), next_step="complete-s-a-s")

    # 'Back' shows one row per resolved feature with the sample as option and the kit by id
    back = wf.back("feature-annotation")
    back_rows = [row[:7] for row in spreadsheet_rows(back)]
    assert len(back_rows) == 4
    assert {(row[0], row[1], row[3]) for row in back_rows} == {
        (sample_existing, kit.id, "CD3"), (sample_existing, kit.id, "CD4"),
        (sample_new, kit.id, "CD4"), (sample_new, "", "CD45"),
    }
    assert f'"{kit.id}": "[{kit.identifier}] {kit.name}"' in back.text  # the editor shows the name of the id
    wf.post("feature-annotation", spreadsheet(COLUMNS, back_rows), next_step="complete-s-a-s")
    wf.complete()

    libraries = libraries_by_name(session, seq_request.id)

    def features(sample: str) -> list[tuple[str, int | None]]:
        library = libraries[f"{sample}_{L.TENX_ANTIBODY_CAPTURE.identifier}"]
        return sorted((f.name, f.feature_kit_id) for f in library.features)

    assert features("Feat_Existing") == [("CD3", kit.id), ("CD4", kit.id)]
    assert features("Feat_New") == [("CD4", kit.id), ("CD45", None)]
