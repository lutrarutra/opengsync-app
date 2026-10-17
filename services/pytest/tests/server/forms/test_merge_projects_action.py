"""MergeProjectsAction: merge a source project's samples into a destination project.

Expected behaviour is legacy ``merge_projects_workflow`` + ``MergeProjectsForm``
+ ``ActionsBP.merge_projects`` (a transaction):

- samples whose name is not in the destination move to it;
- a same-name sample is merged into the destination sample: its library links
  move over, missing attributes are copied, measurements the destination lacks
  are filled in, the more advanced status wins; then the source sample is deleted;
- source assignees are added to the destination (no duplicates);
- rejected before anything changes: same project twice, missing or unknown
  project, same-name samples with attributes of a different type or value;
- a failure during the merge leaves both projects untouched.

Insider-only access is covered in ``server/test_action_access.py``.
"""

import importlib
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, actions, models, queries as Q, categories as C


from ...db.create_units import create_library, create_project, create_sample, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch

PATH = "/htmx/projects/merge-projects"
merge_module = importlib.import_module("server.forms.actions.MergeProjectsAction")  # the package re-exports the class under the same name


def _payload(dst: models.Project | None, src: models.Project | None) -> dict[str, str]:
    return {
        "project_dst": str(dst.id) if dst else "",
        "project_src": str(src.id) if src else "",
    }


def _sample(session: SyncSession, user: models.User, project: models.Project, name: str, **fields) -> models.Sample:
    sample = create_sample(session, user, project)
    sample.name = name
    for key, value in fields.items():
        setattr(sample, key, value)
    session.save(sample, flush=True)
    return sample


def _link_library(session: SyncSession, user: models.User, sample: models.Sample) -> models.Library:
    library = create_library(session, user, create_seq_request(session, user))
    actions.link_sample_library(session, sample.id, library.id)
    return library


def _samples(session: SyncSession, project: models.Project) -> dict[str, models.Sample]:
    session.expire_all()
    return {s.name: s for s in session.get_all(Q.sample.select(project_id=project.id), limit=None)}


def _sample_ids_of_library(session: SyncSession, library: models.Library) -> set[int]:
    session.expire_all()
    return {link.sample_id for link in session.get(models.Library, library.id).sample_links}


@pytest.fixture
def projects(session: SyncSession, user: models.User) -> tuple[models.Project, models.Project]:
    dst, src = create_project(session, user), create_project(session, user)
    session.commit()
    return dst, src


# ── Render ──────────────────────────────────────────────────────────────────


def test_render(client: TestClient, insider_token: str):
    response = get(client, PATH, insider_token)

    assert response.status_code == 200
    assert 'name="project_dst"' in response.text
    assert 'name="project_src"' in response.text
    assert 'name="csrf_token"' in response.text


# ── Merging ─────────────────────────────────────────────────────────────────


def test_unique_samples_move_to_destination(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    _sample(session, user, dst, "kept")
    _sample(session, user, src, "moved-1")
    _sample(session, user, src, "moved-2")
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{dst.id}")
    assert_flash(response, "Projects merged successfully!", category="success")
    assert set(_samples(session, dst)) == {"kept", "moved-1", "moved-2"}
    assert _samples(session, src) == {}


def test_source_project_is_left_empty_not_deleted(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    _sample(session, user, src, "moved")
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    session.expire_all()
    assert session.get(models.Project, src.id) is not None


def test_same_name_sample_is_merged_into_destination_sample(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    dst_sample = _sample(session, user, dst, "shared")
    src_sample = _sample(session, user, src, "shared")
    library = _link_library(session, user, src_sample)
    src_sample_id = src_sample.id
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    session.expire_all()
    assert session.get(models.Sample, src_sample_id) is None
    assert set(_samples(session, dst)) == {"shared"}
    assert _sample_ids_of_library(session, library) == {dst_sample.id}


def test_same_name_sample_fills_in_missing_measurements(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    stored = datetime(2026, 1, 2, 3, 4, 5)
    _sample(session, user, dst, "shared", qubit_concentration=1.5)
    _sample(session, user, src, "shared", qubit_concentration=9.9, avg_fragment_size=420, timestamp_stored_utc=stored)
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    merged = _samples(session, dst)["shared"]
    assert merged.qubit_concentration == 1.5  # destination value wins
    assert merged.avg_fragment_size == 420
    assert merged.timestamp_stored_utc.replace(tzinfo=None) == stored


def test_same_name_sample_keeps_the_more_advanced_status(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    _sample(session, user, dst, "shared", status=C.SampleStatus.WAITING_DELIVERY)
    _sample(session, user, src, "shared", status=C.SampleStatus.STORED)
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    assert _samples(session, dst)["shared"].status == C.SampleStatus.STORED


def test_same_name_sample_without_status_merges(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    """Destination sample has a status, source sample has none (the default for new samples)."""
    dst, src = projects
    _sample(session, user, dst, "shared", status=C.SampleStatus.STORED)
    _sample(session, user, src, "shared")
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=insider_token)

    assert response.status_code == 204
    assert _samples(session, dst)["shared"].status == C.SampleStatus.STORED


@pytest.mark.parametrize("with_library", [True, False], ids=["with-library", "without-library"])
def test_same_name_sample_copies_missing_attributes(
    client: TestClient, session: SyncSession, user, insider_token: str, projects, with_library: bool,
):
    dst, src = projects
    dst_sample = _sample(session, user, dst, "shared")
    dst_sample.set_attribute("sex", "female", type=C.AttributeType.SEX)
    src_sample = _sample(session, user, src, "shared")
    src_sample.set_attribute("sex", "female", type=C.AttributeType.SEX)
    src_sample.set_attribute("tissue", "liver", type=C.AttributeType.TISSUE)
    if with_library:
        _link_library(session, user, src_sample)
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    merged = _samples(session, dst)["shared"]
    assert merged.get_attribute("sex").value == "female"
    assert merged.get_attribute("tissue") is not None, "source-only attribute was dropped"
    assert merged.get_attribute("tissue").value == "liver"


def test_assignees_are_merged_without_duplicates(
    client: TestClient, session: SyncSession, user, insider, admin, insider_token: str, projects,
):
    dst, src = projects
    dst.assignees.append(insider)
    src.assignees.extend([insider, admin])
    session.commit()

    post_form(client, PATH, _payload(dst, src), token=insider_token)

    session.expire_all()
    assert sorted(u.id for u in session.get(models.Project, dst.id).assignees) == sorted([insider.id, admin.id])


def test_empty_source_project_changes_nothing(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    _sample(session, user, dst, "kept")
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=insider_token)

    assert_htmx_redirect(response, f"/projects/{dst.id}")
    assert set(_samples(session, dst)) == {"kept"}


# ── Rejected before anything changes ────────────────────────────────────────


@pytest.mark.parametrize("conflict,src_type,src_value", [
    ("types", C.AttributeType.CUSTOM, "female"),
    ("values", C.AttributeType.SEX, "male"),
])
def test_conflicting_same_name_attributes_are_rejected(
    client: TestClient, session: SyncSession, user, insider_token: str, projects, conflict, src_type, src_value,
):
    dst, src = projects
    dst_sample = _sample(session, user, dst, "shared")
    dst_sample.set_attribute("sex", "female", type=C.AttributeType.SEX)
    src_sample = _sample(session, user, src, "shared")
    src_sample.set_attribute("sex", src_value, type=src_type)
    _sample(session, user, src, "unique")
    session.commit()

    response = post_form(client, PATH, _payload(dst, src), token=insider_token)

    assert_form_invalid(response, contains=f"Sample name conflict for sample 'shared' with incompatible attribute {conflict}.")
    assert set(_samples(session, dst)) == {"shared"}
    assert set(_samples(session, src)) == {"shared", "unique"}


def test_same_project_is_rejected(client: TestClient, session: SyncSession, user, insider_token: str, projects):
    dst, _ = projects

    response = post_form(client, PATH, _payload(dst, dst), token=insider_token)

    assert_form_invalid(response, contains="Source and destination projects cannot be the same.")


@pytest.mark.parametrize("missing", ["dst", "src"])
def test_missing_project_is_rejected(client: TestClient, insider_token: str, projects, missing: str):
    dst, src = projects
    payload = _payload(None if missing == "dst" else dst, None if missing == "src" else src)

    response = post_form(client, PATH, payload, token=insider_token)

    assert_form_invalid(response)


@pytest.mark.parametrize("unknown", ["dst", "src"])
def test_unknown_project_is_rejected(
    client: TestClient, session: SyncSession, user, insider_token: str, projects, unknown: str,
):
    dst, src = projects
    _sample(session, user, src, "stays")
    session.commit()
    payload = _payload(dst, src)
    payload[f"project_{unknown}"] = "999999"

    response = post_form(client, PATH, payload, token=insider_token)

    assert_form_invalid(response, contains="Selected project not found.")
    assert set(_samples(session, src)) == {"stays"}


def test_non_numeric_project_id_is_rejected(client: TestClient, insider_token: str, projects):
    dst, src = projects
    payload = _payload(dst, src)
    payload["project_src"] = "not-a-number"

    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = post_form(lenient, PATH, payload, token=insider_token)

    assert_form_invalid(response)


def test_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, user, insider_token: str, projects,
):
    dst, src = projects
    _sample(session, user, src, "stays")
    session.commit()

    response = post_form_csrf_mismatch(client, PATH, _payload(dst, src), token=insider_token)

    assert_form_invalid(response)
    assert set(_samples(session, src)) == {"stays"}


# ── Rollback ────────────────────────────────────────────────────────────────


def test_failure_during_merge_rolls_everything_back(
    client: TestClient, session: SyncSession, user, insider_token: str, projects, monkeypatch,
):
    """Legacy ran the merge in a transaction; a failure after changes were made must undo them."""
    dst, src = projects
    _sample(session, user, src, "moved")
    same_dst_id = _sample(session, user, dst, "shared").id
    same_src_id = _sample(session, user, src, "shared").id
    session.commit()

    real_merge = merge_module.actions.merge_projects

    def merge_then_fail(*args, **kwargs):
        real_merge(*args, **kwargs)
        raise RuntimeError("simulated failure after merging")

    monkeypatch.setattr(merge_module.actions, "merge_projects", merge_then_fail)
    lenient = TestClient(client.app, raise_server_exceptions=False)

    response = post_form(lenient, PATH, _payload(dst, src), token=insider_token)

    assert response.status_code == 500
    assert set(_samples(session, src)) == {"moved", "shared"}
    assert set(_samples(session, dst)) == {"shared"}
    session.expire_all()
    assert session.get(models.Sample, same_src_id) is not None
    assert session.get(models.Sample, same_dst_id) is not None
