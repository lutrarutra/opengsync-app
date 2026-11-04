"""MediaFileForm: upload form.

On a seq request READ is enough at any status, so customers can add information after
submitting; replacing the signed authorization form needs WRITE. Experiments and lab preps
are insider-only.
"""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C
from server.core import config

from ...db.create_units import create_seq_request
from .._http import CSRF, assert_flash, assert_form_invalid, assert_htmx_redirect, cookie_header, get, post_form, post_form_csrf_mismatch

UPLOAD_PATH = "/htmx/files/upload"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _url(base: str, **params: object) -> str:
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base}?{qs}" if qs else base


def _payload(**overrides: object) -> dict[str, str]:
    data = {"file_type": "1", "comment": "Test upload"}
    data.update({k: str(v) for k, v in overrides.items() if v is not None})
    return data


def test_render_for_own_seq_request(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(UPLOAD_PATH, seq_request_id=sr.id), user_token)
    assert response.status_code == 200
    assert 'name="file_type"' in response.text


def test_render_for_stranger_seq_request_denied(client: TestClient, session: SyncSession, user, user_2_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = get(client, _url(UPLOAD_PATH, seq_request_id=sr.id), user_2_token)
    assert response.status_code == 403


def test_render_without_context_returns_400(client: TestClient, user_token: str):
    response = get(client, UPLOAD_PATH, user_token)
    assert response.status_code == 400


def test_post_without_context_returns_400(client: TestClient, user_token: str):
    response = post_form(client, UPLOAD_PATH, _payload(), token=user_token)
    assert response.status_code == 400


def test_post_empty_file_type_fails(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form(client, _url(UPLOAD_PATH, seq_request_id=sr.id), _payload(file_type=""), token=user_token)
    assert_form_invalid(response)


def test_post_csrf_mismatch(client: TestClient, session: SyncSession, user, user_token: str):
    sr = create_seq_request(session, user)
    session.commit()
    response = post_form_csrf_mismatch(client, _url(UPLOAD_PATH, seq_request_id=sr.id), _payload(), token=user_token)
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, "error")

@pytest.fixture
def media_dirs() -> None:
    for file_type in (C.MediaFileType.CUSTOM, C.MediaFileType.SEQ_AUTH_FORM):
        os.makedirs(Path(config.settings.app_config.media_folder) / file_type.dir, exist_ok=True)


def _submitted_request(session: SyncSession, user: models.User) -> models.SeqRequest:
    seq_request = create_seq_request(session, user)
    seq_request.status = C.SeqRequestStatus.FINISHED
    session.save(seq_request)
    session.commit()
    return seq_request


def _upload(
    client: TestClient, token: str, seq_request_id: int, file_type: C.MediaFileType,
    filename: str = "info.pdf", content: bytes = b"%PDF-1.4",
):
    client.cookies.set("csrf_token", CSRF)
    return client.post(
        UPLOAD_PATH,
        params={"seq_request_id": seq_request_id},
        data={"file_type": str(file_type.id), "comment": "", "csrf_token": CSRF},
        files={"file": (filename, content, "application/octet-stream")},
        headers=cookie_header(client, token),
        follow_redirects=False,
    )


def test_owner_can_add_file_to_submitted_request(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = _submitted_request(session, user)

    assert get(client, _url(UPLOAD_PATH, seq_request_id=seq_request.id), user_token).status_code == 200
    assert_htmx_redirect(_upload(client, user_token, seq_request.id, C.MediaFileType.CUSTOM), f"/seq_requests/{seq_request.id}")


def test_owner_cannot_replace_auth_form_after_submission(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = _submitted_request(session, user)

    response = get(client, _url(UPLOAD_PATH, seq_request_id=seq_request.id, type=C.MediaFileType.SEQ_AUTH_FORM.id), user_token)
    assert response.status_code == 403
    assert _upload(client, user_token, seq_request.id, C.MediaFileType.SEQ_AUTH_FORM).status_code == 403


def test_owner_can_upload_auth_form_on_draft_request(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = create_seq_request(session, user)
    session.commit()

    assert_htmx_redirect(_upload(client, user_token, seq_request.id, C.MediaFileType.SEQ_AUTH_FORM), f"/seq_requests/{seq_request.id}")


# ── customer test 2026-11-04: uploads are checked by type and content ────────


def test_html_renamed_to_pdf_is_rejected(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = create_seq_request(session, user)
    session.commit()
    response = _upload(client, user_token, seq_request.id, C.MediaFileType.SEQ_AUTH_FORM, "fake.pdf", b"<html><script>alert(1)</script></html>")
    assert_form_invalid(response)
    assert "not a valid &#39;.pdf&#39; file" in response.text or "not a valid '.pdf' file" in response.text
    assert session.scalar(sa.select(sa.func.count()).select_from(models.MediaFile)) == 0


def test_auth_form_must_be_a_pdf(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = create_seq_request(session, user)
    session.commit()
    response = _upload(client, user_token, seq_request.id, C.MediaFileType.SEQ_AUTH_FORM, "form.csv", b"a,b\n1,2\n")
    assert_form_invalid(response)


def test_client_cannot_upload_facility_file_types(client: TestClient, session: SyncSession, user, user_token: str, media_dirs):
    seq_request = create_seq_request(session, user)
    session.commit()

    rendered = get(client, _url(UPLOAD_PATH, seq_request_id=seq_request.id), user_token).text
    assert C.MediaFileType.POST_SEQUENCING_QC_REPORT.label not in rendered
    assert C.MediaFileType.SEQ_AUTH_FORM.label in rendered

    response = _upload(client, user_token, seq_request.id, C.MediaFileType.POST_SEQUENCING_QC_REPORT)
    assert_form_invalid(response)


def test_insider_sees_all_file_types(client: TestClient, session: SyncSession, user, insider_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()
    rendered = get(client, _url(UPLOAD_PATH, seq_request_id=seq_request.id), insider_token).text
    assert C.MediaFileType.POST_SEQUENCING_QC_REPORT.label in rendered


@pytest.mark.parametrize("extension, content, ok", [
    ("pdf", b"%PDF-1.7 ...", True), ("pdf", b"<html>", False),
    ("png", b"\x89PNG\r\n\x1a\nrest", True), ("png", b"GIF89a", False),
    ("jpg", b"\xff\xd8\xff\xe0", True), ("xlsx", b"PK\x03\x04...", True), ("xlsx", b"a,b", False),
    ("csv", b"a,b\n1,2", True), ("tsv", b"a\x00b", False),
])
def test_content_matches_extension(extension: str, content: bytes, ok: bool):
    from server.components.inputs.file import content_matches_extension
    assert content_matches_extension(content, extension) is ok
