"""Audit log viewer on the admin page, read from the audit logs with DuckDB."""
import gzip
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from opengsync_db import models, queries as Q, SyncSession

from server.core import audit_reader, config

from ._http import auth

TZ = config.settings.TIMEZONE
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=TZ)
TODAY = NOW.date()
TOKEN = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"


def _line(ts: datetime, user_id: int | None = 1, method: str = "POST", path: str = "/htmx/projects/1/edit",
          route: str = "/htmx/projects/{project_id}/edit", status_code: int = 200, changes: list | None = None,
          resource_id: str | None = None, metadata: dict | None = None, ip: str = "198.51.100.20") -> str:
    return json.dumps({
        "ts": ts.isoformat(), "user_id": user_id, "method": method, "path": path, "route": route,
        "status_code": status_code, "process_time": 0.01, "resource_id": resource_id, "metadata": metadata or {},
        "changes": changes or [], "query_params": {}, "ip": ip, "agent": "pytest",
    })


def _change(table: str, op: str, ids: list, fields: list[str] | None = None, count: int | None = None) -> dict:
    change = {"table": table, "op": op, "count": count if count is not None else len(ids), "ids": ids}
    if fields:
        change["fields"] = fields
    return change


@pytest.fixture
def audit_folder(tmp_path):
    folder = tmp_path / "audits"
    folder.mkdir()
    (folder / f"{TODAY}.jsonl").write_text("\n".join([
        _line(NOW - timedelta(hours=1), user_id=1, changes=[_change("project", "update", [1], ["title"])]),
        _line(NOW - timedelta(hours=2), user_id=2, changes=[
            _change("checklist_log", "insert", [7]), _change("seq_request", "update", [385], ["review_checklist"]),
        ]),
        _line(NOW - timedelta(hours=3), user_id=2, method="DELETE", path="/htmx/seq_requests/386",
              route="/htmx/seq_requests/{seq_request_id}", changes=[_change("seq_request", "delete", [386])]),
        _line(NOW - timedelta(hours=4), user_id=None, method="GET", path=f"/api/shares/browse/{TOKEN}/data",
              route="/api/shares/browse/{token}/{subpath}", resource_id=TOKEN,
              metadata={"owner_id": 1, "path": f"/api/shares/browse/{TOKEN}/data"}, ip="203.0.113.7"),
        _line(NOW - timedelta(hours=5), user_id=1, changes=[_change("share_path", "insert", [[TOKEN, "data"]])]),
        '{"ts": "2026-10-22T1',  # line cut off mid-write
    ]) + "\n")
    # rotated files are gzipped
    with gzip.open(folder / f"{TODAY - timedelta(days=3)}.jsonl.gz", "wt") as f:
        f.write(_line(NOW - timedelta(days=3), user_id=None, method="GET", path=f"/files/share/browse/{TOKEN}",
                      route="/files/share/browse/{token}", status_code=403, ip="203.0.113.8") + "\n")
        f.write(_line(NOW - timedelta(days=3, hours=1), user_id=3, changes=[
            _change("share_token", "insert", ["0190ffff-0000-7000-8000-000000000000"]),
        ]) + "\n")
    (folder / f"{TODAY - timedelta(days=30)}.jsonl").write_text(
        _line(NOW - timedelta(days=30), user_id=1, changes=[_change("seq_request", "update", [385], ["name"])]) + "\n"
    )
    (folder / "notes.txt").write_text("not an audit file")
    return folder


def _query(folder, **kwargs) -> audit_reader.AuditPage:
    kwargs.setdefault("start", TODAY - timedelta(days=6))
    kwargs.setdefault("end", TODAY)
    page = kwargs.pop("page", 0)
    per_page = kwargs.pop("per_page", 50)
    flt = audit_reader.AuditFilter(**kwargs)
    flt.validate()
    return audit_reader.query(str(folder), flt, tz=TZ, page=page, per_page=per_page)


def test_audit_files_until(audit_folder):
    files = audit_reader.audit_files(str(audit_folder), since=TODAY - timedelta(days=40), until=TODAY - timedelta(days=1))
    assert [f.rsplit("/", 1)[-1] for f in files] == [f"{TODAY - timedelta(days=30)}.jsonl", f"{TODAY - timedelta(days=3)}.jsonl.gz"]


def test_query_all_newest_first(audit_folder):
    result = _query(audit_folder)
    assert result.total == 7
    assert [e.ts for e in result.entries] == sorted((e.ts for e in result.entries), reverse=True)
    assert result.entries[0].changes[0].table == "project"
    assert result.entries[0].changes[0].fields == ["title"]


def test_query_date_range(audit_folder):
    assert _query(audit_folder, start=TODAY - timedelta(days=40), end=TODAY - timedelta(days=1)).total == 3
    assert _query(audit_folder, start=TODAY - timedelta(days=40)).total == 8
    assert _query(audit_folder, start=TODAY - timedelta(days=2)).total == 5


def test_query_filters(audit_folder):
    assert _query(audit_folder, user_id=2).total == 2
    assert _query(audit_folder, method="DELETE").total == 1
    assert _query(audit_folder, status="error").total == 1
    assert _query(audit_folder, status="ok").total == 6
    assert _query(audit_folder, route="SEQ_REQUESTS/386").total == 1  # path, case-insensitive
    assert _query(audit_folder, route="{seq_request_id}").total == 1  # route template
    assert _query(audit_folder, ip="203.0.113.7").total == 1


def test_query_changes_to_a_row(audit_folder):
    # "who changed seq request 385 and when?"
    result = _query(audit_folder, table="seq_request", row_id="385", start=TODAY - timedelta(days=40))
    assert [(e.user_id, e.changes[-1].fields) for e in result.entries] == [(2, ["review_checklist"]), (1, ["name"])]

    assert _query(audit_folder, table="seq_request").total == 2
    assert _query(audit_folder, table="seq_request", op="delete").total == 1
    assert _query(audit_folder, table="seq_request", row_id="38").total == 0
    assert _query(audit_folder, table="project", row_id="385").total == 0
    # uuid ids
    assert _query(audit_folder, table="share_token", row_id="0190ffff-0000-7000-8000-000000000000").total == 1


def test_query_share_link_access(audit_folder):
    # "who accessed this share link?" - logged with resource_id, and rejected attempts with the token in the path
    result = _query(audit_folder, share=TOKEN)
    assert [(e.ip, e.status_code) for e in result.entries] == [("203.0.113.7", 200), ("203.0.113.8", 403)]
    assert result.entries[0].owner_id == 1


def test_query_pagination(audit_folder):
    first = _query(audit_folder, per_page=3)
    last = _query(audit_folder, per_page=3, page=2)
    assert (first.total, first.num_pages, len(first.entries), len(last.entries)) == (7, 3, 3, 1)
    assert last.entries[0].ts < first.entries[-1].ts


def test_query_without_audits(tmp_path):
    result = _query(tmp_path / "missing")
    assert (result.total, result.num_pages, result.entries) == (0, 0, [])


@pytest.mark.parametrize("kwargs", [
    {"start": TODAY, "end": TODAY - timedelta(days=1)},
    {"start": TODAY - timedelta(days=400)},
    {"method": "TRACE"},
    {"status": "maybe"},
    {"op": "upsert"},
    {"table": "project; DROP TABLE x"},
    {"row_id": "1"},
])
def test_invalid_filters(kwargs):
    kwargs.setdefault("start", TODAY - timedelta(days=6))
    kwargs.setdefault("end", TODAY)
    with pytest.raises(ValueError):
        audit_reader.AuditFilter(**kwargs).validate()


# ── routes ───────────────────────────────────────────────────────────────────


@pytest.fixture
def live_audits(tmp_path, monkeypatch, user: models.User):
    """Audit lines from today (the routes default to the last 7 days of the real clock)."""
    audit_folder = tmp_path / "live" / "audits"
    audit_folder.mkdir(parents=True)
    monkeypatch.setattr(config.settings.app_config, "log_folder", str(audit_folder.parent))
    now = config.settings.now()
    (audit_folder / f"{now.date()}.jsonl").write_text("\n".join([
        _line(now - timedelta(minutes=5), user_id=user.id, path="/htmx/projects/<b>1</b>",
              changes=[_change("project", "update", [1], ["title"])], metadata={"note": "<script>x</script>"}),
        _line(now - timedelta(minutes=6), user_id=None, method="GET", path=f"/api/shares/browse/{TOKEN}",
              route="/api/shares/browse/{token}", resource_id=TOKEN, metadata={"owner_id": user.id, "path": "/"}),
    ]) + "\n")
    return audit_folder


def _htmx(client: TestClient, token: str, url: str):
    return client.get(url, headers=auth(token) | {"HX-Request": "true"})


def test_admin_sees_audit_log(client: TestClient, admin_token: str, user: models.User, live_audits):
    response = _htmx(client, admin_token, "/htmx/admin/audits")
    assert response.status_code == 200
    assert "2 entries" in response.text
    assert user.name in response.text
    assert "review_checklist" not in response.text  # older than the default range
    assert "&lt;b&gt;1&lt;/b&gt;" in response.text and "<b>1</b>" not in response.text
    assert "<script>x</script>" not in response.text
    assert "Share link" in response.text


def test_admin_filters_audit_log(client: TestClient, admin_token: str, live_audits):
    response = _htmx(client, admin_token, "/htmx/admin/audits?table=project&row_id=1&share=&method=")
    assert response.status_code == 200
    assert "1 entry" in response.text

    response = _htmx(client, admin_token, f"/htmx/admin/audits?share={TOKEN}")
    assert "1 entry" in response.text

    # links keep the current filters
    assert f"share={TOKEN}" in response.text


def test_share_link_start_without_end(client: TestClient, admin_token: str, live_audits):
    # the access log link of an old share token only gives the start; the range is cut to the maximum
    start = config.settings.now().date() - timedelta(days=500)
    response = _htmx(client, admin_token, f"/htmx/admin/audits?share={TOKEN}&start={start}")
    assert response.status_code == 200
    assert "0 entries" in response.text


@pytest.mark.parametrize("query", [
    "start=yesterday", "user_id=me", "start=2026-10-22&end=2026-10-01", "start=2024-01-01&end=2026-01-01",
    "method=TRACE", "table=a%20b", "row_id=1",
])
def test_audit_log_rejects_bad_filters(client: TestClient, admin_token: str, query: str):
    assert _htmx(client, admin_token, f"/htmx/admin/audits?{query}").status_code == 400


def test_admin_sees_audits_page(client: TestClient, admin_token: str):
    response = client.get("/admin/audits?table=seq_request&row_id=385", headers=auth(admin_token))
    assert response.status_code == 200
    assert 'value="seq_request"' in response.text
    assert 'value="385"' in response.text


def test_share_tokens_link_to_access_log(client: TestClient, session: SyncSession, admin_token: str, user):
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()
    response = _htmx(client, admin_token, "/htmx/share_tokens/render-table-page")
    assert response.status_code == 200
    assert f"share={token.uuid}" in response.text


@pytest.mark.parametrize("token", ["user_token", "insider_token"])
@pytest.mark.parametrize("url", ["/admin/audits", "/htmx/admin/audits"])
def test_only_admins_see_audits(client: TestClient, token: str, url: str, request):
    response = client.get(url, headers=auth(request.getfixturevalue(token)) | {"HX-Request": "true"}, follow_redirects=False)
    assert response.status_code == 403
