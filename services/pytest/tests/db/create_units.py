import uuid
from typing import Optional

from opengsync_db import SyncSession, models, queries as Q

from opengsync_db.categories import (
    LibraryType, DataDeliveryMode, UserRole, FeatureType, ExperimentWorkFlow, SequencerModel,
    ReadType, ExperimentStatus, PoolType, SubmissionType, MediaFileType, GenomeRef, ServiceType,
    GroupType, LibraryStatus
)


def create_user(session: SyncSession) -> models.User:
    _uuid = str(uuid.uuid1())
    return session.save(Q.user.create(
        email=f"{_uuid}@email.com",
        first_name=_uuid,
        last_name=_uuid,
        role=UserRole.CLIENT,
        hashed_password=_uuid,
    ), flush=True)
    

def create_project(session: SyncSession, user: models.User) -> models.Project:
    _uuid = str(uuid.uuid1())
    return session.save(Q.project.create(
        title=_uuid,
        description=_uuid,
        owner_id=user.id,
    ), flush=True)


def create_contact(session: SyncSession) -> models.Contact:
    _uuid = str(uuid.uuid1())
    return session.save(Q.contact.create(
        name=_uuid,
    ), flush=True)


def create_seq_request(session: SyncSession, user: models.User) -> models.SeqRequest:
    _uuid = str(uuid.uuid1())
    contact = create_contact(session)
    organization = create_contact(session)
    return session.save(Q.seq_request.create(
        name=_uuid,
        data_delivery_mode=DataDeliveryMode.ALIGNMENT,
        description=_uuid,
        requestor=user,
        read_type=ReadType.PAIRED_END,
        organization_contact=organization,
        contact_person=contact,
        billing_contact=contact,
        group=None,
        submission_type=SubmissionType.POOLED_LIBRARIES,
    ), flush=True)


def create_sample(session: SyncSession, user: models.User, project: models.Project) -> models.Sample:
    _uuid = str(uuid.uuid1())
    return session.save(Q.sample.create(
        name=_uuid,
        owner_id=user.id,
        project_id=project.id,
        status=None,
    ), flush=True)


def create_library(session: SyncSession, user: models.User, seq_request: models.SeqRequest) -> models.Library:
    _uuid = str(uuid.uuid1())
    return session.save(Q.library.create(
        name=_uuid,
        sample_name=_uuid,
        owner_id=user.id,
        seq_request_id=seq_request.id,
        library_type=LibraryType.BULK_RNA_SEQ,
        genome_ref=GenomeRef.CUSTOM,
        service_type=ServiceType.CUSTOM,
        clone_number=0,
        status=LibraryStatus.DRAFT
    ), flush=True)


def create_pool(session: SyncSession, user: models.User, seq_request: models.SeqRequest) -> models.Pool:
    _uuid = str(uuid.uuid1())
    return session.save(Q.pool.create(
        name=_uuid,
        owner_id=user.id,
        contact_name=_uuid,
        contact_email=_uuid,
        seq_request_id=seq_request.id,
        pool_type=PoolType.EXTERNAL,
        clone_number=0,
    ), flush=True)


def create_feature(session: SyncSession, kit: models.FeatureKit | None = None) -> models.Feature:
    _uuid = str(uuid.uuid1())[:10]
    return session.save(Q.feature.create(
        identifier=None,
        name=_uuid,
        sequence=_uuid,
        pattern="pattern",
        read="R2",
        type=FeatureType.ANTIBODY,
        feature_kit_id=kit.id if kit else None,
    ), flush=True)


def create_feature_kit(
    session: SyncSession,
) -> models.FeatureKit:
    _uuid = str(uuid.uuid1())
    return session.save(Q.feature_kit.create(
        name=_uuid,
        identifier=_uuid[:10],
        type=FeatureType.ANTIBODY
    ), flush=True)


def create_sequencer(session: SyncSession) -> models.Sequencer:
    return session.save(Q.sequencer.create(
        name="sequencer",
        model=SequencerModel.NOVA_SEQ_6000,
    ), flush=True)


def create_experiment(session: SyncSession, user: models.User, workflow: ExperimentWorkFlow) -> models.Experiment:
    _uuid = str(uuid.uuid1())
    return session.save(Q.experiment.create(
        name=_uuid[:5],
        workflow=workflow,
        status=ExperimentStatus.DRAFT,
        sequencer_id=create_sequencer(session).id,
        r1_cycles=1,
        i1_cycles=1,
        operator_id=user.id,
        r2_cycles=1,
        i2_cycles=1,
    ), flush=True)


def create_file(
    session: SyncSession, seq_request: Optional[models.SeqRequest] = None,
    experiment: Optional[models.Experiment] = None, lab_prep: Optional[models.LabPrep] = None
) -> models.MediaFile:
    _uuid = str(uuid.uuid1())

    return session.save(Q.media_file.create(
        name=_uuid,
        type=MediaFileType.CUSTOM,
        extension=".txt",
        uploader_id=create_user(session).id,
        size_bytes=1,
        uuid=_uuid,
        seq_request_id=seq_request.id if seq_request else None,
        experiment_id=experiment.id if experiment else None,
        lab_prep_id=lab_prep.id if lab_prep else None,
    ), flush=True)


def create_group(
    session: SyncSession,
) -> models.Group:
    _uuid = str(uuid.uuid1())
    return session.save(Q.group.create(
        name=_uuid,
        type=GroupType.COLLABORATION
    ), flush=True)
