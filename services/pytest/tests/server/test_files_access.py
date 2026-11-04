"""HTTP access to media files: reading follows the seq request, deleting needs WRITE (uploader + draft).

Regression for the customer test 2026-11-04: a client who had uploaded any file could download and
delete every media file in the system.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ..db.create_units import create_seq_request
from ._http import get, delete

FILE_ROUTES = ("download", "render", "markdown")


def _upload(session: SyncSession, uploader: models.User, seq_request: models.SeqRequest, content: bytes = b"secret") -> models.MediaFile:
    file = session.save(Q.media_file.create(
        name="upload", type=C.MediaFileType.CUSTOM, extension=".csv", uploader_id=uploader.id,
        size_bytes=len(content), seq_request_id=seq_request.id,
    ), flush=True)
    session.commit()
    path = Path(config.settings.app_config.media_folder) / file.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return file


@pytest.mark.parametrize("route", FILE_ROUTES)
def test_stranger_with_own_upload_cannot_read_other_file(
    client: TestClient, session: SyncSession, user, user_2, user_2_token: str, route: str,
):
    other = _upload(session, user, create_seq_request(session, user), b"ALICE CONFIDENTIAL")
    _upload(session, user_2, create_seq_request(session, user_2))

    response = get(client, f"/htmx/files/{other.id}/{route}", user_2_token, htmx=True)
    assert response.status_code == 403
    assert b"ALICE CONFIDENTIAL" not in response.content


def test_stranger_with_own_upload_cannot_delete_other_file(
    client: TestClient, session: SyncSession, user, user_2, user_2_token: str,
):
    other = _upload(session, user, create_seq_request(session, user))
    _upload(session, user_2, create_seq_request(session, user_2))

    assert delete(client, f"/htmx/files/{other.id}/delete", user_2_token).status_code == 403
    assert session.get(models.MediaFile, other.id) is not None


def test_uploader_cannot_delete_file_after_submission(
    client: TestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    file = _upload(session, user, seq_request)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.save(seq_request, flush=True)
    session.commit()

    assert delete(client, f"/htmx/files/{file.id}/delete", user_token).status_code == 403
    assert session.get(models.MediaFile, file.id) is not None


def test_uploader_can_delete_file_of_draft(client: TestClient, session: SyncSession, user, user_token: str):
    file = _upload(session, user, create_seq_request(session, user))
    assert delete(client, f"/htmx/files/{file.id}/delete", user_token).status_code == 204


def test_requestor_can_download_staff_file_on_own_request(
    client: TestClient, session: SyncSession, user, insider, user_token: str,
):
    file = _upload(session, insider, create_seq_request(session, user), b"QC report")

    response = get(client, f"/htmx/files/{file.id}/download", user_token, htmx=True)
    assert response.status_code == 200
    assert response.content == b"QC report"
