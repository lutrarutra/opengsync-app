import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from loguru import logger

from opengsync_db import models, SyncSession

from server.core import audit

from ..db.create_units import create_project, create_protocol, create_sample
from ._http import delete, get, post_form


@pytest.fixture
def audit_records():
    records: list[dict] = []
    sink_id = logger.add(
        lambda message: records.append(dict(message.record["extra"])),
        filter=lambda record: record["extra"].get("audit") is True,
        level="INFO",
    )
    yield records
    logger.remove(sink_id)


# ── change collection on the session ──────────────────────────────────

def test_commit_records_insert_update_delete(session: SyncSession):
    protocol = create_protocol(session)
    assert audit.pop_changes(session) == []  # flushed, not committed yet
    session.commit()
    assert audit.pop_changes(session) == [
        {"table": "protocol", "op": "insert", "count": 1, "ids": [protocol.id]},
    ]

    protocol.read_structure = "R1:28"
    session.commit()
    assert audit.pop_changes(session) == [
        {"table": "protocol", "op": "update", "count": 1, "ids": [protocol.id], "fields": ["read_structure"]},
    ]

    session.delete(protocol)
    session.commit()
    assert audit.pop_changes(session) == [
        {"table": "protocol", "op": "delete", "count": 1, "ids": [protocol.id]},
    ]


def test_rollback_discards_changes(session: SyncSession):
    create_protocol(session)
    session.rollback()
    assert audit.pop_changes(session) == []


def test_rollback_keeps_changes_committed_earlier(session: SyncSession):
    protocol = create_protocol(session)
    session.commit()

    create_protocol(session)
    session.rollback()

    assert audit.pop_changes(session) == [
        {"table": "protocol", "op": "insert", "count": 1, "ids": [protocol.id]},
    ]


def test_bulk_statement_is_recorded(session: SyncSession):
    protocol = create_protocol(session)
    session.commit()
    audit.pop_changes(session)

    session.execute(sa.delete(models.Protocol).where(models.Protocol.id == protocol.id))
    session.commit()
    assert audit.pop_changes(session) == [
        {"table": "protocol", "op": "delete", "count": 1, "ids": [], "bulk": True},
    ]


# ── audit lines written by the middleware ─────────────────────────────

def test_db_write_is_audited_with_changes(
    client: TestClient, session: SyncSession, admin, admin_token: str, audit_records: list[dict],
):
    protocol = create_protocol(session)
    session.commit()

    response = delete(client, f"/htmx/protocols/{protocol.id}/delete", token=admin_token, htmx=True)
    assert response.status_code == 204

    assert len(audit_records) == 1
    record = audit_records[0]
    assert record["user_id"] == admin.id
    assert record["route"] == "/htmx/protocols/{protocol_id}/delete"
    assert record["status_code"] == 204
    assert {"table": "protocol", "op": "delete", "count": 1, "ids": [protocol.id]} in record["changes"]


def test_write_is_attributed_when_route_only_checks_user_id(
    client: TestClient, session: SyncSession, user, user_token: str, audit_records: list[dict],
):
    # sample_permissions authenticates via require_user_id and never loads the user object
    sample = create_sample(session, user, create_project(session, user))
    session.commit()

    response = delete(client, f"/htmx/samples/{sample.id}/delete", token=user_token, htmx=True)
    assert response.status_code == 204

    assert len(audit_records) == 1
    assert audit_records[0]["user_id"] == user.id
    assert {"table": "sample", "op": "delete", "count": 1, "ids": [sample.id]} in audit_records[0]["changes"]


def test_read_only_request_is_not_audited(client: TestClient, user_token: str, audit_records: list[dict]):
    assert get(client, "/", token=user_token).status_code == 200
    assert audit_records == []


def test_auth_route_is_audited_without_db_write(client: TestClient, user, audit_records: list[dict]):
    response = post_form(client, "/htmx/auth/login", {"email": user.email, "password": "wrong-password"})
    assert response.status_code == 202

    assert len(audit_records) == 1
    assert audit_records[0]["route"] == "/htmx/auth/login"
    assert audit_records[0]["changes"] == []


def test_failed_commit_returns_500_and_is_not_audited_as_change(
    client: TestClient, session: SyncSession, admin_token: str, audit_records: list[dict],
    monkeypatch: pytest.MonkeyPatch,
):
    protocol = create_protocol(session)
    session.commit()

    def failing_commit(self):
        raise sa.exc.OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(SyncSession, "commit", failing_commit)
    response = delete(client, f"/htmx/protocols/{protocol.id}/delete", token=admin_token, htmx=True)
    monkeypatch.undo()

    assert response.status_code == 500
    session.expire_all()
    assert session.get(models.Protocol, protocol.id) is not None

    assert len(audit_records) == 1
    assert audit_records[0]["status_code"] == 500
    assert audit_records[0]["changes"] == []
