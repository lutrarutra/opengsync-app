import pytest

from opengsync_db import SyncSession, actions, categories as C, models, queries as Q

from .create_units import create_library, create_project, create_sample, create_seq_request, create_user


def test_project_split_moves_selected_samples_and_sets_destination_status(session: SyncSession):
    user = create_user(session)
    source = create_project(session, user)
    destination = create_project(session, user)
    moved = create_sample(session, user, source)
    retained = create_sample(session, user, source)
    session.flush()

    actions.split_project(
        session,
        project_src=source,
        project_dst=destination,
        sample_ids=[moved.id],
        destination_status=C.ProjectStatus.PROCESSING,
    )
    session.refresh(source)
    session.refresh(destination)

    assert source.status == C.ProjectStatus.DRAFT
    assert destination.status == C.ProjectStatus.PROCESSING
    assert [sample.id for sample in source.samples] == [retained.id]
    assert [sample.id for sample in destination.samples] == [moved.id]


def test_project_split_merges_duplicate_sample_and_skips_duplicate_library_link(session: SyncSession):
    user = create_user(session)
    source = create_project(session, user)
    destination = create_project(session, user)
    source_sample = session.save(Q.sample.create("shared", user.id, source.id, None), flush=True)
    destination_sample = session.save(Q.sample.create("shared", user.id, destination.id, None), flush=True)
    source_sample.set_attribute("condition", "treated", C.AttributeType.CONDITION)
    destination_sample.set_attribute("condition", "treated", C.AttributeType.CONDITION)
    request = create_seq_request(session, user)
    library = create_library(session, user, request)
    actions.link_sample_library(session, source_sample.id, library.id)
    actions.link_sample_library(session, destination_sample.id, library.id)
    session.flush()

    actions.split_project(
        session,
        project_src=source,
        project_dst=destination,
        sample_ids=[source_sample.id],
        destination_status=C.ProjectStatus.DELIVERED,
    )
    session.refresh(destination)
    session.refresh(source)

    assert len(source.samples) == 0
    assert len(destination.samples) == 1
    assert destination.samples[0].name == "shared"
    assert destination.samples[0].get_attribute("condition").value == "treated"
    assert len(destination.samples[0].library_links) == 1


def test_project_split_attribute_conflict_is_preflighted_without_mutation(session: SyncSession):
    user = create_user(session)
    source = create_project(session, user)
    destination = create_project(session, user)
    source_sample = session.save(Q.sample.create("shared", user.id, source.id, None), flush=True)
    destination_sample = session.save(Q.sample.create("shared", user.id, destination.id, None), flush=True)
    source_sample.set_attribute("condition", "treated", C.AttributeType.CONDITION)
    destination_sample.set_attribute("condition", "control", C.AttributeType.CONDITION)
    session.flush()

    with pytest.raises(ValueError, match="incompatible attribute values"):
        actions.split_project(
            session,
            project_src=source,
            project_dst=destination,
            sample_ids=[source_sample.id],
            destination_status=C.ProjectStatus.ARCHIVED,
        )

    session.refresh(source_sample)
    session.refresh(destination_sample)
    assert source_sample.project_id == source.id
    assert destination_sample.project_id == destination.id
    assert source.status == C.ProjectStatus.DRAFT
    assert destination.status == C.ProjectStatus.DRAFT


def test_project_split_moves_non_duplicate_library_and_plate_links(session: SyncSession):
    user = create_user(session)
    source = create_project(session, user)
    destination = create_project(session, user)
    source_sample = create_sample(session, user, source)
    request = create_seq_request(session, user)
    library = create_library(session, user, request)
    plate = session.save(Q.plate.create("plate", num_cols=2, num_rows=2, owner=user), flush=True)

    actions.link_sample_library(session, source_sample.id, library.id)
    source_sample.plate_links.append(
        models.links.SamplePlateLink(plate=plate, sample=source_sample, well_idx=0)
    )
    session.flush()

    actions.split_project(
        session,
        project_src=source,
        project_dst=destination,
        sample_ids=[source_sample.id],
        destination_status=C.ProjectStatus.PROCESSING,
    )
    session.expire_all()

    moved = session.first(Q.sample.select(id=source_sample.id))
    assert moved is not None
    assert moved.project_id == destination.id
    assert [link.library_id for link in moved.library_links] == [library.id]
    assert [(link.plate_id, link.well_idx) for link in moved.plate_links] == [(plate.id, 0)]
