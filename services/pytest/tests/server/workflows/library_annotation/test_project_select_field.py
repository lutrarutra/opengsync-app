"""Project selection with one SearchableInputField(allow_new=True): rendering of the selection and the description."""

import html
import re

from opengsync_db import SyncSession, categories as C

from ....db.create_units import create_project, create_seq_request
from ..._http import get
from ._workflow import AnnotationWorkflow


def _description_container(text: str) -> str:
    match = re.search(r'<div data-search-select-new-only="project"[^>]*>', text)
    assert match is not None, "description is not wrapped in the new-only container"
    return match.group(0)


def _start(client, session: SyncSession, user, user_token) -> AnnotationWorkflow:
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    wf = AnnotationWorkflow(client, user_token, seq_request.id)
    wf.begin()
    return wf


def test_step_renders_one_project_field_with_hidden_description(client, session: SyncSession, user, user_token):
    wf = _start(client, session, user, user_token)

    response = get(client, f"{wf.prefix}/begin", user_token, params=wf.params)

    assert 'name="project" value=""' in response.text
    assert 'name="project-text" value=""' in response.text
    assert "data-allow-new" in response.text and 'data-new-label="Create New Project"' in response.text
    assert 'name="new_project"' not in response.text and 'name="existing_project"' not in response.text
    assert 'class="d-none"' in _description_container(response.text)


def test_invalid_new_title_rerenders_as_new_with_description(client, session: SyncSession, user, user_token):
    wf = _start(client, session, user, user_token)

    response = wf.post("project-select", {"project": "new", "project-text": "Short", "project_description": "kept"}, status=202)

    assert 'name="project" value="new"' in response.text
    assert 'name="project-text" value="Short"' in response.text
    assert "is-new" in response.text
    assert "Project should have at least 6 characters." in response.text
    assert "d-none" not in _description_container(response.text)
    assert ">kept</textarea>" in response.text
    # Only shown for new projects, where it is required (the field itself is optional)
    assert 'placeholder="Required: describe the new project' in response.text


def test_existing_project_with_description_is_rejected_and_hides_description(client, session: SyncSession, user, user_token):
    project = create_project(session, user)
    session.commit()
    wf = _start(client, session, user, user_token)

    response = wf.post("project-select", {
        "project": str(project.id), "project-text": project.title, "project_description": "not needed",
    }, status=202)

    assert "Project description is not needed if using existing project." in response.text
    assert f'name="project" value="{project.id}"' in response.text
    assert f'name="project-text" value="{html.escape(project.title)}"' in response.text
    assert 'class="d-none"' in _description_container(response.text)


def test_back_restores_existing_project_with_its_title(client, session: SyncSession, user, user_token):
    project = create_project(session, user)
    session.commit()
    wf = _start(client, session, user, user_token)
    wf.post("project-select", {"project": str(project.id)}, next_step="sample-annotation")

    back = get(client, f"{wf.prefix}/project-select", user_token, params=wf.params)

    assert back.status_code == 200
    assert f'name="project" value="{project.id}"' in back.text
    assert f'name="project-text" value="{html.escape(project.title)}"' in back.text
    assert 'class="d-none"' in _description_container(back.text)


def test_back_restores_new_project_title_and_description(client, session: SyncSession, user, user_token):
    wf = _start(client, session, user, user_token)
    wf.project("Brand New Project", description="described before")

    back = get(client, f"{wf.prefix}/project-select", user_token, params=wf.params)

    assert 'name="project" value="new"' in back.text
    assert 'name="project-text" value="Brand New Project"' in back.text
    assert "d-none" not in _description_container(back.text)
    assert "described before" in back.text


def test_digit_only_new_title_creates_a_new_project(client, session: SyncSession, user, user_token):
    wf = _start(client, session, user, user_token)

    wf.post("project-select", {"project": "new", "project-text": "20261016", "project_description": "d"}, next_step="sample-annotation")
