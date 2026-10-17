"""Archiving a sequencing request: users who can edit a DRAFT request may archive it, all others need staff.

By the request access levels, the requestor (and their group) has WRITE on a DRAFT request and READ
on a submitted one.
"""
import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import create_seq_request
from ._http import post_form


def _archive(client: TestClient, seq_request_id: int, token: str):
    return post_form(client, f"/htmx/seq_requests/{seq_request_id}/archive", {}, token=token, htmx=True)


def _status(session: SyncSession, seq_request_id: int) -> C.SeqRequestStatus:
    session.expire_all()
    return session.get_one(Q.seq_request.select(id=seq_request_id)).status


def test_requestor_archives_own_draft(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()
    assert _archive(client, seq_request.id, user_token).status_code in (200, 204)
    assert _status(session, seq_request.id) == C.SeqRequestStatus.ARCHIVED


def test_requestor_cannot_archive_submitted_request(client: TestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()
    assert _archive(client, seq_request.id, user_token).status_code == 403
    assert _status(session, seq_request.id) == C.SeqRequestStatus.SUBMITTED


def test_stranger_cannot_archive_draft(client: TestClient, session: SyncSession, user, user_2_token: str):
    seq_request = create_seq_request(session, user)
    session.commit()
    assert _archive(client, seq_request.id, user_2_token).status_code in (403, 404)
    assert _status(session, seq_request.id) == C.SeqRequestStatus.DRAFT


@pytest.mark.parametrize("status", [C.SeqRequestStatus.DRAFT, C.SeqRequestStatus.FINISHED])
def test_insider_archives_any_request(client: TestClient, session: SyncSession, user, insider_token: str, status):
    seq_request = create_seq_request(session, user)
    seq_request.status = status
    session.commit()
    assert _archive(client, seq_request.id, insider_token).status_code in (200, 204)
    assert _status(session, seq_request.id) == C.SeqRequestStatus.ARCHIVED
