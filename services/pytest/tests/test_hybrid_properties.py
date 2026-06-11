import uuid
import sqlalchemy as sa
from opengsync_db import SyncDBHandler, models, queries as Q
from opengsync_db.categories import (
    UserRole, AffiliationType, ExperimentWorkFlow, LibraryType, DataPathType,
    MediaFileType, PrepStatus, LabChecklistType, ServiceType
)
from opengsync_db.models import links

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_pool, create_experiment, create_file, create_group, create_feature
)


def test_user_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    
    # Initial checks
    assert user.num_api_tokens == 0
    assert user.num_samples == 0
    assert user.num_seq_requests == 0
    assert user.num_projects == 0
    assert user.num_affiliations == 0
    assert user.name == f"{user.first_name} {user.last_name}"

    # Add API Token
    token = models.APIToken(
        time_valid_min=10,
        owner_id=user.id,
    )
    db.session.add(token)

    # Add Project
    project = create_project(db, user)

    # Add Sample
    sample = create_sample(db, user, project)

    # Add SeqRequest
    seq_request = create_seq_request(db, user)

    # Add Group Affiliation
    group = create_group(db)
    affiliation = links.UserAffiliation(
        user_id=user.id,
        group_id=group.id,
        affiliation_type_id=AffiliationType.MEMBER.id
    )
    db.session.add(affiliation)
    db.session.flush()

    # Refresh user
    db.session.refresh(user)

    # Python property access
    assert user.num_api_tokens == 1
    assert user.num_samples == 1
    assert user.num_seq_requests == 1
    assert user.num_projects == 1
    assert user.num_affiliations == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.User.num_api_tokens,
            models.User.num_samples,
            models.User.num_seq_requests,
            models.User.num_projects,
            models.User.num_affiliations,
            models.User.name
        ).where(models.User.id == user.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == 1
    assert res[2] == 1
    assert res[3] == 1
    assert res[4] == 1
    assert res[5] == f"{user.first_name} {user.last_name}"


def test_project_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    project = create_project(db, user)

    # Initial checks
    assert project.num_samples == 0
    assert project.library_types == []
    assert project.num_data_paths == 0
    assert project.num_assignees == 0
    assert project.num_seq_requests == 0
    assert project.num_experiments == 0

    # Add Sample
    sample = create_sample(db, user, project)

    # Add SeqRequest
    seq_request = create_seq_request(db, user)

    # Add Library
    library = create_library(db, user, seq_request)
    db.actions.link_sample_library(sample.id, library.id)

    # Add DataPath
    data_path = models.DataPath(
        path="test_path",
        project_id=project.id,
        type_id=DataPathType.CUSTOM.id,
    )
    db.session.add(data_path)

    # Add Assignee
    assignee_link = links.ProjectAssigneeLink(
        project_id=project.id,
        user_id=user.id,
    )
    db.session.add(assignee_link)

    # Add Experiment
    experiment = create_experiment(db, user, ExperimentWorkFlow.MISEQ_v2)
    # Link library to pool, pool to experiment
    pool = create_pool(db, user, seq_request)
    library.pool_id = pool.id
    db.session.flush()
    db.actions.link_pool_experiment(pool=pool, experiment=experiment)

    db.session.flush()
    db.session.refresh(project)

    # Python property access
    assert project.num_samples == 1
    assert project.library_types == [LibraryType.BULK_RNA_SEQ]
    assert project.num_data_paths == 1
    assert project.num_assignees == 1
    assert project.num_seq_requests == 1
    assert project.num_experiments == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Project.num_samples,
            models.Project.library_types,
            models.Project.num_data_paths,
            models.Project.num_assignees,
            models.Project.num_seq_requests,
            models.Project.num_experiments
        ).where(models.Project.id == project.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == [LibraryType.BULK_RNA_SEQ.id]
    assert res[2] == 1
    assert res[3] == 1
    assert res[4] == 1
    assert res[5] == 1


def test_seq_request_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)

    # Initial checks
    assert seq_request.num_projects == 0
    assert seq_request.num_libraries == 0
    assert seq_request.num_pools == 0
    assert seq_request.num_samples == 0
    assert seq_request.num_assignees == 0
    assert seq_request.num_comments == 0
    assert seq_request.num_files == 0
    assert seq_request.num_data_paths == 0
    assert seq_request.library_types == []
    assert seq_request.library_type_counts == {}
    assert seq_request.num_delivery_email_links == 0

    # Add Project
    project = create_project(db, user)

    # Add Sample
    sample = create_sample(db, user, project)

    # Add Library
    library = create_library(db, user, seq_request)
    db.actions.link_sample_library(sample.id, library.id)

    # Add Pool
    pool = create_pool(db, user, seq_request)

    # Add Assignee
    assignee_link = links.SeqRequestAssigneeLink(
        seq_request_id=seq_request.id,
        user_id=user.id,
    )
    db.session.add(assignee_link)

    # Add Comment
    comment = models.Comment(
        text="test comment",
        author_id=user.id,
        seq_request_id=seq_request.id,
    )
    db.session.add(comment)

    # Add File
    media_file = create_file(db, seq_request=seq_request)

    # Add DataPath
    data_path = models.DataPath(
        path="test_path",
        seq_request_id=seq_request.id,
        type_id=DataPathType.CUSTOM.id,
    )
    db.session.add(data_path)

    # Add Delivery Email Link
    email_link = links.SeqRequestDeliveryEmailLink(
        seq_request_id=seq_request.id,
        email="test@email.com",
    )
    db.session.add(email_link)

    db.session.flush()
    db.session.refresh(seq_request)

    # Python property access
    assert seq_request.num_projects == 1
    assert seq_request.num_libraries == 1
    assert seq_request.num_pools == 1
    assert seq_request.num_samples == 1
    assert seq_request.num_assignees == 1
    assert seq_request.num_comments == 1
    assert seq_request.num_files == 1
    assert seq_request.num_data_paths == 1
    assert seq_request.library_types == [LibraryType.BULK_RNA_SEQ]
    assert seq_request.library_type_counts == {LibraryType.BULK_RNA_SEQ: 1}
    assert seq_request.num_delivery_email_links == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.SeqRequest.num_projects,
            models.SeqRequest.num_libraries,
            models.SeqRequest.num_pools,
            models.SeqRequest.num_samples,
            models.SeqRequest.num_assignees,
            models.SeqRequest.num_comments,
            models.SeqRequest.num_files,
            models.SeqRequest.num_data_paths,
            models.SeqRequest.library_types,
            models.SeqRequest.num_delivery_email_links
        ).where(models.SeqRequest.id == seq_request.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == 1
    assert res[2] == 1
    assert res[3] == 1
    assert res[4] == 1
    assert res[5] == 1
    assert res[6] == 1
    assert res[7] == 1
    assert res[8] == [LibraryType.BULK_RNA_SEQ.id]
    assert res[9] == 1


def test_experiment_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    experiment = create_experiment(db, user, ExperimentWorkFlow.MISEQ_v2)

    # Initial checks
    assert experiment.library_types == []
    assert experiment.num_pools == 0
    assert experiment.num_libraries == 0
    assert experiment.num_files == 0
    assert experiment.num_comments == 0
    assert experiment.num_projects == 0
    assert experiment.num_data_paths == 0
    assert experiment.lane_pooling_table is None
    assert experiment.sequencer_loading_checklist is None

    # Add SeqRequest
    seq_request = create_seq_request(db, user)

    # Add Pool
    pool = create_pool(db, user, seq_request)
    db.actions.link_pool_experiment(pool=pool, experiment=experiment)

    # Add Library
    library = create_library(db, user, seq_request)
    library.pool_id = pool.id

    # Add File
    media_file = create_file(db, experiment=experiment)

    # Add Comment
    comment = models.Comment(
        text="test comment",
        author_id=user.id,
        experiment_id=experiment.id,
    )
    db.session.add(comment)

    # Add Project
    project = create_project(db, user)
    sample = create_sample(db, user, project)
    db.actions.link_sample_library(sample.id, library.id)

    # Add DataPath
    data_path = models.DataPath(
        path="test_path",
        experiment_id=experiment.id,
        type_id=DataPathType.CUSTOM.id,
    )
    db.session.add(data_path)

    # Add Lane Pooling Table
    lane_pooling_table = models.MediaFile(
        name="lane_pooling_table",
        type_id=MediaFileType.LANE_POOLING_TABLE.id,
        extension=".txt",
        uploader_id=user.id,
        size_bytes=1,
        uuid=str(uuid.uuid4()),
        experiment_id=experiment.id,
    )
    db.session.add(lane_pooling_table)

    # Add Sequencer Loading Checklist
    sequencer_loading_checklist = models.MediaFile(
        name="sequencer_loading_checklist",
        type_id=MediaFileType.SEQUENCER_LOADING_CHECKLIST.id,
        extension=".txt",
        uploader_id=user.id,
        size_bytes=1,
        uuid=str(uuid.uuid4()),
        experiment_id=experiment.id,
    )
    db.session.add(sequencer_loading_checklist)

    db.session.flush()
    db.session.refresh(experiment)

    # Python property access
    assert experiment.library_types == [LibraryType.BULK_RNA_SEQ]
    assert experiment.num_pools == 1
    assert experiment.num_libraries == 1
    assert experiment.num_files == 3  # media_file, lane_pooling_table, sequencer_loading_checklist
    assert experiment.num_comments == 1
    assert experiment.num_projects == 1
    assert experiment.num_data_paths == 1
    assert experiment.lane_pooling_table.id == lane_pooling_table.id
    assert experiment.sequencer_loading_checklist.id == sequencer_loading_checklist.id

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Experiment.library_types,
            models.Experiment.num_pools,
            models.Experiment.num_libraries,
            models.Experiment.num_files,
            models.Experiment.num_comments,
            models.Experiment.num_projects,
            models.Experiment.num_data_paths
        ).where(models.Experiment.id == experiment.id)
    ).first()
    assert res is not None
    assert res[0] == [LibraryType.BULK_RNA_SEQ.id]
    assert res[1] == 1
    assert res[2] == 1
    assert res[3] == 3
    assert res[4] == 1
    assert res[5] == 1
    assert res[6] == 1


def test_library_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)

    # Initial checks
    assert library.num_samples == 0
    assert library.num_features == 0
    assert library.num_data_paths == 0

    # Add Sample
    project = create_project(db, user)
    sample = create_sample(db, user, project)
    db.actions.link_sample_library(sample.id, library.id)

    # Add Feature
    feature = create_feature(db)
    db.actions.link_feature_library(feature.id, library.id)

    # Add DataPath
    data_path = models.DataPath(
        path="test_path",
        library_id=library.id,
        type_id=DataPathType.CUSTOM.id,
    )
    db.session.add(data_path)

    db.session.flush()
    db.session.refresh(library)

    # Python property access
    assert library.num_samples == 1
    assert library.num_features == 1
    assert library.num_data_paths == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Library.num_samples,
            models.Library.num_features,
            models.Library.num_data_paths
        ).where(models.Library.id == library.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == 1
    assert res[2] == 1


def test_api_token_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    token = models.APIToken(
        time_valid_min=10,
        owner_id=user.id,
    )
    db.session.add(token)
    db.session.flush()

    # Python property access
    assert token.expiration is not None
    assert not token.is_expired

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.APIToken.expiration
        ).where(models.APIToken.id == token.id)
    ).scalar()
    assert res is not None


def test_share_token_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    token = models.ShareToken(
        time_valid_min=10,
        owner_id=user.id,
    )
    db.session.add(token)
    db.session.flush()

    # Initial checks
    assert token.num_paths == 0
    assert token.expiration is not None
    assert not token.is_expired

    # Add SharePath
    share_path = models.SharePath(
        path="test_path",
        uuid=token.uuid,
    )
    db.session.add(share_path)
    db.session.flush()
    db.session.refresh(token)

    # Python property access
    assert token.num_paths == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.ShareToken.num_paths,
            models.ShareToken.expiration
        ).where(models.ShareToken.uuid == token.uuid)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] is not None


def test_group_hybrid_properties(db: SyncDBHandler):
    group = create_group(db)

    # Initial checks
    assert group.num_projects == 0
    assert group.num_seq_requests == 0
    assert group.num_users == 0

    # Add User Affiliation
    user = create_user(db)
    affiliation = links.UserAffiliation(
        user_id=user.id,
        group_id=group.id,
        affiliation_type_id=AffiliationType.MEMBER.id
    )
    db.session.add(affiliation)

    # Add Project
    project = create_project(db, user)
    project.group_id = group.id

    # Add SeqRequest
    seq_request = create_seq_request(db, user)
    seq_request.group_id = group.id

    db.session.flush()
    db.session.refresh(group)

    # Python property access
    assert group.num_projects == 1
    assert group.num_seq_requests == 1
    assert group.num_users == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Group.num_projects,
            models.Group.num_seq_requests,
            models.Group.num_users
        ).where(models.Group.id == group.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == 1
    assert res[2] == 1


def test_lane_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)
    pool = create_pool(db, user, seq_request)
    pool.avg_fragment_size = 300
    pool.qubit_concentration = 1.5

    # Create Lane
    lane = models.Lane(
        number=1,
        experiment_id=create_experiment(db, user, ExperimentWorkFlow.MISEQ_v2).id,
    )
    db.session.add(lane)
    db.session.flush()

    # Initial checks
    assert lane.avg_fragment_size is None
    assert lane.original_qubit_concentration is None
    assert lane.lane_molarity is None
    assert lane.sequencing_molarity is None
    assert lane.molarity is None

    # Link pool to lane
    lane_pool_link = links.LanePoolLink(
        lane_id=lane.id,
        pool_id=pool.id,
    )
    db.session.add(lane_pool_link)
    db.session.flush()
    db.session.refresh(lane)

    # Python property access
    assert lane.avg_fragment_size == 300
    assert lane.original_qubit_concentration == 1.5
    assert lane.lane_molarity is not None
    assert lane.molarity is not None

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Lane.avg_fragment_size,
            models.Lane.original_qubit_concentration,
            models.Lane.lane_molarity,
            models.Lane.molarity
        ).where(models.Lane.id == lane.id)
    ).first()
    assert res is not None
    assert res[0] == 300
    assert res[1] == 1.5
    assert res[2] is not None
    assert res[3] is not None


def test_sample_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    project = create_project(db, user)
    sample = create_sample(db, user, project)

    # Initial checks
    assert sample.num_libraries == 0

    # Add Library
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)
    db.actions.link_sample_library(sample.id, library.id)

    db.session.flush()
    db.session.refresh(sample)

    # Python property access
    assert sample.num_libraries == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Sample.num_libraries
        ).where(models.Sample.id == sample.id)
    ).scalar()
    assert res == 1


def test_pool_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    seq_request = create_seq_request(db, user)
    pool = create_pool(db, user, seq_request)

    # Initial checks
    assert pool.num_libraries == 0
    assert pool.library_types == []

    # Add Library
    library = create_library(db, user, seq_request)
    library.pool_id = pool.id

    db.session.flush()
    db.session.refresh(pool)

    # Python property access
    assert pool.num_libraries == 1
    assert pool.library_types == [LibraryType.BULK_RNA_SEQ]

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.Pool.num_libraries,
            models.Pool.library_types
        ).where(models.Pool.id == pool.id)
    ).first()
    assert res is not None
    assert res[0] == 1
    assert res[1] == [LibraryType.BULK_RNA_SEQ.id]


def test_lab_prep_hybrid_properties(db: SyncDBHandler):
    user = create_user(db)
    lab_prep = models.LabPrep(
        name="test_lab_prep",
        prep_number=1,
        status_id=PrepStatus.DRAFT.id,
        checklist_type_id=LabChecklistType.TENX_3_v3_1.id,
        service_type_id=ServiceType.CUSTOM.id,
        creator_id=user.id,
    )
    db.session.add(lab_prep)
    db.session.flush()

    # Initial checks
    assert lab_prep.library_types == []
    assert lab_prep.num_samples == 0
    assert lab_prep.num_libraries == 0
    assert lab_prep.num_pools == 0
    assert lab_prep.num_files == 0
    assert lab_prep.num_comments == 0
    assert lab_prep.num_plates == 0

    # Add Library
    seq_request = create_seq_request(db, user)
    library = create_library(db, user, seq_request)
    library.lab_prep_id = lab_prep.id

    # Add Sample
    project = create_project(db, user)
    sample = create_sample(db, user, project)
    db.actions.link_sample_library(sample.id, library.id)

    # Add Pool
    pool = create_pool(db, user, seq_request)
    pool.lab_prep_id = lab_prep.id

    # Add File
    media_file = create_file(db, lab_prep=lab_prep)

    # Add Comment
    comment = models.Comment(
        text="test comment",
        author_id=user.id,
        lab_prep_id=lab_prep.id,
    )
    db.session.add(comment)

    # Add Plate
    plate = models.Plate(
        name="test_plate",
        num_cols=12,
        num_rows=8,
        owner_id=user.id,
        lab_prep_id=lab_prep.id,
    )
    db.session.add(plate)

    db.session.flush()
    db.session.refresh(lab_prep)

    # Python property access
    assert lab_prep.library_types == [LibraryType.BULK_RNA_SEQ]
    assert lab_prep.num_samples == 1
    assert lab_prep.num_libraries == 1
    assert lab_prep.num_pools == 1
    assert lab_prep.num_files == 1
    assert lab_prep.num_comments == 1
    assert lab_prep.num_plates == 1

    # SQLAlchemy expression query
    res = db.session.execute(
        sa.select(
            models.LabPrep.library_types,
            models.LabPrep.num_samples,
            models.LabPrep.num_libraries,
            models.LabPrep.num_pools,
            models.LabPrep.num_files,
            models.LabPrep.num_comments,
            models.LabPrep.num_plates
        ).where(models.LabPrep.id == lab_prep.id)
    ).first()
    assert res is not None
    assert res[0] == [LibraryType.BULK_RNA_SEQ.id]
    assert res[1] == 1
    assert res[2] == 1
    assert res[3] == 1
    assert res[4] == 1
    assert res[5] == 1
    assert res[6] == 1
