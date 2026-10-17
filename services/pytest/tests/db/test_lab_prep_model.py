import pytest

from opengsync_db import SyncSession, actions, models, queries as Q
from opengsync_db.categories import LibraryStatus, MediaFileType, MUXType, SampleStatus

from .create_units import (
    create_user, create_project, create_sample, create_seq_request, create_library, create_lab_prep,
    create_pool, create_protocol
)  # noqa

SKIPPED_STATUSES = [LibraryStatus.FAILED, LibraryStatus.REJECTED, LibraryStatus.ARCHIVED, LibraryStatus.REMOVED]


def _add_library(session: SyncSession, user, seq_request, lab_prep, mux_type: MUXType | None = None, status: LibraryStatus | None = None):
    library = create_library(session, user, seq_request)
    library.lab_prep_id = lab_prep.id
    library.mux_type = mux_type
    if status is not None:
        library.status = status
    session.save(library, flush=True)
    return library


def _add_prep_file(session: SyncSession, user, lab_prep):
    session.save(Q.media_file.create(
        name=f"{lab_prep.name}_prep",
        type=MediaFileType.LIBRARY_PREP_FILE,
        extension=".xlsx",
        uploader_id=user.id,
        size_bytes=1,
        lab_prep_id=lab_prep.id,
    ), flush=True)
    session.refresh(lab_prep)


def test_lab_prep_checklist_prep_table_without_libraries(session: SyncSession):
    user = create_user(session)
    lab_prep = create_lab_prep(session, user)

    assert lab_prep.get_checklist()["prep_table_submitted"] is None

    _add_prep_file(session, user, lab_prep)
    assert lab_prep.get_checklist()["prep_table_submitted"] is True


def test_lab_prep_checklist_prep_table_not_blocked_by_missing_mux(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)

    library = _add_library(session, user, seq_request, lab_prep, mux_type=MUXType.TENX_OLIGO)
    sample = create_sample(session, user, project)
    actions.link_sample_library(session, sample_id=sample.id, library_id=library.id, mux={"barcode": "ACGT", "read": "R2", "pattern": ""})
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["oligo_mux_annotated"] is False
    assert checklist["prep_table_submitted"] is None

    _add_prep_file(session, user, lab_prep)
    checklist = lab_prep.get_checklist()
    assert checklist["oligo_mux_annotated"] is False
    assert checklist["prep_table_submitted"] is True


def test_lab_prep_checklist_prep_table_missing_when_ready(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)
    _add_library(session, user, seq_request, lab_prep)
    session.refresh(lab_prep)

    assert lab_prep.get_checklist()["prep_table_submitted"] is False

    _add_prep_file(session, user, lab_prep)
    assert lab_prep.get_checklist()["prep_table_submitted"] is True


@pytest.mark.parametrize("status", SKIPPED_STATUSES)
def test_lab_prep_checklist_skips_inactive_libraries_in_mux_check(session: SyncSession, status: LibraryStatus):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)

    annotated = _add_library(session, user, seq_request, lab_prep, mux_type=MUXType.TENX_FLEX_PROBE)
    actions.link_sample_library(session, sample_id=create_sample(session, user, project).id, library_id=annotated.id, mux={"barcode": "BC001"})

    # e.g. a failed library: samples without barcode
    canceled = _add_library(session, user, seq_request, lab_prep, mux_type=MUXType.TENX_FLEX_PROBE, status=status)
    actions.link_sample_library(session, sample_id=create_sample(session, user, project).id, library_id=canceled.id, mux=None)
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["flex_mux_required"] is True
    assert checklist["flex_mux_annotated"] is True
    assert checklist["flex_mux_libraries_annotations_missing"] == set()
    assert checklist["prep_table_submitted"] is False
    assert checklist["protocols_selected"] is False

    canceled.status = LibraryStatus.PREPARING
    session.flush()
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["flex_mux_annotated"] is False
    assert checklist["flex_mux_libraries_annotations_missing"] == {canceled.name}
    assert checklist["prep_table_submitted"] is None



def test_lab_prep_checklist_skips_rejected_samples_in_mux_check(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)

    library = _add_library(session, user, seq_request, lab_prep, mux_type=MUXType.TENX_FLEX_PROBE)
    actions.link_sample_library(session, sample_id=create_sample(session, user, project).id, library_id=library.id, mux={"barcode": "BC001"})
    # Failed sample, rejected before its barcode was annotated
    rejected = create_sample(session, user, project)
    actions.link_sample_library(session, sample_id=rejected.id, library_id=library.id, mux=None)
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["flex_mux_annotated"] is False
    assert checklist["flex_mux_libraries_annotations_missing"] == {library.name}

    rejected.status = SampleStatus.REJECTED
    session.flush()
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["flex_mux_required"] is True
    assert checklist["flex_mux_annotated"] is True
    assert checklist["flex_mux_libraries_annotations_missing"] == set()

@pytest.mark.parametrize("status", SKIPPED_STATUSES)
def test_lab_prep_checklist_skips_inactive_libraries_in_all_steps(session: SyncSession, status: LibraryStatus):
    user = create_user(session)
    project = create_project(session, user)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)

    done = _add_library(session, user, seq_request, lab_prep)
    done.protocol_id = create_protocol(session).id
    done.avg_fragment_size = 400
    done.pool_id = create_pool(session, user, seq_request).id
    done.indices.append(models.LibraryIndex(name_i7="IDX1", sequence_i7="ACGTACGTAA"))
    session.save(done, flush=True)

    # Nothing done on this one: no protocol, size, index, pool or mux annotation
    inactive = _add_library(session, user, seq_request, lab_prep, mux_type=MUXType.TENX_OLIGO, status=status)
    actions.link_sample_library(session, sample_id=create_sample(session, user, project).id, library_id=inactive.id, mux=None)
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["libraries_added"] is True
    assert checklist["oligo_mux_required"] is False
    assert checklist["mux_required"] is False
    assert checklist["protocols_selected"] is True
    assert checklist["library_fragment_sizes_measured"] is True
    assert checklist["libraries_indexed"] is True
    assert checklist["libraries_pooled"] is True
    assert checklist["lab_prep_completed"] is False

    inactive.status = LibraryStatus.PREPARING
    session.flush()
    session.refresh(lab_prep)

    checklist = lab_prep.get_checklist()
    assert checklist["oligo_mux_required"] is True
    assert checklist["oligo_mux_annotated"] is False
    assert checklist["protocols_selected"] is None
    assert checklist["library_fragment_sizes_measured"] is False
    assert checklist["libraries_indexed"] is False
    assert checklist["libraries_pooled"] is None
    assert checklist["lab_prep_completed"] is None


@pytest.mark.parametrize("status,pooled", [
    (LibraryStatus.PREPARING, False),
    (LibraryStatus.STORED, False),
    (LibraryStatus.SEQUENCED, True),
    (LibraryStatus.SHARED, True),
    (LibraryStatus.QC_PENDING, True),
    (LibraryStatus.QC_COMPLETED, True),
])
def test_lab_prep_checklist_libraries_pooled_without_pool(session: SyncSession, status: LibraryStatus, pooled: bool):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)

    library = _add_library(session, user, seq_request, lab_prep, status=status)
    library.indices.append(models.LibraryIndex(name_i7="IDX1", sequence_i7="ACGTACGTAA"))
    session.save(library, flush=True)
    session.refresh(lab_prep)

    assert lab_prep.get_checklist()["libraries_pooled"] is pooled
