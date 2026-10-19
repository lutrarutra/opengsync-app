"""Regression tests for findings of the 2026-10 security review.

High severity:

1. Template injection in GenerateSequencerLoadingChecklistAction (insider → RCE).
2. Cross-customer object references: workflow selections, ``reseq-library`` and
   EditLibraryPropertiesAction accepted ids outside the scope the access check covered.
3. Stored XSS from uploads: unsanitised markdown rendering, HTML/SVG served inline from the
   app origin, upload extension/size limits not enforced server-side.
4. API tokens stored (and listed to insiders) in plaintext.

Medium severity:
5. Email links (registration, password reset, shares) built from the client-controlled Host header.
6. Missing permission checks: group ownership takeover by managers, seq requests filed into
   foreign groups, library feature tables, comments on insider-only threads. (ProtocolForm and
   SampleForm are covered in their own test files.)
7. The server started, and signed and verified tokens, with an empty SECRET_KEY.
"""

import hashlib
import importlib
import json
import os
import uuid as uuid_mod
from pathlib import Path
from urllib.parse import unquote

import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ..db.create_units import (
    create_experiment, create_feature, create_group, create_lab_prep, create_library, create_pool,
    create_seq_request,
)
from ._http import CSRF, assert_form_invalid, cookie_header, assert_htmx_redirect, get, post_form, spreadsheet_payload


# ── 1. Template injection ────────────────────────────────────────────────────

CHECKLIST_WORKFLOW = C.ExperimentWorkFlow.NOVASEQ_X_1B_XP  # 2 lanes, novaseq_x.md
SSTI_PAYLOAD = "{{ cycler.__init__.__globals__.os.popen('echo pwned').read() }}"


def _checklist_path(experiment_id: int) -> str:
    return f"/htmx/experiments/{experiment_id}/sequencer-loading-checklist"


def _checklist_payload(param_label: str = "NaOH") -> dict[str, str]:
    params = [
        (param_label, "naoh", "8.5"),
        ("Preload", "preload", "127.5"),
        ("Pool Volume", "pool_volume", "34"),
        ("Phi X (Lane 1)", "phi_x_lane_1", "2"),
        ("Phi X (Lane 2)", "phi_x_lane_2", "3"),
    ]
    data: dict[str, str] = {}
    for i, (label, var_name, value) in enumerate(params):
        data[f"parameters-{i}-param_label"] = label
        data[f"parameters-{i}-param_value"] = value
        data[f"parameters-{i}-var_name"] = var_name
    return data


def _checklist_content(session: SyncSession, experiment: models.Experiment) -> str:
    session.expire_all()
    file = session.get_one(sa.select(models.MediaFile).where(
        models.MediaFile.experiment_id == experiment.id,
        models.MediaFile.type == C.MediaFileType.SEQUENCER_LOADING_CHECKLIST,
    ))
    return (Path(config.settings.app_config.media_folder) / file.path).read_text()


def test_checklist_posted_label_is_not_evaluated_as_template(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = create_experiment(session, insider, CHECKLIST_WORKFLOW)
    session.commit()

    response = post_form(client, _checklist_path(experiment.id), _checklist_payload(SSTI_PAYLOAD), token=insider_token)

    assert_htmx_redirect(response, f"/experiments/{experiment.id}")
    content = _checklist_content(session, experiment)
    assert SSTI_PAYLOAD in content
    assert "pwned" not in content.replace(SSTI_PAYLOAD, "")


def test_checklist_experiment_and_operator_names_are_not_evaluated(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    experiment = create_experiment(session, insider, CHECKLIST_WORKFLOW)
    experiment.name = "{{ 7 * 191 }}"
    insider.first_name = "{{ 7 * 193 }}"
    session.commit()

    response = post_form(client, _checklist_path(experiment.id), _checklist_payload(), token=insider_token)

    assert_htmx_redirect(response)
    content = _checklist_content(session, experiment)
    assert "# Experiment {{ 7 * 191 }}" in content
    assert "{{ 7 * 193 }}" in content
    assert "1337" not in content and "1351" not in content


def test_checklist_template_body_is_sandboxed(
    client: TestClient, session: SyncSession, insider, insider_token: str, monkeypatch: pytest.MonkeyPatch,
):
    """Even the facility template cannot reach Python internals."""
    # ``server.forms.actions`` re-exports the class under the module's name.
    action_module = importlib.import_module("server.forms.actions.GenerateSequencerLoadingChecklistAction")

    params, _ = action_module.parse_markdown_template(
        (Path(config.settings.app_config.static_folder) / "resources" / "templates" / "seq_loading" / "novaseq_x.md").read_text()
    )
    monkeypatch.setattr(
        action_module, "parse_markdown_template",
        lambda raw_md: (params, "{{ ''.__class__.__mro__[1].__subclasses__() }}"),
    )
    experiment = create_experiment(session, insider, CHECKLIST_WORKFLOW)
    session.commit()

    lenient = TestClient(client.app, raise_server_exceptions=False)
    response = post_form(lenient, _checklist_path(experiment.id), _checklist_payload(), token=insider_token)

    assert response.status_code == 500
    session.expire_all()
    assert session.first(sa.select(models.MediaFile).where(models.MediaFile.experiment_id == experiment.id)) is None


# ── 2. Cross-customer object references ─────────────────────────────────────


@pytest.fixture
def victim_request(session: SyncSession, user_2) -> models.SeqRequest:
    seq_request = create_seq_request(session, user_2)
    session.commit()
    return seq_request


@pytest.fixture
def own_request(session: SyncSession, user) -> models.SeqRequest:
    seq_request = create_seq_request(session, user)
    session.commit()
    return seq_request


def _begin_workflow(client: TestClient, prefix: str, token: str, seq_request_id: int) -> dict:
    params = {"seq_request_id": seq_request_id, "uuid": str(uuid_mod.uuid4())}
    assert get(client, f"{prefix}/begin", token, params=params, htmx=True).status_code == 200
    return params


def test_merge_pools_rejects_pools_of_another_request(
    client: TestClient, session: SyncSession, user, user_token: str, own_request, victim_request, user_2,
):
    own_pool = create_pool(session, user, own_request)
    victim_pools = [create_pool(session, user_2, victim_request) for _ in range(2)]
    session.commit()
    prefix = "/htmx/workflows/merge-pools"
    params = _begin_workflow(client, prefix, user_token, own_request.id)

    response = post_form(
        client, f"{prefix}/select-samples",
        {"selected_pool_ids": json.dumps([own_pool.id, *[p.id for p in victim_pools]])},
        token=user_token, params=params,
    )

    assert response.status_code == 404
    for pool in victim_pools:
        assert pool.name not in response.text


def test_merge_pools_accepts_pools_of_own_request(
    client: TestClient, session: SyncSession, user, user_token: str, own_request,
):
    pools = [create_pool(session, user, own_request) for _ in range(2)]
    for pool in pools:
        create_library(session, user, own_request).pool_id = pool.id
    session.commit()
    prefix = "/htmx/workflows/merge-pools"
    params = _begin_workflow(client, prefix, user_token, own_request.id)

    response = post_form(
        client, f"{prefix}/select-samples",
        {"selected_pool_ids": json.dumps([p.id for p in pools])},
        token=user_token, params=params,
    )

    assert response.status_code == 200
    for pool in pools:
        assert pool.name in response.text


def test_reindex_rejects_libraries_of_another_request(
    client: TestClient, session: SyncSession, user_token: str, own_request, victim_request, user_2,
):
    victim_library = create_library(session, user_2, victim_request)
    session.commit()
    prefix = "/htmx/workflows/reindex"
    params = _begin_workflow(client, prefix, user_token, own_request.id)

    response = post_form(
        client, f"{prefix}/select-samples",
        {"selected_library_ids": json.dumps([victim_library.id])},
        token=user_token, params=params,
    )

    assert response.status_code == 404
    assert victim_library.name not in response.text


def test_reindex_accepts_libraries_of_own_request(
    client: TestClient, session: SyncSession, user, user_token: str, own_request,
):
    library = create_library(session, user, own_request)
    session.commit()
    prefix = "/htmx/workflows/reindex"
    params = _begin_workflow(client, prefix, user_token, own_request.id)

    response = post_form(
        client, f"{prefix}/select-samples",
        {"selected_library_ids": json.dumps([library.id])},
        token=user_token, params=params,
    )

    assert response.status_code == 200
    assert library.name in response.text


def _reseq_path(seq_request_id: int, library_id: int) -> str:
    return f"/htmx/seq_requests/{seq_request_id}/reseq-library/{library_id}"


def _library_names(session: SyncSession, seq_request_id: int) -> list[str]:
    session.expire_all()
    return [lib.name for lib in session.get_all(Q.library.select(seq_request_id=seq_request_id), limit=None)]


def test_reseq_library_rejects_library_of_another_request(
    client: TestClient, session: SyncSession, user_token: str, own_request, victim_request, user_2,
):
    victim_library = create_library(session, user_2, victim_request)
    session.commit()

    response = post_form(client, _reseq_path(own_request.id, victim_library.id), {}, token=user_token)

    assert response.status_code == 400
    assert _library_names(session, own_request.id) == []


def test_reseq_library_accepts_library_of_same_request(
    client: TestClient, session: SyncSession, user, user_token: str, own_request,
):
    library = create_library(session, user, own_request)
    session.commit()

    response = post_form(client, _reseq_path(own_request.id, library.id), {}, token=user_token)

    assert response.status_code == 204
    assert _library_names(session, own_request.id) == [library.name, library.name]  # original and clone


EDIT_PROPERTIES_PATH = "/htmx/actions/edit-library-properties-action"


def _properties_payload(library: models.Library) -> dict[str, str]:
    return spreadsheet_payload(["ID", "Library Name"], [[library.id, library.name]])


def test_edit_library_properties_rejects_library_outside_scope(
    client: TestClient, session: SyncSession, user_token: str, own_request, victim_request, user_2,
):
    victim_library = create_library(session, user_2, victim_request)
    victim_library.properties = {"secret": "keep me"}
    session.commit()

    response = post_form(
        client, EDIT_PROPERTIES_PATH, _properties_payload(victim_library),
        token=user_token, params={"seq_request_id": own_request.id},
    )

    assert response.status_code == 404
    session.expire_all()
    assert session.get_one(Q.library.select(id=victim_library.id)).properties == {"secret": "keep me"}


def test_edit_library_properties_rejects_other_library_in_single_library_scope(
    client: TestClient, session: SyncSession, user, user_token: str, own_request,
):
    library, other = create_library(session, user, own_request), create_library(session, user, own_request)
    other.properties = {"note": "untouched"}
    session.commit()

    response = post_form(
        client, EDIT_PROPERTIES_PATH, _properties_payload(other),
        token=user_token, params={"library_id": library.id},
    )

    assert response.status_code == 404
    session.expire_all()
    assert session.get_one(Q.library.select(id=other.id)).properties == {"note": "untouched"}


def test_edit_library_properties_updates_library_in_scope(
    client: TestClient, session: SyncSession, user, user_token: str, own_request,
):
    library = create_library(session, user, own_request)
    library.properties = {"stale": "x"}
    session.commit()

    response = post_form(
        client, EDIT_PROPERTIES_PATH, _properties_payload(library),
        token=user_token, params={"seq_request_id": own_request.id},
    )

    assert_htmx_redirect(response, f"/seq_requests/{own_request.id}")
    session.expire_all()
    assert session.get_one(Q.library.select(id=library.id)).properties == {}


# ── 3. Stored XSS through uploads ───────────────────────────────────────────


def _media_file(session: SyncSession, uploader: models.User, seq_request: models.SeqRequest, extension: str, content: bytes) -> models.MediaFile:
    file = session.save(Q.media_file.create(
        name="upload",
        type=C.MediaFileType.CUSTOM,
        extension=extension,
        uploader_id=uploader.id,
        size_bytes=len(content),
        seq_request_id=seq_request.id,
    ), flush=True)
    session.commit()
    path = Path(config.settings.app_config.media_folder) / file.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return file


MALICIOUS_MARKDOWN = b"""# Notes

<img src=x onerror="alert(document.cookie)">
<script>alert(1)</script>
[click](javascript:alert(1))
<a href="https://example.org" onclick="alert(1)">link</a>

| Lane | Pool |
|------|------|
| 1    | A    |

- [x] done
"""


def test_markdown_render_strips_script(
    client: TestClient, session: SyncSession, user, insider_token: str, own_request,
):
    file = _media_file(session, user, own_request, ".md", MALICIOUS_MARKDOWN)

    response = get(client, f"/htmx/files/{file.id}/markdown", insider_token, htmx=True)

    assert response.status_code == 200
    body = response.text.lower()
    for forbidden in ("<script", "onerror", "onclick", "javascript:"):
        assert forbidden not in body, forbidden
    # Legitimate markdown output survives.
    assert "<h1>notes</h1>" in body
    assert "<table>" in body
    assert 'href="https://example.org"' in body
    assert 'type="checkbox"' in body


def test_markdown_render_keeps_generated_checklist_tables(
    client: TestClient, session: SyncSession, user, insider_token: str, own_request,
):
    """Checklists embed raw ``<table class="table">`` HTML; sanitising must keep it."""
    file = _media_file(
        session, user, own_request, ".md",
        b'<table border="0" class="dataframe table"><tr><td>Pool_A</td></tr></table>\n',
    )

    response = get(client, f"/htmx/files/{file.id}/markdown", insider_token, htmx=True)

    assert response.status_code == 200
    assert 'class="dataframe table"' in response.text
    assert "<td>Pool_A</td>" in response.text


@pytest.mark.parametrize("extension", [".html", ".htm", ".svg", ".xml"])
def test_active_content_is_served_sandboxed(
    client: TestClient, session: SyncSession, user, insider_token: str, own_request, extension: str,
):
    file = _media_file(session, user, own_request, extension, b"<script>alert(1)</script>")

    response = get(client, f"/htmx/files/{file.id}/render", insider_token)

    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == "sandbox"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_images_are_served_inline_without_sandbox(
    client: TestClient, session: SyncSession, user, insider_token: str, own_request,
):
    file = _media_file(session, user, own_request, ".png", b"\x89PNG\r\n\x1a\n")

    response = get(client, f"/htmx/files/{file.id}/render", insider_token)

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("inline")
    assert "Content-Security-Policy" not in response.headers


UPLOAD_PATH = "/htmx/files/upload"


def _upload(client: TestClient, token: str, seq_request_id: int, filename: str, content: bytes):
    client.cookies.set("csrf_token", CSRF)
    return client.post(
        UPLOAD_PATH,
        params={"seq_request_id": seq_request_id},
        data={"file_type": str(C.MediaFileType.CUSTOM.id), "comment": "", "csrf_token": CSRF},
        files={"file": (filename, content, "application/octet-stream")},
        headers=cookie_header(client, token),
        follow_redirects=False,
    )


def _uploads(session: SyncSession, seq_request_id: int) -> list[models.MediaFile]:
    session.expire_all()
    return list(session.get_all(
        sa.select(models.MediaFile).where(models.MediaFile.seq_request_id == seq_request_id), limit=None,
    ))


@pytest.fixture
def media_dir() -> None:
    os.makedirs(Path(config.settings.app_config.media_folder) / C.MediaFileType.CUSTOM.dir, exist_ok=True)


@pytest.mark.parametrize("filename", ["report.html", "image.svg", "notes.md", "noextension"])
def test_upload_rejects_disallowed_extension(
    client: TestClient, session: SyncSession, user_token: str, own_request, media_dir, filename: str,
):
    response = _upload(client, user_token, own_request.id, filename, b"<script>alert(1)</script>")

    assert_form_invalid(response, "is not allowed")
    assert _uploads(session, own_request.id) == []


def test_upload_rejects_oversized_file(
    client: TestClient, session: SyncSession, user_token: str, own_request, media_dir,
):
    from server.forms.models.MediaFileForm import MediaFileForm

    content = b"a" * (MediaFileForm.MAX_SIZE_MBYTES * 1024 * 1024 + 1)
    response = _upload(client, user_token, own_request.id, "big.csv", content)

    assert_form_invalid(response, "too large")
    assert _uploads(session, own_request.id) == []


def test_upload_accepts_allowed_extension_case_insensitively(
    client: TestClient, session: SyncSession, user_token: str, own_request, media_dir,
):
    response = _upload(client, user_token, own_request.id, "samples.CSV", b"a,b\n1,2\n")

    assert_htmx_redirect(response, f"/seq_requests/{own_request.id}")
    files = _uploads(session, own_request.id)
    assert len(files) == 1



def test_upload_name_cannot_choose_the_storage_path(
    client: TestClient, session: SyncSession, user_token: str, own_request, media_dir,
):
    """The stored path is ``<type dir>/<uuid><extension>``; the client filename is only the display name."""
    response = _upload(client, user_token, own_request.id, "../../../evil.csv", b"a,b\n")

    assert_htmx_redirect(response, f"/seq_requests/{own_request.id}")
    [file] = _uploads(session, own_request.id)
    assert file.path == f"{C.MediaFileType.CUSTOM.dir}/{file.uuid}.csv"
    assert (Path(config.settings.app_config.media_folder) / file.path).read_bytes() == b"a,b\n"


@pytest.mark.parametrize("filename, fallback", [
    ("Bericht–2024.csv", "Bericht_2024.csv"),
    ("数据.csv", "__.csv"),
    ("plain report.csv", "plain report.csv"),
])
def test_download_of_any_filename(
    client: TestClient, session: SyncSession, user_token: str, own_request, media_dir, filename: str, fallback: str,
):
    """Header values must be latin-1: names outside ASCII get an ASCII fallback plus ``filename*`` (RFC 5987)."""
    _upload(client, user_token, own_request.id, filename, b"a,b\n")
    [file] = _uploads(session, own_request.id)

    response = get(client, f"/htmx/files/{file.id}/download", user_token)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith(f'attachment; filename="{fallback}"')
    assert ("filename*=UTF-8''" in disposition) is (fallback != filename)
    if fallback != filename:
        assert unquote(disposition.split("filename*=UTF-8''")[1]) == filename


def test_content_disposition_strips_quotes_and_line_breaks():
    from server.core.responses import content_disposition

    value = content_disposition("attachment", 'a"b\r\nSet-Cookie: x.csv')

    assert "\r" not in value and "\n" not in value
    assert value.startswith('attachment; filename="a_b__Set-Cookie: x.csv"; filename*=UTF-8\'\'')

# ── 4. API tokens ────────────────────────────────────────────────────────────

CREATE_TOKEN_PATH = "/htmx/users/{user_id}/create-api-token"
TOKEN_TABLE_PATH = "/htmx/api-tokens/render-table-page"
VALIDATE_TOKEN_PATH = "/api/validate-api_token"


def _new_token(session: SyncSession, owner: models.User) -> models.APIToken:
    token = session.save(Q.api_token.create(owner=owner, time_valid_min=60), flush=True)
    session.commit()
    return token


def test_api_token_only_hash_is_stored(session: SyncSession, user):
    token = _new_token(session, user)

    assert token.plaintext is not None and len(token.plaintext) >= 43
    assert token.token_hash == hashlib.sha256(token.plaintext.encode()).hexdigest()
    columns = {c.name for c in models.APIToken.__table__.columns}
    assert "uuid" not in columns
    row = session.execute(sa.text("SELECT * FROM api_token WHERE id = :id"), {"id": token.id}).mappings().one()
    assert token.plaintext not in [str(v) for v in row.values()]

    session.expunge_all()
    assert session.get_one(Q.api_token.select(id=token.id)).plaintext is None


def test_api_token_lookup_by_secret(session: SyncSession, user):
    token = _new_token(session, user)

    assert session.get_one(Q.api_token.select(token=token.plaintext)).id == token.id
    assert session.first(Q.api_token.select(token=token.token_hash)) is None
    assert session.first(Q.api_token.select(token="not-a-token")) is None


def test_api_token_authenticates_with_secret_only(client: TestClient, session: SyncSession, user):
    token = _new_token(session, user)

    ok = client.get(VALIDATE_TOKEN_PATH, headers={"X-API-Token": token.plaintext})
    assert ok.status_code == 200

    # The stored hash is not a credential.
    by_hash = client.get(VALIDATE_TOKEN_PATH, headers={"X-API-Token": token.token_hash})
    assert by_hash.status_code in (401, 403)


def test_migration_hash_matches_application_hash(session: SyncSession):
    """The migration hashes legacy uuid tokens in SQL; that must equal ``APIToken.hash``."""
    legacy = "0192f1c4-5b7e-7c3a-9d2e-3f4a5b6c7d8e"
    in_sql = session.execute(
        sa.text("SELECT encode(sha256(convert_to(:t, 'UTF8')), 'hex')"), {"t": legacy},
    ).scalar_one()
    assert in_sql == models.APIToken.hash(legacy)


def test_insider_token_table_does_not_reveal_admin_token(
    client: TestClient, session: SyncSession, admin, insider_token: str,
):
    token = _new_token(session, admin)

    response = get(client, TOKEN_TABLE_PATH, insider_token, htmx=True)

    assert response.status_code == 200
    assert admin.name in response.text
    assert token.plaintext not in response.text
    assert token.token_hash not in response.text


def test_created_token_is_shown_once(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    response = post_form(client, CREATE_TOKEN_PATH.format(user_id=user.id), {"time_valid_min": "60"}, token=user_token)

    assert response.status_code == 200
    session.expire_all()
    token = session.get_one(Q.api_token.select(owner_id=user.id))
    secrets_shown = [v for v in response.text.split('"') if models.APIToken.hash(v) == token.token_hash]
    assert len(secrets_shown) == 1

    # The user's own token table no longer has a way to show it again.
    table = get(client, TOKEN_TABLE_PATH, user_token, params={"user_id": user.id}, htmx=True)
    assert secrets_shown[0] not in table.text


# ── 5. Email links use external_base_url, not the Host header ───────────────

EXTERNAL_BASE = "https://opengsync.example.org"
FORGED_HOST = "attacker.example"


@pytest.fixture
def external_base(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(config.settings.app_config, "external_base_url", EXTERNAL_BASE + "/")
    return EXTERNAL_BASE


def test_registration_link_ignores_forged_host(client: TestClient, fake_mailer, external_base: str):
    response = post_form(client, "/htmx/auth/register", {"email": "victim@example.com"}, headers={"Host": FORGED_HOST})

    assert_htmx_redirect(response)
    [(recipient, link)] = fake_mailer.registration
    assert recipient == "victim@example.com"
    assert link.startswith(f"{external_base}/auth/complete-registration/")
    assert FORGED_HOST not in link


def test_password_reset_link_ignores_forged_host(
    client: TestClient, fake_mailer, user, user_token: str, external_base: str,
):
    post_form(client, f"/htmx/auth/{user.id}/reset-password", {}, token=user_token, headers={"Host": FORGED_HOST})

    [(_, link)] = fake_mailer.password_reset
    assert link.startswith(f"{external_base}/auth/reset-password/")
    assert FORGED_HOST not in link


def test_email_link_falls_back_to_request_host_without_config(client: TestClient, fake_mailer):
    assert not config.settings.app_config.external_base_url

    post_form(client, "/htmx/auth/register", {"email": "new@example.com"})

    [(_, link)] = fake_mailer.registration
    # The host follows the request, the scheme is still https.
    assert link.startswith("https://testserver/auth/complete-registration/")


def test_share_snippets_use_external_base(external_base: str):
    """Copy-paste commands (also mailed with shares) use ``url_for(..., _external=True)``."""
    from starlette.requests import Request

    from server.core import templates
    from server.main import app

    request = Request({
        "type": "http", "app": app, "router": app.router, "method": "GET", "path": "/", "root_path": "",
        "query_string": b"", "headers": [(b"host", FORGED_HOST.encode())], "scheme": "http", "server": (FORGED_HOST, 80),
    })
    url = templates.j2.env.from_string('{{ url_for("file_share.rclone", token="tok", _external=True) }}').render(request=request)
    internal = templates.j2.env.from_string('{{ url_for("file_share.rclone", token="tok") }}').render(request=request)

    assert url.startswith(f"{external_base}/") and url.endswith("tok")
    assert FORGED_HOST not in url
    # In-app links keep following the request.
    assert internal.startswith(f"http://{FORGED_HOST}/")


@pytest.mark.parametrize("configured_base", [
    EXTERNAL_BASE,
    EXTERNAL_BASE + "/opengsync/v2/",
    # legacy config format: host only, scheme added by the app
    EXTERNAL_BASE.removeprefix("https://"),
    EXTERNAL_BASE.removeprefix("https://") + "/opengsync/v2",
])
def test_external_url_keeps_proxy_prefix(monkeypatch: pytest.MonkeyPatch, configured_base: str):
    """Behind nginx (X-Forwarded-Prefix -> root_path) email links keep the prefix, also when the base already has it."""
    from starlette.requests import Request

    from server.core import templates
    from server.main import app

    monkeypatch.setattr(config.settings.app_config, "external_base_url", configured_base)
    request = Request({
        "type": "http", "app": app, "router": app.router, "method": "GET", "path": "/", "root_path": "/opengsync/v2",
        "query_string": b"", "headers": [(b"host", FORGED_HOST.encode())], "scheme": "http", "server": (FORGED_HOST, 80),
    })

    url = str(templates.absolute_url_for(request, "file_share.browse", external=True, token="tok"))

    assert url == f"{EXTERNAL_BASE}/opengsync/v2/api/shares/browse/tok"


def _proxied_request(scheme: str = "http"):
    from starlette.requests import Request

    from server.main import app

    return Request({
        "type": "http", "app": app, "router": app.router, "method": "GET", "path": "/", "root_path": "/opengsync/v2",
        "query_string": b"", "headers": [(b"host", b"opengsync.example.org")], "scheme": scheme,
        "server": ("opengsync.example.org", 80),
    })


@pytest.mark.parametrize("environment", ["prod", "test"])
def test_external_url_without_config_is_https(monkeypatch: pytest.MonkeyPatch, environment: str):
    """Without ``external_base_url``, external links follow the request host and prefix but are always https outside dev."""
    from server.core import templates

    monkeypatch.setattr(config.settings.app_config, "external_base_url", None)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", environment)
    request = _proxied_request("http")

    external = str(templates.absolute_url_for(request, "file_share.browse", external=True, token="tok"))
    snippet = templates.j2.env.from_string('{{ url_for("file_share.rclone", token="tok", _external=True) }}').render(request=request)
    internal = str(templates.absolute_url_for(request, "file_share.browse", token="tok"))

    assert external == "https://opengsync.example.org/opengsync/v2/api/shares/browse/tok"
    assert snippet.startswith("https://opengsync.example.org/opengsync/v2/")
    # In-app links keep the request's scheme.
    assert internal.startswith("http://")


def test_external_url_without_config_keeps_http_in_dev(monkeypatch: pytest.MonkeyPatch):
    """Local dev serves plain http, so its links must not be forced to https."""
    from server.core import templates

    monkeypatch.setattr(config.settings.app_config, "external_base_url", None)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "dev")

    url = str(templates.absolute_url_for(_proxied_request("http"), "file_share.browse", external=True, token="tok"))

    assert url == "http://opengsync.example.org/opengsync/v2/api/shares/browse/tok"


def test_external_url_keeps_configured_scheme(monkeypatch: pytest.MonkeyPatch):
    """An explicit scheme in ``external_base_url`` is used as configured."""
    from server.core import templates

    monkeypatch.setattr(config.settings.app_config, "external_base_url", "http://intranet.example.org")

    url = str(templates.absolute_url_for(_proxied_request(), "file_share.browse", external=True, token="tok"))

    assert url == "http://intranet.example.org/opengsync/v2/api/shares/browse/tok"


# ── 6. Missing permission checks ────────────────────────────────────────────


def _affiliate(session: SyncSession, user: models.User, group: models.Group, kind: C.AffiliationType) -> None:
    session.add(models.links.UserAffiliation(user_id=user.id, group_id=group.id, affiliation_type=kind))


def _affiliation_type(session: SyncSession, group: models.Group, user: models.User) -> C.AffiliationType:
    session.expire_all()
    return session.get_one(Q.affiliation.select(group_id=group.id, user_id=user.id)).affiliation_type


@pytest.fixture
def lab(session: SyncSession, user, user_2) -> models.Group:
    """``user`` owns the group, ``user_2`` manages it."""
    group = create_group(session)
    _affiliate(session, user, group, C.AffiliationType.OWNER)
    _affiliate(session, user_2, group, C.AffiliationType.MANAGER)
    session.commit()
    return group


def test_manager_cannot_take_group_ownership(
    client: TestClient, session: SyncSession, lab, user, user_2, user_2_token: str,
):
    response = post_form(client, f"/htmx/groups/{lab.id}/make-owner/{user_2.id}", {}, token=user_2_token)

    assert response.status_code == 403
    assert _affiliation_type(session, lab, user) == C.AffiliationType.OWNER
    assert _affiliation_type(session, lab, user_2) == C.AffiliationType.MANAGER


def test_owner_can_transfer_group_ownership(
    client: TestClient, session: SyncSession, lab, user, user_2, user_token: str,
):
    response = post_form(client, f"/htmx/groups/{lab.id}/make-owner/{user_2.id}", {}, token=user_token)

    assert response.status_code == 204
    assert _affiliation_type(session, lab, user) == C.AffiliationType.MANAGER
    assert _affiliation_type(session, lab, user_2) == C.AffiliationType.OWNER


def test_insider_can_transfer_group_ownership(
    client: TestClient, session: SyncSession, lab, user_2, insider_token: str,
):
    response = post_form(client, f"/htmx/groups/{lab.id}/make-owner/{user_2.id}", {}, token=insider_token)

    assert response.status_code == 204
    assert _affiliation_type(session, lab, user_2) == C.AffiliationType.OWNER


def _seq_request_payload(name: str, group_id: int) -> dict[str, str]:
    from .forms.test_seq_request_form import _request_payload
    return _request_payload(name, **{"basic_info-group_id": str(group_id)})


def _seq_request_by_name(session: SyncSession, name: str) -> models.SeqRequest | None:
    session.expire_all()
    return session.first(Q.seq_request.select(name=name))


def test_seq_request_cannot_be_filed_into_foreign_group(
    client: TestClient, session: SyncSession, user_token: str,
):
    foreign = create_group(session)
    session.commit()

    response = post_form(client, "/htmx/seq_requests/create", _seq_request_payload("foreign-group-request", foreign.id), token=user_token)

    assert_form_invalid(response, "Requestor must be part of the selected group.")
    assert _seq_request_by_name(session, "foreign-group-request") is None


def test_seq_request_can_be_filed_into_own_group(
    client: TestClient, session: SyncSession, lab, user_token: str,
):
    response = post_form(client, "/htmx/seq_requests/create", _seq_request_payload("own-group-request", lab.id), token=user_token)

    assert response.status_code == 204
    request = _seq_request_by_name(session, "own-group-request")
    assert request is not None and request.group_id == lab.id


FEATURE_TABLE_PATH = "/htmx/features/render-table-page"


@pytest.fixture
def victim_feature(session: SyncSession, user_2, victim_request) -> tuple[models.Library, models.Feature]:
    library = create_library(session, user_2, victim_request)
    feature = create_feature(session)
    session.add(models.links.LibraryFeatureLink(library_id=library.id, feature_id=feature.id))
    session.commit()
    return library, feature


def test_feature_table_denies_foreign_library(client: TestClient, victim_feature, user_token: str):
    library, feature = victim_feature

    response = get(client, FEATURE_TABLE_PATH, user_token, params={"library_id": library.id}, htmx=True)

    assert response.status_code == 403
    assert feature.name not in response.text


def test_feature_table_shows_own_library(client: TestClient, victim_feature, user_2_token: str):
    library, feature = victim_feature

    response = get(client, FEATURE_TABLE_PATH, user_2_token, params={"library_id": library.id}, htmx=True)

    assert response.status_code == 200
    assert feature.name in response.text


def test_feature_table_unfiltered_is_insider_only(client: TestClient, victim_feature, user_token: str):
    # (The insider view of this branch renders a template that does not exist yet.)
    assert get(client, FEATURE_TABLE_PATH, user_token, htmx=True).status_code == 403


COMMENT_PATH = "/htmx/comments/comment"


def _comments(session: SyncSession) -> list[models.Comment]:
    session.expire_all()
    return list(session.get_all(sa.select(models.Comment), limit=None))


def test_comment_cannot_piggyback_into_experiment_thread(
    client: TestClient, session: SyncSession, own_request, insider, user_token: str,
):
    experiment = create_experiment(session, insider, CHECKLIST_WORKFLOW)
    session.commit()

    response = post_form(
        client, COMMENT_PATH, {"comment": "injected"}, token=user_token,
        params={"seq_request_id": own_request.id, "experiment_id": experiment.id},
    )

    assert response.status_code == 403
    assert _comments(session) == []


def test_comment_cannot_piggyback_into_lab_prep_thread(
    client: TestClient, session: SyncSession, own_request, insider, user_token: str,
):
    lab_prep = create_lab_prep(session, insider)
    session.commit()

    response = post_form(
        client, COMMENT_PATH, {"comment": "injected"}, token=user_token,
        params={"seq_request_id": own_request.id, "lab_prep_id": lab_prep.id},
    )

    assert response.status_code == 403
    assert _comments(session) == []


def test_comment_on_own_request_still_allowed(
    client: TestClient, session: SyncSession, own_request, user_token: str,
):
    response = post_form(client, COMMENT_PATH, {"comment": "hello"}, token=user_token, params={"seq_request_id": own_request.id})

    assert_htmx_redirect(response, f"/seq_requests/{own_request.id}")
    assert [c.text for c in _comments(session)] == ["hello"]


# ── 7. Empty SECRET_KEY ─────────────────────────────────────────────────────
# The key signs login, registration and password reset tokens. With an empty key anyone could
# sign a valid login token for any user, so the server must not start, sign or verify without one.

EMPTY_KEYS = pytest.mark.parametrize("key", ["", "   "], ids=["empty", "whitespace"])


def _forged(payload: dict, key: str) -> str:
    """An HS256 token signed with ``key``, built by hand: recent PyJWT refuses to sign with an empty key."""
    import base64
    import hmac

    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    signing_input = b64(b'{"alg":"HS256","typ":"JWT"}') + b"." + b64(json.dumps(payload).encode())
    signature = hmac.new(key.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + b64(signature)).decode()


@EMPTY_KEYS
def test_server_does_not_start_without_secret_key(monkeypatch: pytest.MonkeyPatch, key: str):
    import asyncio
    from fastapi import FastAPI
    from server.core import lifespan

    monkeypatch.setattr(config.settings, "SECRET_KEY", SecretStr(key))
    app = FastAPI()

    async def start():
        async with lifespan.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        asyncio.run(start())
    assert not hasattr(app.state, "db_handler")  # stopped before connecting to anything


@EMPTY_KEYS
def test_tokens_are_not_signed_without_secret_key(monkeypatch: pytest.MonkeyPatch, key: str, user):
    from server.core import secrets

    monkeypatch.setattr(config.settings, "SECRET_KEY", SecretStr(key))

    for sign in (
        lambda: secrets.create_login_token(user),
        lambda: secrets.create_password_reset_token(user.id),
        lambda: secrets.generate_registration_token("new@example.com", C.UserRole.CLIENT),
    ):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            sign()


@EMPTY_KEYS
def test_forged_tokens_are_not_accepted_without_secret_key(monkeypatch: pytest.MonkeyPatch, key: str, user):
    from server.core import secrets

    monkeypatch.setattr(config.settings, "SECRET_KEY", SecretStr(key))
    exp = config.settings.now().timestamp() + 3600

    for verify in (
        lambda: secrets.validate_login_token(_forged(
            {"id": user.id, "username": user.email, "role": C.UserRole.ADMIN.id, "exp": exp}, key,
        )),
        lambda: secrets.verify_password_reset_token(_forged(
            {"user_id": user.id, "action": "password_reset", "exp": exp}, key,
        )),
        lambda: secrets.verify_registration_token(_forged(
            {"email": "new@example.com", "role": C.UserRole.ADMIN.id, "action": "registration", "exp": exp}, key,
        )),
    ):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            verify()


def test_tokens_round_trip_with_secret_key(user):
    from server.core import secrets

    assert config.settings.SECRET_KEY.get_secret_value().strip()
    assert secrets.validate_login_token(secrets.create_login_token(user))["id"] == user.id
    assert secrets.verify_password_reset_token(secrets.create_password_reset_token(user.id)) == user.id
    assert secrets.verify_registration_token(
        secrets.generate_registration_token("new@example.com", C.UserRole.CLIENT),
    ) == ("new@example.com", C.UserRole.CLIENT)
