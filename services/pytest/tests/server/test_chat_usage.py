"""Chat usage summary on the admin page, read from the audit logs with DuckDB."""
import gzip
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from server.chat import usage
from server.core import config

from ._http import auth

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=config.settings.TIMEZONE)


def _line(ts: datetime, user_id: int | None, status_code: int = 200, message: str = "hello",
          page: str | None = "/projects/{project_id}", route: str = usage.CHAT_ROUTE, method: str = "POST") -> str:
    return json.dumps({
        "ts": ts.isoformat(), "user_id": user_id, "method": method, "path": route, "route": route,
        "status_code": status_code, "process_time": 0.01, "resource_id": None,
        "metadata": {"message": message, "length": len(message), "page": page, "form": None},
        "changes": [], "query_params": {}, "ip": "198.51.100.20", "agent": "pytest",
    })


@pytest.fixture
def audit_folder(tmp_path):
    folder = tmp_path / "audits"
    folder.mkdir()
    (folder / f"{NOW.date()}.jsonl").write_text("\n".join([
        _line(NOW - timedelta(hours=1), 1, message="How do I submit a request?"),
        _line(NOW - timedelta(hours=2), 1, page=None),
        _line(NOW - timedelta(hours=3), 2, status_code=429, message="spam"),
        _line(NOW - timedelta(hours=4), 2, route="/htmx/projects/{project_id}/delete", method="DELETE"),
        _line(NOW - timedelta(hours=5), 2, method="GET"),
        '{"ts": "2026-10-22T1',  # line cut off mid-write
    ]) + "\n")
    # rotated files are gzipped
    with gzip.open(folder / f"{(NOW - timedelta(days=10)).date()}.jsonl.gz", "wt") as f:
        f.write(_line(NOW - timedelta(days=10), 3) + "\n")
    (folder / "2025-01-01.jsonl").write_text(_line(datetime(2025, 1, 1, tzinfo=config.settings.TIMEZONE), 4) + "\n")
    (folder / "notes.txt").write_text("not an audit file")
    return folder


def test_audit_files_filters_by_date(audit_folder):
    files = usage.audit_files(str(audit_folder), since=date(2026, 1, 1))
    assert [f.rsplit("/", 1)[-1] for f in files] == ["2026-10-12.jsonl.gz", "2026-10-22.jsonl"]


def test_summarize_counts_chat_messages(audit_folder):
    summary = usage.summarize(str(audit_folder), now=NOW, days=30)

    assert summary.messages_24h == 2
    assert summary.messages_7d == 2
    assert summary.messages == 3
    assert summary.rejected == 1
    assert summary.users_7d == 1
    assert summary.users == 2

    assert len(summary.daily) == 30
    assert summary.daily[-1].day == NOW.date()
    assert (summary.daily[-1].messages, summary.daily[-1].rejected, summary.daily[-1].users) == (2, 1, 1)
    assert sum(d.messages for d in summary.daily) == 3
    assert summary.max_daily == 3

    assert [(u.user_id, u.messages, u.rejected) for u in summary.top_users] == [(1, 2, 0), (3, 1, 0), (2, 0, 1)]
    assert [(p.page, p.messages) for p in summary.top_pages] == [("/projects/{project_id}", 2), (None, 1)]
    assert [(r.status_code, r.attempts, r.label) for r in summary.rejections] == [(429, 1, usage.STATUS_LABELS[429])]
    assert [m.message for m in summary.recent][:3] == ["How do I submit a request?", "hello", "spam"]


def test_summarize_window(audit_folder):
    summary = usage.summarize(str(audit_folder), now=NOW, days=7)
    assert summary.messages == 2
    assert len(summary.daily) == 7
    assert 3 not in {u.user_id for u in summary.top_users}


def test_summarize_without_audits(tmp_path):
    summary = usage.summarize(str(tmp_path / "missing"), now=NOW, days=7)
    assert summary.messages == 0
    assert summary.max_daily == 0
    assert len(summary.daily) == 7
    assert summary.recent == []


def test_admin_sees_chat_usage(client: TestClient, admin_token: str, user, audit_folder, monkeypatch):
    monkeypatch.setattr(config.settings.app_config, "log_folder", str(audit_folder.parent))
    (audit_folder / f"{config.settings.now().date()}.jsonl").write_text(
        _line(config.settings.now() - timedelta(minutes=5), user.id, message="<b>where are my reads?</b>") + "\n"
    )

    response = client.get("/htmx/admin/chat-usage?days=7", headers=auth(admin_token) | {"HX-Request": "true"})
    assert response.status_code == 200
    assert "Chat Usage" in response.text
    assert user.name in response.text
    assert "&lt;b&gt;where are my reads?&lt;/b&gt;" in response.text  # message text is escaped


def test_chat_usage_rejects_other_windows(client: TestClient, admin_token: str):
    response = client.get("/htmx/admin/chat-usage?days=5", headers=auth(admin_token) | {"HX-Request": "true"})
    assert response.status_code == 400


@pytest.mark.parametrize("token", ["user_token", "insider_token"])
def test_only_admins_see_chat_usage(client: TestClient, token: str, request):
    response = client.get("/htmx/admin/chat-usage", headers=auth(request.getfixturevalue(token)) | {"HX-Request": "true"})
    assert response.status_code == 403
