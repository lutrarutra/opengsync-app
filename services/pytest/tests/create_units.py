import uuid
from typing import Optional

from opengsync_db import DBHandler, models

from opengsync_db.categories import (
    LibraryType, DataDeliveryMode, UserRole, FeatureType, ExperimentWorkFlow, SequencerModel,
    ReadType, ExperimentStatus, PoolType, SubmissionType, MediaFileType, GenomeRef, ServiceType,
    GroupType
)


def create_user(db: DBHandler) -> models.User:
    _uuid = str(uuid.uuid1())
    return db.users.create(
        email=f"{_uuid}@email.com",
        first_name=_uuid,
        last_name=_uuid,
        role=UserRole.ADMIN,
        hashed_password=_uuid,
    )
    

def create_project(db: DBHandler, user: models.User) -> models.Project:
    _uuid = str(uuid.uuid1())
    return db.projects.create(
        title=_uuid,
        description=_uuid,
        owner_id=user.id,
    )


def create_contact(db: DBHandler) -> models.Contact:
    _uuid = str(uuid.uuid1())
    return db.contacts.create_contact(
        name=_uuid,
    )


def create_seq_request(db: DBHandler, user: models.User) -> models.SeqRequest:
    _uuid = str(uuid.uuid1())
    contact = create_contact(db)
    organization = create_contact(db)
    return db.seq_requests.create(
        name=_uuid,
        data_delivery_mode=DataDeliveryMode.ALIGNMENT,
        description=_uuid,
        requestor_id=user.id,
        read_type=ReadType.PAIRED_END,
        organization_contact_id=organization.id,
        contact_person_id=contact.id,
        billing_contact_id=contact.id,
        group_id=None,
        submission_type=SubmissionType.POOLED_LIBRARIES,
    )


def create_sample(db: DBHandler, user: models.User, project: models.Project) -> models.Sample:
    _uuid = str(uuid.uuid1())
    return db.samples.create(
        name=_uuid,
        owner_id=user.id,
        project_id=project.id,
        status=None,
    )


def create_library(db: DBHandler, user: models.User, seq_request: models.SeqRequest) -> models.Library:
    _uuid = str(uuid.uuid1())
    return db.libraries.create(
        name=_uuid,
        sample_name=_uuid,
        owner_id=user.id,
        seq_request_id=seq_request.id,
        library_type=LibraryType.BULK_RNA_SEQ,
        genome_ref=GenomeRef.CUSTOM,
        service_type=ServiceType.CUSTOM,
    )


def create_pool(db: DBHandler, user: models.User, seq_request: models.SeqRequest) -> models.Pool:
    _uuid = str(uuid.uuid1())
    return db.pools.create(
        name=_uuid,
        owner_id=user.id,
        contact_name=_uuid,
        contact_email=_uuid,
        seq_request_id=seq_request.id,
        pool_type=PoolType.EXTERNAL,
    )


def create_feature(db: DBHandler, kit: models.FeatureKit | None = None) -> models.Feature:
    _uuid = str(uuid.uuid1())[:10]
    return db.features.create(
        identifier=None,
        name=_uuid,
        sequence=_uuid,
        pattern="pattern",
        read="R2",
        type=FeatureType.ANTIBODY,
        feature_kit_id=kit.id if kit else None,
    )


def create_feature_kit(
    df: DBHandler,
) -> models.FeatureKit:
    _uuid = str(uuid.uuid1())
    return df.feature_kits.create(
        name=_uuid,
        identifier=_uuid[:10],
        type=FeatureType.ANTIBODY
    )


def create_sequencer(db: DBHandler) -> models.Sequencer:
    return db.sequencers.create(
        name="sequencer",
        model=SequencerModel.NOVA_SEQ_6000,
    )


def create_experiment(db: DBHandler, user: models.User, workflow: ExperimentWorkFlow) -> models.Experiment:
    _uuid = str(uuid.uuid1())
    return db.experiments.create(
        name=_uuid[:5],
        workflow=workflow,
        status=ExperimentStatus.DRAFT,
        sequencer_id=create_sequencer(db).id,
        r1_cycles=1,
        i1_cycles=1,
        operator_id=user.id,
        r2_cycles=1,
        i2_cycles=1,
    )


def create_file(
    db: DBHandler, seq_request: Optional[models.SeqRequest] = None,
    experiment: Optional[models.Experiment] = None, lab_prep: Optional[models.LabPrep] = None
) -> models.MediaFile:
    _uuid = str(uuid.uuid1())

    return db.media_files.create(
        name=_uuid,
        type=MediaFileType.CUSTOM,
        extension=".txt",
        uploader_id=create_user(db).id,
        size_bytes=1,
        uuid=_uuid,
        seq_request_id=seq_request.id if seq_request else None,
        experiment_id=experiment.id if experiment else None,
        lab_prep_id=lab_prep.id if lab_prep else None,
    )


def create_group(
    db: DBHandler,
    user: models.User,
) -> models.Group:
    _uuid = str(uuid.uuid1())
    return db.groups.create(
        name=_uuid,
        user_id=user.id,
        type=GroupType.COLLABORATION
    )