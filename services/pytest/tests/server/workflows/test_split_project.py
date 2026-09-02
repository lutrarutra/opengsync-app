import json
import uuid

from opengsync_db import SyncSession, categories as C, queries as Q

from ...db.create_units import create_project, create_sample
from .._http import OpenGSyncTestClient, assert_form_invalid, assert_htmx_redirect, get, post_form


def test_split_project_workflow_is_insider_only(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
    user_token,
):
    source = create_project(session, user)
    session.commit()
    path = "/htmx/workflows/split-project/begin"

    assert get(client, path, user_token, params={"project_id": source.id}).status_code == 403
    assert get(client, path, insider_token, params={"project_id": source.id}).status_code == 200


def test_split_project_workflow_moves_samples_to_existing_project(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    source = create_project(session, user)
    destination = create_project(session, user)
    moved = create_sample(session, user, source)
    retained = create_sample(session, user, source)
    session.commit()

    workflow_uuid = str(uuid.uuid4())
    params = {"project_id": source.id, "uuid": workflow_uuid}
    prefix = "/htmx/workflows/split-project"

    response = get(client, f"{prefix}/begin", insider_token, params=params)
    assert response.status_code == 200

    response = post_form(
        client,
        f"{prefix}/select-samples",
        {"selected_sample_ids": json.dumps([moved.id])},
        token=insider_token,
        params=params,
    )
    assert response.status_code == 200
    assert "Select Destination" in response.text

    response = post_form(
        client,
        f"{prefix}/project-select",
        {"existing_project": str(destination.id)},
        token=insider_token,
        params=params,
    )
    assert response.status_code == 200
    assert "Destination Project Status" in response.text

    response = post_form(
        client,
        f"{prefix}/confirm-split",
        {"destination_status": str(C.ProjectStatus.PROCESSING.id)},
        token=insider_token,
        params=params,
    )
    assert_htmx_redirect(response, f"/projects/{destination.id}")

    session.expire_all()
    assert session.first(Q.sample.select(id=moved.id)).project_id == destination.id
    assert session.first(Q.sample.select(id=retained.id)).project_id == source.id


def test_split_project_requires_samples_and_rejects_forged_sample_ids(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    source = create_project(session, user)
    other = create_project(session, user)
    other_sample = create_sample(session, user, other)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}
    prefix = "/htmx/workflows/split-project"

    get(client, f"{prefix}/begin", insider_token, params=params)
    assert_form_invalid(post_form(
        client,
        f"{prefix}/select-samples",
        {"selected_sample_ids": "[]"},
        token=insider_token,
        params=params,
    ), "Please select at least one item.")
    assert_form_invalid(post_form(
        client,
        f"{prefix}/select-samples",
        {"selected_sample_ids": json.dumps([other_sample.id])},
        token=insider_token,
        params=params,
    ), "source project")


def test_split_project_creates_destination_with_source_owner_and_group(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    source = create_project(session, user)
    group = session.save(Q.group.create(name="Split Group", type=C.GroupType.COLLABORATION), flush=True)
    source.group_id = group.id
    source_sample = create_sample(session, user, source)
    session.commit()

    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}
    prefix = "/htmx/workflows/split-project"

    get(client, f"{prefix}/begin", insider_token, params=params)
    assert post_form(
        client,
        f"{prefix}/select-samples",
        {"selected_sample_ids": json.dumps([source_sample.id])},
        token=insider_token,
        params=params,
    ).status_code == 200
    assert post_form(
        client,
        f"{prefix}/project-select",
        {
            "new_project": "A New Split Project",
            "project_description": "Created by the project split workflow.",
        },
        token=insider_token,
        params=params,
    ).status_code == 200

    response = post_form(
        client,
        f"{prefix}/confirm-split",
        {"destination_status": str(C.ProjectStatus.DELIVERED.id)},
        token=insider_token,
        params=params,
    )
    assert response.status_code == 204

    session.expire_all()
    destination = session.first(Q.project.select(title="A New Split Project", owner_id=user.id))
    assert destination is not None
    assert destination.group_id == group.id
    assert destination.status == C.ProjectStatus.DELIVERED
    assert destination.assignees == []
    assert session.first(Q.sample.select(id=source_sample.id)).project_id == destination.id
