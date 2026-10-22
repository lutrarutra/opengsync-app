"""Admin shares page: every share link with its paths, sizes from the fs-index, expiring and editing paths."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q
from opengsync_db.fs_index import FsIndexDBHandler

from server.core import config

from ._http import get, post_form
from .test_fs_index_search import _index

ENTRIES = [
    {"path": "BSF_PROJECTS", "kind": "d", "total_size": 1500, "n_files": 3},
    {"path": "BSF_PROJECTS/P1", "kind": "d", "total_size": 1000, "n_files": 2},
    {"path": "BSF_PROJECTS/P1/a.txt", "kind": "f", "size": 400},
    {"path": "BSF_PROJECTS/P1/b.txt", "kind": "f", "size": 600},
    {"path": "BSF_PROJECTS/P2", "kind": "d", "total_size": 500, "n_files": 1},
    {"path": "BSF_PROJECTS/P2/c.txt", "kind": "f", "size": 500},
]


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "share"
    for entry in ENTRIES:
        path = root / entry["path"]
        if entry["kind"] == "d":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.write_bytes(b"x" * entry["size"])
    (root / "BSF_PROJECTS" / "P3").mkdir()  # on the share, not in the index yet
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return root


@pytest.fixture
def index(client: TestClient, share_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "fs_index.sqlite3"
    _index(db_file, ENTRIES)
    monkeypatch.setattr(config.settings.app_config.fs_index, "enabled", True)
    monkeypatch.setattr(config.settings.app_config.fs_index, "db_file", str(db_file))
    handler = FsIndexDBHandler(str(db_file))
    client.app.state.fs_index_db = handler
    try:
        yield db_file
    finally:
        handler.close()
        client.app.state.fs_index_db = None


def _share(session: SyncSession, owner: models.User, paths: list[str], age_min: int = 0) -> models.ShareToken:
    token = session.save(Q.share_token.create(owner=owner, time_valid_min=60, paths=paths), flush=True)
    token.created_utc = datetime.now(timezone.utc) - timedelta(minutes=age_min)
    session.save(token)
    session.commit()
    return token


def _table(client: TestClient, token: str, **params):
    return get(client, "/htmx/admin/share-tokens", token, htmx=True, params=params)


def _row(html: str, share_token: models.ShareToken) -> str:
    start = html.index(f'id="share_token-{share_token.uuid}"')
    return html[start:html.index("</tr>", start)]


def _save(client: TestClient, share_token: models.ShareToken, token: str, add: list[str] = (), remove: list[str] = ()):
    fields = {f"add-{i}": p for i, p in enumerate(add)} | {f"remove-{i}": p for i, p in enumerate(remove)}
    return post_form(client, f"/htmx/admin/share-tokens/{share_token.uuid}/paths", fields, token, htmx=True)


def _paths(session: SyncSession, share_token: models.ShareToken) -> set[str]:
    session.expire_all()
    return {p.path for p in session.get_one(Q.share_token.select(uuid=share_token.uuid)).paths}


def test_admin_sees_shares_newest_first(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    old = _share(session, user, ["BSF_PROJECTS/P1"], age_min=60)
    new = _share(session, user, ["BSF_PROJECTS/P2/c.txt"])

    assert get(client, "/admin/shares", admin_token).status_code == 200

    response = _table(client, admin_token)
    assert response.status_code == 200
    assert response.text.index(new.uuid) < response.text.index(old.uuid)
    assert user.name in _row(response.text, new)
    assert "BSF_PROJECTS/P1" in _row(response.text, old)
    assert "BSF_PROJECTS/P2/c.txt" in _row(response.text, new)


def test_sizes_from_the_index(client: TestClient, session: SyncSession, admin_token: str, user: models.User, index: Path):
    # a path inside another one is listed but not counted twice
    nested = _share(session, user, ["BSF_PROJECTS/P1", "BSF_PROJECTS/P1/a.txt", "BSF_PROJECTS/P2/c.txt"])
    partial = _share(session, user, ["BSF_PROJECTS/P2", "BSF_PROJECTS/P3"])

    html = _table(client, admin_token).text
    row = _row(html, nested)
    assert "1500 B" not in row and "1.46 KB" in row  # 1000 + 500
    assert "400 B" in row
    row = _row(html, partial)
    assert "≥ 500 B" in row
    assert "?" in row


def test_sizes_without_index(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    assert "—" in _row(_table(client, admin_token).text, share)


def test_project_released_with_the_share(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    project = session.save(Q.project.create(title="released", description="d", owner_id=user.id), flush=True)
    project.share_token_uuid = share.uuid
    session.save(project)
    session.commit()
    assert f"/projects/{project.id}" in _row(_table(client, admin_token).text, share)


def test_expire(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    # cached by the share routes
    assert client.get(f"/api/shares/browse/{share.uuid}").status_code == 200
    assert Redis(connection_pool=client.app.state.redis_pool).get(f"share-token:{share.uuid}") is not None

    response = post_form(client, f"/htmx/admin/share-tokens/{share.uuid}/expire", {}, admin_token, htmx=True)
    assert response.status_code == 200
    assert "revoked" in response.text
    assert f'id="share_token-{share.uuid}"' in response.text

    session.expire_all()
    assert session.get_one(Q.share_token.select(uuid=share.uuid))._expired
    assert client.get(f"/api/shares/browse/{share.uuid}").status_code == 403


def test_expire_unknown_token(client: TestClient, admin_token: str):
    assert post_form(client, "/htmx/admin/share-tokens/does-not-exist/expire", {}, admin_token, htmx=True).status_code == 404


def test_picker_ticks_the_share_paths(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1", "BSF_PROJECTS/P2/c.txt"])
    response = get(client, f"/htmx/admin/share-tokens/{share.uuid}/paths", admin_token, htmx=True)
    assert response.status_code == 200
    assert "BSF_PROJECTS/P1" in response.text and "BSF_PROJECTS/P2/c.txt" in response.text
    assert f"/htmx/admin/share-tokens/{share.uuid}/paths" in response.text


def test_edit_paths(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1/a.txt", "BSF_PROJECTS/P1/b.txt"])
    # cached with its old paths
    assert client.get(f"/api/shares/browse/{share.uuid}/BSF_PROJECTS/P1/b.txt").status_code == 200

    response = _save(client, share, admin_token, add=["BSF_PROJECTS/P2"], remove=["BSF_PROJECTS/P1/b.txt"])
    assert response.status_code == 204
    assert response.headers["HX-Redirect"].endswith("/admin/shares")
    assert _paths(session, share) == {"BSF_PROJECTS/P1/a.txt", "BSF_PROJECTS/P2"}

    assert client.get(f"/api/shares/browse/{share.uuid}/BSF_PROJECTS/P1/b.txt").status_code != 200
    assert client.get(f"/api/shares/browse/{share.uuid}/BSF_PROJECTS/P2/c.txt").status_code == 200


def test_ticked_folder_replaces_the_paths_inside(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1/a.txt", "BSF_PROJECTS/P2"])
    assert _save(client, share, admin_token, add=["BSF_PROJECTS/P1"]).status_code == 204
    assert _paths(session, share) == {"BSF_PROJECTS/P1", "BSF_PROJECTS/P2"}


@pytest.mark.parametrize("path", ["BSF_PROJECTS/missing", "../outside", "/etc"])
def test_edit_paths_rejects_bad_paths(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path, path: str):
    (share_root.parent / "outside").mkdir(exist_ok=True)
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    response = _save(client, share, admin_token, add=["BSF_PROJECTS/P2", path], remove=["BSF_PROJECTS/P1"])
    assert response.status_code == 400
    assert _paths(session, share) == {"BSF_PROJECTS/P1"}


def test_edit_paths_keeps_at_least_one(client: TestClient, session: SyncSession, admin_token: str, user: models.User, share_root: Path):
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    assert _save(client, share, admin_token, remove=["BSF_PROJECTS/P1"]).status_code == 400
    assert _paths(session, share) == {"BSF_PROJECTS/P1"}


@pytest.mark.parametrize("token", ["user_token", "insider_token"])
def test_only_admins(client: TestClient, session: SyncSession, user: models.User, share_root: Path, token: str, request):
    login = request.getfixturevalue(token)
    share = _share(session, user, ["BSF_PROJECTS/P1"])
    assert get(client, "/admin/shares", login).status_code in (302, 303, 403)
    assert _table(client, login).status_code == 403
    assert get(client, f"/htmx/admin/share-tokens/{share.uuid}/paths", login, htmx=True).status_code == 403
    assert post_form(client, f"/htmx/admin/share-tokens/{share.uuid}/expire", {}, login, htmx=True).status_code == 403
    assert _save(client, share, login, add=["BSF_PROJECTS/P2"]).status_code == 403
    assert _paths(session, share) == {"BSF_PROJECTS/P1"}
    session.expire_all()
    assert not session.get_one(Q.share_token.select(uuid=share.uuid))._expired
