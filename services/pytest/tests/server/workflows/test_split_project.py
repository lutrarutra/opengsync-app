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
        {"project": str(destination.id)},
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
            "project": "new", "project-text": "A New Split Project",
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


PREFIX = "/htmx/workflows/split-project"


def _to_confirm(client, token, params, sample_ids, destination: dict[str, str]):
    get(client, f"{PREFIX}/begin", token, params=params)
    assert post_form(
        client, f"{PREFIX}/select-samples", {"selected_sample_ids": json.dumps(sample_ids)}, token=token, params=params,
    ).status_code == 200
    response = post_form(client, f"{PREFIX}/project-select", destination, token=token, params=params)
    assert response.status_code == 200, response.text
    return response


def test_split_project_back_navigation_keeps_choices_and_can_change_destination(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    source = create_project(session, user)
    destination = create_project(session, user)
    sample = create_sample(session, user, source)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}

    confirm = _to_confirm(client, insider_token, params, [sample.id], {
        "project": "new", "project-text": "Split Back Project", "project_description": "Chosen first, then replaced.",
    })
    assert "project-select" in confirm.text  # back link to the destination step

    back = get(client, f"{PREFIX}/project-select", insider_token, params=params)
    assert back.status_code == 200
    assert "Split Back Project" in back.text and "Chosen first, then replaced." in back.text

    back = get(client, f"{PREFIX}/select-samples", insider_token, params=params)
    assert back.status_code == 200
    assert str(sample.id) in back.text

    # Choose an existing project instead and finish
    assert post_form(
        client, f"{PREFIX}/project-select", {"project": str(destination.id)}, token=insider_token, params=params,
    ).status_code == 200
    response = post_form(
        client, f"{PREFIX}/confirm-split", {"destination_status": str(C.ProjectStatus.DRAFT.id)}, token=insider_token, params=params,
    )

    assert_htmx_redirect(response, f"/projects/{destination.id}")
    session.expire_all()
    assert session.first(Q.sample.select(id=sample.id)).project_id == destination.id
    assert session.first(Q.project.select(title="Split Back Project", owner_id=user.id)) is None


def test_split_project_owner_without_insider_role_is_denied_on_every_step(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    user_token,
):
    """Insider-only even for the source project's owner."""
    source = create_project(session, user)
    destination = create_project(session, user)
    sample = create_sample(session, user, source)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}

    assert post_form(client, f"{PREFIX}/select-samples", {"selected_sample_ids": json.dumps([sample.id])}, token=user_token, params=params).status_code == 403
    assert post_form(client, f"{PREFIX}/project-select", {"project": str(destination.id)}, token=user_token, params=params).status_code == 403
    assert post_form(client, f"{PREFIX}/confirm-split", {"destination_status": str(C.ProjectStatus.DRAFT.id)}, token=user_token, params=params).status_code == 403
    for path in ("select-samples", "project-select"):
        assert get(client, f"{PREFIX}/{path}", user_token, params=params).status_code == 403

    session.expire_all()
    assert session.first(Q.sample.select(id=sample.id)).project_id == source.id


def test_split_project_unknown_source_is_404(client: OpenGSyncTestClient, insider_token):
    assert get(client, f"{PREFIX}/begin", insider_token, params={"project_id": 999999}).status_code == 404


def test_split_project_failure_after_creating_destination_rolls_back(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    """The split fails after the new destination was flushed; the project must not be kept."""
    source = create_project(session, user)
    sample = create_sample(session, user, source)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}
    _to_confirm(client, insider_token, params, [sample.id, sample.id], {
        "project": "new", "project-text": "Split Rollback Project", "project_description": "Must not survive the failed split.",
    })

    response = post_form(
        client, f"{PREFIX}/confirm-split", {"destination_status": str(C.ProjectStatus.DRAFT.id)}, token=insider_token, params=params,
    )

    assert_form_invalid(response, "A sample may only be selected once.")
    session.expire_all()
    assert session.first(Q.project.select(title="Split Rollback Project", owner_id=user.id)) is None
    assert session.first(Q.sample.select(id=sample.id)).project_id == source.id


def test_split_project_confirm_without_workflow_state_is_rejected(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    source = create_project(session, user)
    sample = create_sample(session, user, source)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}

    response = post_form(
        client, f"{PREFIX}/confirm-split", {"destination_status": str(C.ProjectStatus.DRAFT.id)}, token=insider_token, params=params,
    )

    assert_form_invalid(response, "incomplete")
    session.expire_all()
    assert session.first(Q.sample.select(id=sample.id)).project_id == source.id


def test_split_project_confirm_twice_creates_one_project(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token,
):
    """A repeated confirm (double click, browser retry) finds the state cleared and creates nothing."""
    source = create_project(session, user)
    sample = create_sample(session, user, source)
    session.commit()
    params = {"project_id": source.id, "uuid": str(uuid.uuid4())}
    _to_confirm(client, insider_token, params, [sample.id], {"project": "new", "project-text": "Split Once", "project_description": "x"})
    payload = {"destination_status": str(C.ProjectStatus.DRAFT.id)}

    assert post_form(client, f"{PREFIX}/confirm-split", payload, token=insider_token, params=params).status_code == 204
    assert_form_invalid(post_form(client, f"{PREFIX}/confirm-split", payload, token=insider_token, params=params), "incomplete")

    session.expire_all()
    assert len(session.get_all(Q.project.select(title="Split Once"), limit=None)) == 1
