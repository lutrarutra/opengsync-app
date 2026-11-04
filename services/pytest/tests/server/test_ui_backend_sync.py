"""The UI's enabled/disabled state of every action matches what the backend allows.

For each scenario (an entity in some status, viewed by its owner, an insider or an admin)
the page and the fragments it lazy-loads are rendered, every action on them is collected
(buttons, workflow tiles and context-menu items) and its endpoint is called:

- a disabled action must be rejected: 400/403/409, or a redirect that flashes a
  warning or error (how some routes refuse),
- an enabled action must be accepted.

GET actions (opening a modal) are called on the rendered scenario. Actions that change
data run against a freshly built copy of the scenario, one copy per action, so they can't
affect each other.

Disagreements the backend is known to have are listed in ``KNOWN_GAPS``. The test also
fails when one of them is fixed, so the list can't go stale.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C
from opengsync_db.core import actions as db_actions

from ..db.create_units import (
    create_experiment, create_group, create_lab_prep, create_library, create_pool, create_project,
    create_sample, create_seq_request,
)
from ._http import delete, get, post_form, put_form, set_cookie_header

REJECTED = {400, 403, 409}
LAZY_TRIGGERS = ("intersect", "load", "revealed")
HX_METHODS = {"hx-get": "GET", "hx-post": "POST", "hx-delete": "DELETE", "hx-put": "PUT"}
MENU_METHODS = {"hxget": "GET", "hxpost": "POST", "hxdelete": "DELETE"}
MAX_FRAGMENT_DEPTH = 2
# not entity actions: signing out would end the session the test is using
SKIPPED_PATHS = ("/htmx/auth/logout",)


# ── Collecting actions ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Action:
    label: str
    method: str
    url: str
    disabled: bool

    @property
    def key(self) -> tuple[str, str, str]:
        """Identifies the action across scenario copies, whose ids differ."""
        return self.label, self.method, re.sub(r"\d+", "{id}", urlsplit(self.url).path)


def _path(url: str) -> str:
    parts = urlsplit(unescape(url))
    return parts.path + (f"?{parts.query}" if parts.query else "")


class _ActionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.actions: list[Action] = []
        self.fragments: list[str] = []
        self._open: list[dict] = []  # actions whose label is still being read

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {name: value or "" for name, value in attrs_list}
        for entry in self._open:
            if entry["tag"] == tag:
                entry["depth"] += 1

        if (menu := attrs.get("data-context-menu")) is not None:
            for item in json.loads(menu)["actions"]:
                if (method := MENU_METHODS.get(item.get("type", ""))) is not None:
                    self.actions.append(Action(item.get("label", item["type"]), method, _path(item["config"]["url"]), bool(item.get("disabled"))))

        hx = next(((name, attrs[name]) for name in HX_METHODS if name in attrs), None)
        trigger = attrs.get("hx-trigger", "")
        if hx is not None and hx[0] == "hx-get" and any(t in trigger for t in LAZY_TRIGGERS):
            self.fragments.append(_path(hx[1]))
            return

        if "data-action-url" in attrs:
            method, url = HX_METHODS[attrs["data-action-method"]], attrs["data-action-url"]
        elif hx is not None and tag in ("button", "a") and trigger in ("", "click"):
            method, url = HX_METHODS[hx[0]], hx[1]
            # only GETs that open a modal are actions; others page, sort or filter
            if method == "GET" and "modal" not in attrs.get("hx-target", "") + attrs.get("data-bs-target", ""):
                return
        else:
            return
        if _path(url).startswith(SKIPPED_PATHS):
            return

        disabled = "disabled" in attrs or attrs.get("aria-disabled") == "true"
        self._open.append(dict(tag=tag, depth=1, text=[], method=method, url=_path(url), disabled=disabled))

    def handle_endtag(self, tag: str) -> None:
        for entry in list(self._open):
            if entry["tag"] == tag:
                entry["depth"] -= 1
                if entry["depth"] == 0:
                    self._open.remove(entry)
                    label = " ".join("".join(entry["text"]).split())
                    self.actions.append(Action(label, entry["method"], entry["url"], entry["disabled"]))

    def handle_data(self, data: str) -> None:
        for entry in self._open:
            entry["text"].append(data)


def _collect(client: TestClient, page: str, token: str) -> list[Action]:
    response = get(client, page, token)
    assert response.status_code == 200, f"{page}: {response.status_code}"

    collected: list[Action] = []
    seen = {page}
    queue = [(response.text, 0)]
    while queue:
        html, depth = queue.pop(0)
        parser = _ActionParser()
        parser.feed(html)
        collected.extend(parser.actions)
        for fragment in parser.fragments:
            if fragment in seen or depth >= MAX_FRAGMENT_DEPTH:
                continue
            seen.add(fragment)
            fragment_response = get(client, fragment, token, htmx=True)
            if fragment_response.status_code == 200:
                queue.append((fragment_response.text, depth + 1))

    unique: dict[tuple, Action] = {}
    for action in collected:
        unique.setdefault((action.key, action.url, action.disabled), action)
    return list(unique.values())


def _call(client: TestClient, action: Action, token: str) -> int:
    """Status code of calling the action; a success that flashes a warning or error counts as 400."""
    if action.method == "GET":
        response = get(client, action.url, token, htmx=True)
    elif action.method == "POST":
        response = post_form(client, action.url, {}, token=token, htmx=True)
    elif action.method == "PUT":
        response = put_form(client, action.url, {}, token=token, htmx=True)
    else:
        response = delete(client, action.url, token, htmx=True)

    flashes = unquote(response.headers.get("HX-Trigger", "") + set_cookie_header(response))
    if response.status_code < 400 and re.search(r'"category":\s*"(warning|error)"', flashes):
        return 400
    return response.status_code


# ── Scenarios ────────────────────────────────────────────────────────────────

@dataclass
class Users:
    owner: models.User
    insider: models.User
    admin: models.User


@dataclass(frozen=True)
class Scenario:
    id: str
    build: Callable[[SyncSession, Users], str]  # returns the page path
    roles: tuple[str, ...] = ("owner", "insider", "admin")


def _set_status(session: SyncSession, entity, status) -> None:
    entity.status = status
    session.save(entity)


def _seq_request(request_status: C.SeqRequestStatus, library_status: C.LibraryStatus):
    def build(session: SyncSession, users: Users) -> str:
        seq_request = create_seq_request(session, users.owner)
        _set_status(session, seq_request, request_status)
        library = create_library(session, users.owner, seq_request)
        _set_status(session, library, library_status)
        sample = create_sample(session, users.owner, create_project(session, users.owner))
        db_actions.link_sample_library(session, sample.id, library.id)
        library.pool_id = create_pool(session, users.owner, seq_request).id
        for email in ("a@example.com", "b@example.com"):
            seq_request.delivery_email_links.append(models.links.SeqRequestDeliveryEmailLink(email=email))
        session.commit()
        return f"/seq_requests/{seq_request.id}"
    return build


def _project(status: C.ProjectStatus):
    def build(session: SyncSession, users: Users) -> str:
        project = create_project(session, users.owner)
        _set_status(session, project, status)
        create_sample(session, users.owner, project)
        session.commit()
        return f"/projects/{project.id}"
    return build


def _empty_project(session: SyncSession, users: Users) -> str:
    project = create_project(session, users.owner)
    session.commit()
    return f"/projects/{project.id}"


def _sample(project_status: C.ProjectStatus, sample_status: C.SampleStatus | None):
    def build(session: SyncSession, users: Users) -> str:
        project = create_project(session, users.owner)
        _set_status(session, project, project_status)
        sample = create_sample(session, users.owner, project)
        sample.status = sample_status
        session.save(sample)
        session.commit()
        return f"/samples/{sample.id}"
    return build


def _library(request_status: C.SeqRequestStatus, library_status: C.LibraryStatus):
    def build(session: SyncSession, users: Users) -> str:
        seq_request = create_seq_request(session, users.owner)
        _set_status(session, seq_request, request_status)
        library = create_library(session, users.owner, seq_request)
        _set_status(session, library, library_status)
        sample = create_sample(session, users.owner, create_project(session, users.owner))
        db_actions.link_sample_library(session, sample.id, library.id)
        session.commit()
        return f"/libraries/{library.id}"
    return build


def _pool(request_status: C.SeqRequestStatus, pool_status: C.PoolStatus, empty: bool = False):
    def build(session: SyncSession, users: Users) -> str:
        seq_request = create_seq_request(session, users.owner)
        _set_status(session, seq_request, request_status)
        pool = create_pool(session, users.owner, seq_request)
        _set_status(session, pool, pool_status)
        if not empty:
            pool.libraries.append(create_library(session, users.owner, seq_request))
        session.commit()
        return f"/pools/{pool.id}"
    return build


def _experiment(status: C.ExperimentStatus):
    def build(session: SyncSession, users: Users) -> str:
        experiment = create_experiment(session, users.insider, C.ExperimentWorkFlow.NOVASEQ_6K_S4_STD)
        _set_status(session, experiment, status)
        seq_request = create_seq_request(session, users.owner)
        _set_status(session, seq_request, C.SeqRequestStatus.ACCEPTED)
        pool = create_pool(session, users.owner, seq_request)
        pool.libraries.append(create_library(session, users.owner, seq_request))
        pool.experiment_id = experiment.id
        session.commit()
        return f"/experiments/{experiment.id}"
    return build


def _lab_prep(status: C.PrepStatus):
    def build(session: SyncSession, users: Users) -> str:
        lab_prep = create_lab_prep(session, users.insider)
        _set_status(session, lab_prep, status)
        session.commit()
        return f"/lab_preps/{lab_prep.id}"
    return build


def _user_page(session: SyncSession, users: Users) -> str:
    return f"/users/{users.owner.id}"


def _group(session: SyncSession, users: Users) -> str:
    group = create_group(session)
    session.add(models.links.UserAffiliation(user_id=users.owner.id, group_id=group.id, affiliation_type=C.AffiliationType.OWNER))
    session.commit()
    return f"/groups/{group.id}"


INTERNAL = ("insider", "admin")

SCENARIOS = [
    Scenario("seq_request-draft", _seq_request(C.SeqRequestStatus.DRAFT, C.LibraryStatus.DRAFT)),
    Scenario("seq_request-submitted", _seq_request(C.SeqRequestStatus.SUBMITTED, C.LibraryStatus.SUBMITTED)),
    Scenario("seq_request-accepted", _seq_request(C.SeqRequestStatus.ACCEPTED, C.LibraryStatus.ACCEPTED)),
    Scenario("seq_request-finished", _seq_request(C.SeqRequestStatus.FINISHED, C.LibraryStatus.SEQUENCED)),
    Scenario("project-draft", _project(C.ProjectStatus.DRAFT)),
    Scenario("project-processing", _project(C.ProjectStatus.PROCESSING)),
    Scenario("project-empty", _empty_project),
    Scenario("sample-draft", _sample(C.ProjectStatus.DRAFT, C.SampleStatus.DRAFT)),
    Scenario("sample-stored", _sample(C.ProjectStatus.PROCESSING, C.SampleStatus.STORED)),
    Scenario("library-draft", _library(C.SeqRequestStatus.DRAFT, C.LibraryStatus.DRAFT)),
    Scenario("library-sequenced", _library(C.SeqRequestStatus.FINISHED, C.LibraryStatus.SEQUENCED)),
    Scenario("pool-draft", _pool(C.SeqRequestStatus.DRAFT, C.PoolStatus.DRAFT)),
    Scenario("pool-accepted", _pool(C.SeqRequestStatus.ACCEPTED, C.PoolStatus.ACCEPTED)),
    Scenario("pool-empty", _pool(C.SeqRequestStatus.DRAFT, C.PoolStatus.DRAFT, empty=True)),
    Scenario("experiment-draft", _experiment(C.ExperimentStatus.DRAFT), INTERNAL),
    Scenario("experiment-loaded", _experiment(C.ExperimentStatus.LOADED), INTERNAL),
    Scenario("experiment-sequencing", _experiment(C.ExperimentStatus.SEQUENCING), INTERNAL),
    Scenario("lab_prep-preparing", _lab_prep(C.PrepStatus.PREPARING), INTERNAL),
    Scenario("lab_prep-completed", _lab_prep(C.PrepStatus.COMPLETED), INTERNAL),
    Scenario("user", _user_page),
    Scenario("group", _group),
]


# ── Known disagreements ──────────────────────────────────────────────────────

# Checklist steps the UI disables until earlier steps are done; the backend doesn't check the order.
PREREQUISITE = "UI-only prerequisite: backend does not check earlier checklist steps"
# Status rules only the UI enforces; the backend only checks the role.
NO_STATUS_CHECK = "backend has no status check"

_EXPERIMENT_PREREQUISITES = {
    ("*", "Begin", "GET", "/htmx/experiments/{id}/load-flow-cell/combined"): PREREQUISITE,
    ("*", "Begin", "GET", "/htmx/workflows/ba-report/begin"): PREREQUISITE,
    ("*", "Begin", "GET", "/htmx/workflows/index-check/begin"): PREREQUISITE,
    ("*", "Begin", "GET", "/htmx/workflows/qubit-measure/begin"): PREREQUISITE,
}
_LAB_PREP_PREREQUISITES = {
    ("*", "Begin", "GET", "/htmx/actions/reject-samples/{id}"): PREREQUISITE,
    ("*", "Begin", "GET", "/htmx/actions/sample-pooling/{id}"): PREREQUISITE,
    ("*", "Begin", "GET", "/htmx/workflows/mux-prep/begin"): PREREQUISITE,
    ("*", "Complete Prep", "POST", "/htmx/lab_preps/{id}/complete"): "complete_lab_prep checks neither the checklist nor the status",
}
_STORE_SAMPLES = {
    (role, "Store Samples Store samples received from customers.", "GET", "/htmx/actions/store-samples-action"): "StoreSamplesAction has no ACCEPTED check"
    for role in ("insider", "admin")
}

# (scenario, role or "*", label, method, path pattern) -> why the UI and backend disagree
KNOWN_GAPS: dict[tuple[str, str, str, str, str], str] = {
    **{("seq_request-draft", *key): why for key, why in _STORE_SAMPLES.items()},
    ("seq_request-draft", "owner", "Re-Sequence Library", "POST", "/htmx/seq_requests/{id}/reseq-library/{id}"): "reseq_library lets customers re-sequence on draft requests",
    ("seq_request-draft", "owner", "Submit", "GET", "/htmx/seq_requests/{id}/submit"): "UI-only prerequisite: the submit form opens without samples or an auth form",
    **{(scenario, *key): why for scenario in ("seq_request-submitted", "seq_request-finished") for key, why in _STORE_SAMPLES.items()},
    ("library-sequenced", "owner", "Edit Properties", "GET", "/htmx/actions/edit-library-properties-action"): "backend opens a read-only view; the UI disables the button instead",
    **{(scenario, *key): why for scenario in ("experiment-draft", "experiment-loaded", "experiment-sequencing") for key, why in _EXPERIMENT_PREREQUISITES.items()},
    ("experiment-loaded", "insider", "Remove Pool", "DELETE", "/htmx/experiments/{id}/remove-pool/{id}"): NO_STATUS_CHECK,
    ("experiment-sequencing", "insider", "Remove Pool", "DELETE", "/htmx/experiments/{id}/remove-pool/{id}"): NO_STATUS_CHECK,
    ("experiment-sequencing", "insider", "Begin", "GET", "/htmx/experiments/{id}"): NO_STATUS_CHECK + " (DilutePoolsAction)",
    ("experiment-sequencing", "insider", "Begin", "GET", "/htmx/experiments/{id}/lane-pools/combined"): NO_STATUS_CHECK,
    ("experiment-sequencing", "insider", "Begin", "GET", "/htmx/experiments/{id}/select-pools"): NO_STATUS_CHECK,
    **{(scenario, *key): why for scenario in ("lab_prep-preparing", "lab_prep-completed") for key, why in _LAB_PREP_PREREQUISITES.items()},
}


def _known_gaps(scenario: Scenario) -> set[tuple]:
    return {
        (scenario_id, role, *key)
        for (scenario_id, roles, *key) in KNOWN_GAPS
        if scenario_id == scenario.id
        for role in (scenario.roles if roles == "*" else (roles,))
    }


# ── Test ─────────────────────────────────────────────────────────────────────

def _mismatch(action: Action, status: int) -> str | None:
    if status in (401, 404, 405, 422) or status >= 500:
        return f"broken ({status})"
    if action.disabled and status < 400:
        return f"disabled in UI but backend allows it ({status})"
    if not action.disabled and status in REJECTED:
        return f"enabled in UI but backend rejects it ({status})"
    if status >= 400 and status not in REJECTED:
        return f"unexpected status {status}"
    return None


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_ui_disabled_state_matches_backend(
    client: TestClient, session: SyncSession, user, insider, admin,
    user_token: str, insider_token: str, admin_token: str, scenario: Scenario,
):
    users = Users(owner=user, insider=insider, admin=admin)
    tokens = {"owner": user_token, "insider": insider_token, "admin": admin_token}

    found: dict[tuple, str] = {}
    for role in scenario.roles:
        token = tokens[role]
        page = scenario.build(session, users)
        actions = _collect(client, page, token)
        assert actions, f"no actions found on {page}"

        for action in actions:
            if action.method == "GET":
                status = _call(client, action, token)
            else:
                # each data-changing action gets its own copy of the scenario
                fresh = [a for a in _collect(client, scenario.build(session, users), token) if a.key == action.key and a.disabled == action.disabled]
                assert fresh, f"{action} not found again on a fresh copy of the scenario"
                status = _call(client, fresh[0], token)

            if (problem := _mismatch(action, status)) is not None:
                found[(scenario.id, role, *action.key)] = f"{problem}: {action.url}"

    expected = _known_gaps(scenario)
    new = {key: found[key] for key in found.keys() - expected}
    fixed = expected - found.keys()
    assert not new and not fixed, (
        "UI and backend disagree:\n" + "\n".join(f"  {key}: {why}" for key, why in sorted(new.items()))
        + "\nNo longer disagree (remove from KNOWN_GAPS):\n" + "\n".join(f"  {key}" for key in sorted(fixed))
    )
