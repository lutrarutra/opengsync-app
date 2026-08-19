import uuid
from datetime import datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import orm
from sqlalchemy.ext.hybrid import hybrid_property

from opengsync_db import SyncSession, actions, models
from opengsync_db.categories import (
    AffiliationType, ExperimentWorkFlow, LibraryType, DataPathType,
    MediaFileType, PrepStatus, LabChecklistType, ServiceType
)
from opengsync_db.models import links
from opengsync_db.models.Base import Base

from .create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_pool, create_experiment, create_file, create_group, create_feature
)


HYBRID_COVERAGE: dict[type, list[str]] = {
    models.User: [
        "num_api_tokens", "num_samples", "num_seq_requests", "num_projects",
        "num_affiliations", "is_insider", "is_admin", "name",
    ],
    models.Project: [
        "num_samples", "library_types", "num_data_paths", "num_assignees",
        "num_seq_requests", "num_experiments",
    ],
    models.SeqRequest: [
        "num_projects", "num_libraries", "num_pools", "num_samples", "num_assignees",
        "num_comments", "num_files", "num_data_paths", "library_types", "mux_types",
        "library_type_counts", "num_delivery_email_links",
    ],
    models.Experiment: [
        "library_types", "num_pools", "num_libraries", "num_files", "num_comments",
        "num_projects", "num_data_paths",
    ],
    models.Library: [
        "num_samples", "num_features", "num_data_paths",
        "is_multiplexed", "is_editable", "is_indexed", "is_pooled",
    ],
    models.Sample: ["num_libraries"],
    models.Pool: ["num_libraries", "library_types", "molarity"],
    models.ShareToken: ["num_paths", "expiration"],
    models.APIToken: ["expiration"],
    models.Group: ["num_projects", "num_seq_requests", "num_users"],
    models.Lane: [
        "avg_fragment_size", "original_qubit_concentration", "original_molarity",
        "lane_molarity", "sequencing_molarity", "molarity",
    ],
    models.LabPrep: [
        "library_types", "num_samples", "num_libraries", "num_pools",
        "num_files", "num_comments", "num_plates",
    ],
    models.FlowCellDesign: [
        "num_m_reads", "r1_cycles", "i1_cycles", "i2_cycles", "r2_cycles",
    ],
}


def _declared_hybrids(model: type) -> set[str]:
    return {
        name for name, value in model.__dict__.items()
        if isinstance(value, hybrid_property)
    }


def _pk(model: type, instance: Any) -> tuple[Any, Any]:
    pk_col = sa_inspect(model).primary_key[0]
    return pk_col, getattr(instance, pk_col.key)


def _query_expression_attr(model: type, hybrid_name: str):
    col_name = f"_{hybrid_name}"
    mapper = sa_inspect(model)
    try:
        prop = mapper.column_attrs[col_name]
    except KeyError:
        return None
    if prop.columns:
        return None
    return getattr(model, col_name)


def _sql_expected(value: Any) -> Any:
    if isinstance(value, list):
        return [item.id if hasattr(item, "id") else item for item in value]
    if isinstance(value, dict) and value:
        key = next(iter(value))
        if hasattr(key, "id"):
            return {key.id: val for key, val in value.items()}
    return value


def _normalize_sql_got(got: Any, want: Any) -> Any:
    if isinstance(want, list) and got is None:
        return []
    if isinstance(want, dict) and got is None:
        return {}
    if isinstance(want, dict) and isinstance(got, dict):
        return {int(k): v for k, v in got.items()}
    return got


def _values_equal(got: Any, want: Any) -> bool:
    if isinstance(want, float) and got is not None:
        return got == pytest.approx(want, rel=1e-6, abs=1e-9)
    if isinstance(want, datetime) and isinstance(got, datetime):
        return abs((want - got).total_seconds()) < 2
    return got == want


def assert_hybrids(
    session: SyncSession,
    instance: Any,
    model: type,
    expected: dict[str, Any],
) -> None:
    """Assert lazy Python, SQL expression, and with_expression all agree.

    The instance is expired first so getters hit the SQL path instead of
    loaded relationships. with_expression is used whenever the model has a
    matching query_expression column.
    """
    missing = set(expected) - _declared_hybrids(model)
    assert not missing, f"{model.__name__} missing hybrids in coverage call: {missing}"

    session.flush()
    session.expire(instance)

    for name, want in expected.items():
        got = getattr(instance, name)
        assert _values_equal(got, want), f"{model.__name__}.{name} lazy: {got!r} != {want!r}"

    pk_col, pk = _pk(model, instance)
    names = list(expected)
    row = session.execute(
        sa.select(*[getattr(model, name) for name in names]).where(pk_col == pk)
    ).one()
    for i, name in enumerate(names):
        want_sql = _sql_expected(expected[name])
        got = _normalize_sql_got(row[i], want_sql)
        assert _values_equal(got, want_sql), f"{model.__name__}.{name} sql: {got!r} != {want_sql!r}"

    options = []
    expressed: list[str] = []
    for name in names:
        col = _query_expression_attr(model, name)
        hybrid = getattr(model, name)
        if col is None or not hasattr(hybrid, "expression"):
            continue
        options.append(orm.with_expression(col, hybrid.expression))
        expressed.append(name)

    if not options:
        return

    loaded = session.execute(
        sa.select(model).where(pk_col == pk).options(*options).execution_options(populate_existing=True)
    ).scalar_one()
    for name in expressed:
        got = getattr(loaded, name)
        want = expected[name]
        assert _values_equal(got, want), f"{model.__name__}.{name} with_expression: {got!r} != {want!r}"


def test_all_model_hybrids_are_covered():
    covered_models = set(HYBRID_COVERAGE)
    mapped = {mapper.class_ for mapper in Base.registry.mappers}
    undeclared = []
    for model in mapped:
        hybrids = _declared_hybrids(model)
        if not hybrids:
            continue
        if model not in covered_models:
            undeclared.append(f"{model.__name__}: {sorted(hybrids)}")
            continue
        expected = set(HYBRID_COVERAGE[model])
        assert hybrids == expected, (
            f"{model.__name__} hybrid coverage mismatch. "
            f"missing={sorted(hybrids - expected)} extra={sorted(expected - hybrids)}"
        )
    assert not undeclared, "Uncovered hybrid models:\n" + "\n".join(undeclared)


def test_user_hybrid_properties(session: SyncSession):
    user = create_user(session)
    assert_hybrids(session, user, models.User, {
        "num_api_tokens": 0,
        "num_samples": 0,
        "num_seq_requests": 0,
        "num_projects": 0,
        "num_affiliations": 0,
        "is_insider": False,
        "is_admin": False,
        "name": f"{user.first_name} {user.last_name}",
    })

    token = models.APIToken(time_valid_min=10, owner_id=user.id)
    session.add(token)
    project = create_project(session, user)
    create_sample(session, user, project)
    create_seq_request(session, user)
    group = create_group(session)
    session.add(links.UserAffiliation(
        user_id=user.id, group_id=group.id, affiliation_type_id=AffiliationType.MEMBER.id,
    ))
    session.flush()

    other = create_user(session)
    other_project = create_project(session, other)
    create_sample(session, other, other_project)
    create_seq_request(session, other)
    session.add(models.APIToken(time_valid_min=10, owner_id=other.id))
    session.add(links.UserAffiliation(
        user_id=other.id, group_id=group.id, affiliation_type_id=AffiliationType.MEMBER.id,
    ))

    assert_hybrids(session, user, models.User, {
        "num_api_tokens": 1,
        "num_samples": 1,
        "num_seq_requests": 1,
        "num_projects": 1,
        "num_affiliations": 1,
        "is_insider": False,
        "is_admin": False,
        "name": f"{user.first_name} {user.last_name}",
    })


def test_project_hybrid_properties(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    assert_hybrids(session, project, models.Project, {
        "num_samples": 0,
        "library_types": [],
        "num_data_paths": 0,
        "num_assignees": 0,
        "num_seq_requests": 0,
        "num_experiments": 0,
    })

    sample = create_sample(session, user, project)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    session.add(models.DataPath(path="test_path", project_id=project.id, type_id=DataPathType.CUSTOM.id))
    session.add(links.ProjectAssigneeLink(project_id=project.id, user_id=user.id))
    experiment = create_experiment(session, user, ExperimentWorkFlow.MISEQ_v2)
    pool = create_pool(session, user, seq_request)
    library.pool_id = pool.id
    session.flush()
    actions.link_pool_experiment(session, pool=pool, experiment=experiment)

    other = create_project(session, user)
    other_sample = create_sample(session, user, other)
    other_request = create_seq_request(session, user)
    other_library = create_library(session, user, other_request)
    actions.link_sample_library(session, other_sample.id, other_library.id)
    other_experiment = create_experiment(session, user, ExperimentWorkFlow.MISEQ_v2)
    other_pool = create_pool(session, user, other_request)
    other_library.pool_id = other_pool.id
    session.flush()
    actions.link_pool_experiment(session, pool=other_pool, experiment=other_experiment)
    session.add(models.DataPath(path="other_path", project_id=other.id, type_id=DataPathType.CUSTOM.id))
    session.add(links.ProjectAssigneeLink(project_id=other.id, user_id=user.id))

    assert_hybrids(session, project, models.Project, {
        "num_samples": 1,
        "library_types": [LibraryType.BULK_RNA_SEQ],
        "num_data_paths": 1,
        "num_assignees": 1,
        "num_seq_requests": 1,
        "num_experiments": 1,
    })


def test_seq_request_hybrid_properties(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    assert_hybrids(session, seq_request, models.SeqRequest, {
        "num_projects": 0,
        "num_libraries": 0,
        "num_pools": 0,
        "num_samples": 0,
        "num_assignees": 0,
        "num_comments": 0,
        "num_files": 0,
        "num_data_paths": 0,
        "library_types": [],
        "mux_types": [],
        "library_type_counts": {},
        "num_delivery_email_links": 0,
    })

    project = create_project(session, user)
    sample = create_sample(session, user, project)
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    create_pool(session, user, seq_request)
    session.add(links.SeqRequestAssigneeLink(seq_request_id=seq_request.id, user_id=user.id))
    session.add(models.Comment(text="test comment", author_id=user.id, seq_request_id=seq_request.id))
    create_file(session, seq_request=seq_request)
    session.add(models.DataPath(path="test_path", seq_request_id=seq_request.id, type_id=DataPathType.CUSTOM.id))
    session.add(links.SeqRequestDeliveryEmailLink(seq_request_id=seq_request.id, email="test@email.com"))

    other = create_seq_request(session, user)
    other_project = create_project(session, user)
    other_sample = create_sample(session, user, other_project)
    other_library = create_library(session, user, other)
    actions.link_sample_library(session, other_sample.id, other_library.id)
    create_pool(session, user, other)
    session.add(links.SeqRequestAssigneeLink(seq_request_id=other.id, user_id=user.id))
    session.add(models.Comment(text="other", author_id=user.id, seq_request_id=other.id))
    create_file(session, seq_request=other)
    session.add(models.DataPath(path="other_path", seq_request_id=other.id, type_id=DataPathType.CUSTOM.id))
    session.add(links.SeqRequestDeliveryEmailLink(seq_request_id=other.id, email="other@email.com"))

    assert_hybrids(session, seq_request, models.SeqRequest, {
        "num_projects": 1,
        "num_libraries": 1,
        "num_pools": 1,
        "num_samples": 1,
        "num_assignees": 1,
        "num_comments": 1,
        "num_files": 1,
        "num_data_paths": 1,
        "library_types": [LibraryType.BULK_RNA_SEQ],
        "mux_types": [],
        "library_type_counts": {LibraryType.BULK_RNA_SEQ: 1},
        "num_delivery_email_links": 1,
    })


def test_experiment_hybrid_properties(session: SyncSession):
    user = create_user(session)
    experiment = create_experiment(session, user, ExperimentWorkFlow.MISEQ_v2)
    assert_hybrids(session, experiment, models.Experiment, {
        "library_types": [],
        "num_pools": 0,
        "num_libraries": 0,
        "num_files": 0,
        "num_comments": 0,
        "num_projects": 0,
        "num_data_paths": 0,
    })

    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    library = create_library(session, user, seq_request)
    library.pool_id = pool.id
    session.flush()
    actions.link_pool_experiment(session, pool=pool, experiment=experiment)
    create_file(session, experiment=experiment)
    session.add(models.Comment(text="test comment", author_id=user.id, experiment_id=experiment.id))
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    actions.link_sample_library(session, sample.id, library.id)
    session.add(models.DataPath(path="test_path", experiment_id=experiment.id, type_id=DataPathType.CUSTOM.id))
    session.add(models.MediaFile(
        name="lane_pooling_table", type_id=MediaFileType.LANE_POOLING_TABLE.id, extension=".txt",
        uploader_id=user.id, size_bytes=1, uuid=str(uuid.uuid4()), experiment_id=experiment.id,
    ))
    session.add(models.MediaFile(
        name="sequencer_loading_checklist", type_id=MediaFileType.SEQUENCER_LOADING_CHECKLIST.id,
        extension=".txt", uploader_id=user.id, size_bytes=1, uuid=str(uuid.uuid4()),
        experiment_id=experiment.id,
    ))

    other = create_experiment(session, user, ExperimentWorkFlow.MISEQ_v2)
    other_request = create_seq_request(session, user)
    other_pool = create_pool(session, user, other_request)
    other_library = create_library(session, user, other_request)
    other_library.pool_id = other_pool.id
    session.flush()
    actions.link_pool_experiment(session, pool=other_pool, experiment=other)
    other_project = create_project(session, user)
    other_sample = create_sample(session, user, other_project)
    actions.link_sample_library(session, other_sample.id, other_library.id)
    create_file(session, experiment=other)
    session.add(models.Comment(text="other", author_id=user.id, experiment_id=other.id))
    session.add(models.DataPath(path="other_path", experiment_id=other.id, type_id=DataPathType.CUSTOM.id))

    assert_hybrids(session, experiment, models.Experiment, {
        "library_types": [LibraryType.BULK_RNA_SEQ],
        "num_pools": 1,
        "num_libraries": 1,
        "num_files": 3,
        "num_comments": 1,
        "num_projects": 1,
        "num_data_paths": 1,
    })


def test_library_hybrid_properties(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    assert_hybrids(session, library, models.Library, {
        "num_samples": 0,
        "num_features": 0,
        "num_data_paths": 0,
        "is_multiplexed": False,
        "is_editable": True,
        "is_indexed": False,
        "is_pooled": False,
    })

    project = create_project(session, user)
    sample = create_sample(session, user, project)
    actions.link_sample_library(session, sample.id, library.id)
    feature = create_feature(session)
    actions.link_feature_library(session, feature.id, library.id)
    session.add(models.DataPath(path="test_path", library_id=library.id, type_id=DataPathType.CUSTOM.id))

    other = create_library(session, user, seq_request)
    other_sample = create_sample(session, user, project)
    actions.link_sample_library(session, other_sample.id, other.id)
    other_feature = create_feature(session)
    actions.link_feature_library(session, other_feature.id, other.id)
    session.add(models.DataPath(path="other_path", library_id=other.id, type_id=DataPathType.CUSTOM.id))

    assert_hybrids(session, library, models.Library, {
        "num_samples": 1,
        "num_features": 1,
        "num_data_paths": 1,
        "is_multiplexed": False,
        "is_editable": True,
        "is_indexed": False,
        "is_pooled": False,
    })


def test_api_token_hybrid_properties(session: SyncSession):
    user = create_user(session)
    token = models.APIToken(time_valid_min=10, owner_id=user.id)
    session.add(token)
    session.flush()
    assert_hybrids(session, token, models.APIToken, {"expiration": token.expiration})
    assert not token.is_expired


def test_share_token_hybrid_properties(session: SyncSession):
    user = create_user(session)
    token = models.ShareToken(time_valid_min=10, owner_id=user.id)
    session.add(token)
    session.flush()
    assert_hybrids(session, token, models.ShareToken, {
        "num_paths": 0,
        "expiration": token.expiration,
    })

    session.add(models.SharePath(path="test_path", uuid=token.uuid))
    other = models.ShareToken(time_valid_min=10, owner_id=user.id)
    session.add(other)
    session.flush()
    session.add(models.SharePath(path="other_path", uuid=other.uuid))

    assert_hybrids(session, token, models.ShareToken, {
        "num_paths": 1,
        "expiration": token.expiration,
    })
    assert not token.is_expired


def test_group_hybrid_properties(session: SyncSession):
    group = create_group(session)
    assert_hybrids(session, group, models.Group, {
        "num_projects": 0,
        "num_seq_requests": 0,
        "num_users": 0,
    })

    user = create_user(session)
    session.add(links.UserAffiliation(
        user_id=user.id, group_id=group.id, affiliation_type_id=AffiliationType.MEMBER.id,
    ))
    project = create_project(session, user)
    project.group_id = group.id
    seq_request = create_seq_request(session, user)
    seq_request.group_id = group.id

    other = create_group(session)
    other_user = create_user(session)
    session.add(links.UserAffiliation(
        user_id=other_user.id, group_id=other.id, affiliation_type_id=AffiliationType.MEMBER.id,
    ))
    other_project = create_project(session, other_user)
    other_project.group_id = other.id
    other_request = create_seq_request(session, other_user)
    other_request.group_id = other.id

    assert_hybrids(session, group, models.Group, {
        "num_projects": 1,
        "num_seq_requests": 1,
        "num_users": 1,
    })


def test_lane_hybrid_properties(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    pool.avg_fragment_size = 300
    pool.qubit_concentration = 1.5
    experiment = create_experiment(session, user, ExperimentWorkFlow.MISEQ_v2)
    lane = experiment.lanes[0]
    assert_hybrids(session, lane, models.Lane, {
        "avg_fragment_size": None,
        "original_qubit_concentration": None,
        "original_molarity": None,
        "lane_molarity": None,
        "sequencing_molarity": None,
        "molarity": None,
    })

    actions.add_pool_to_lane(session, experiment, pool=pool, lane=lane)
    other_pool = create_pool(session, user, seq_request)
    other_pool.avg_fragment_size = 100
    other_pool.qubit_concentration = 9.0
    other_lane = experiment.lanes[1]
    actions.add_pool_to_lane(session, experiment, pool=other_pool, lane=other_lane)
    session.refresh(lane)

    expected_molarity = 1.5 / (300 * 660) * 1_000_000
    assert_hybrids(session, lane, models.Lane, {
        "avg_fragment_size": 300,
        "original_qubit_concentration": 1.5,
        "original_molarity": expected_molarity,
        "lane_molarity": lane.lane_molarity,
        "sequencing_molarity": lane.sequencing_molarity,
        "molarity": lane.molarity,
    })


def test_sample_hybrid_properties(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    assert_hybrids(session, sample, models.Sample, {"num_libraries": 0})

    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    other = create_sample(session, user, project)
    other_library = create_library(session, user, seq_request)
    actions.link_sample_library(session, other.id, other_library.id)

    assert_hybrids(session, sample, models.Sample, {"num_libraries": 1})


def test_pool_hybrid_properties(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    pool = create_pool(session, user, seq_request)
    assert_hybrids(session, pool, models.Pool, {
        "num_libraries": 0,
        "library_types": [],
        "molarity": None,
    })

    library = create_library(session, user, seq_request)
    library.pool_id = pool.id
    pool.avg_fragment_size = 300
    pool.qubit_concentration = 1.5
    other = create_pool(session, user, seq_request)
    other_library = create_library(session, user, seq_request)
    other_library.pool_id = other.id
    other.avg_fragment_size = 100
    other.qubit_concentration = 9.0

    expected_molarity = 1.5 / (300 * 660) * 1_000_000
    assert_hybrids(session, pool, models.Pool, {
        "num_libraries": 1,
        "library_types": [LibraryType.BULK_RNA_SEQ],
        "molarity": expected_molarity,
    })


def test_lab_prep_hybrid_properties(session: SyncSession):
    user = create_user(session)
    lab_prep = models.LabPrep(
        name="test_lab_prep",
        prep_number=1,
        status_id=PrepStatus.PREPARING.id,
        checklist_type_id=LabChecklistType.SMART_SEQ.id,
        service_type_id=ServiceType.CUSTOM.id,
        creator_id=user.id,
    )
    session.add(lab_prep)
    session.flush()
    assert_hybrids(session, lab_prep, models.LabPrep, {
        "library_types": [],
        "num_samples": 0,
        "num_libraries": 0,
        "num_pools": 0,
        "num_files": 0,
        "num_comments": 0,
        "num_plates": 0,
    })

    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.lab_prep_id = lab_prep.id
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    actions.link_sample_library(session, sample.id, library.id)
    pool = create_pool(session, user, seq_request)
    pool.lab_prep_id = lab_prep.id
    create_file(session, lab_prep=lab_prep)
    session.add(models.Comment(text="test comment", author_id=user.id, lab_prep_id=lab_prep.id))
    session.add(models.Plate(
        name="test_plate", num_cols=12, num_rows=8, owner_id=user.id, lab_prep_id=lab_prep.id,
    ))

    other = models.LabPrep(
        name="other_lab_prep",
        prep_number=2,
        status_id=PrepStatus.PREPARING.id,
        checklist_type_id=LabChecklistType.SMART_SEQ.id,
        service_type_id=ServiceType.CUSTOM.id,
        creator_id=user.id,
    )
    session.add(other)
    session.flush()
    other_library = create_library(session, user, seq_request)
    other_library.lab_prep_id = other.id
    other_sample = create_sample(session, user, project)
    actions.link_sample_library(session, other_sample.id, other_library.id)
    other_pool = create_pool(session, user, seq_request)
    other_pool.lab_prep_id = other.id
    create_file(session, lab_prep=other)
    session.add(models.Comment(text="other", author_id=user.id, lab_prep_id=other.id))
    session.add(models.Plate(
        name="other_plate", num_cols=12, num_rows=8, owner_id=user.id, lab_prep_id=other.id,
    ))

    assert_hybrids(session, lab_prep, models.LabPrep, {
        "library_types": [LibraryType.BULK_RNA_SEQ],
        "num_samples": 1,
        "num_libraries": 1,
        "num_pools": 1,
        "num_files": 1,
        "num_comments": 1,
        "num_plates": 1,
    })


def test_flow_cell_design_hybrid_properties(session: SyncSession):
    design = models.FlowCellDesign(name="design-a")
    session.add(design)
    session.flush()
    assert_hybrids(session, design, models.FlowCellDesign, {
        "num_m_reads": 0.0,
        "r1_cycles": 0,
        "i1_cycles": 0,
        "i2_cycles": 0,
        "r2_cycles": 0,
    })

    session.add(models.PoolDesign(
        name="pool-a", cycles_r1=51, cycles_i1=8, cycles_i2=8, cycles_r2=51,
        flow_cell_design_id=design.id, num_m_requested_reads=10.5,
    ))
    other = models.FlowCellDesign(name="design-b")
    session.add(other)
    session.flush()
    session.add(models.PoolDesign(
        name="pool-b", cycles_r1=151, cycles_i1=10, cycles_i2=10, cycles_r2=151,
        flow_cell_design_id=other.id, num_m_requested_reads=99.0,
    ))

    assert_hybrids(session, design, models.FlowCellDesign, {
        "num_m_reads": 10.5,
        "r1_cycles": 51,
        "i1_cycles": 8,
        "i2_cycles": 8,
        "r2_cycles": 51,
    })
