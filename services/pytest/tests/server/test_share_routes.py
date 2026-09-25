from dataclasses import dataclass
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from fastapi.testclient import TestClient
from opengsync_db import SyncSession, models, queries as Q
from redis import Redis

from server.core import config, dependencies


@dataclass(frozen=True)
class ShareFixture:
    token: models.ShareToken
    root: Path


@pytest.fixture
def share_fixture(
    session: SyncSession,
    user: models.User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ShareFixture:
    share_root = tmp_path / "share"
    shared = share_root / "shared"
    nested = shared / "nested"
    nested.mkdir(parents=True)
    (shared / "root.txt").write_text("root")
    (nested / "child.txt").write_text("child")
    (share_root / "unshared.txt").write_text("private")
    (shared / ".DS_Store").write_text("junk")

    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(share_root)
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    try:
        token = session.save(Q.share_token.create(
            owner=user,
            time_valid_min=60,
            paths=["shared"],
        ), flush=True)
        session.commit()
        yield ShareFixture(token=token, root=share_root)
    finally:
        config.settings.app_config.share_root = original_share_root


def test_public_share_routes(
    client: TestClient,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid

    validate = client.get(f"/api/shares/validate/{token}")
    assert validate.status_code == 200
    assert validate.text == "OK"

    browse = client.get(f"/api/shares/browse/{token}")
    assert browse.status_code == 200
    assert "shared/" in browse.text
    assert ".DS_Store" not in browse.text

    shared = client.get(f"/api/shares/browse/{token}/shared")
    assert shared.status_code == 200
    assert "root.txt" in shared.text
    assert "nested/" in shared.text

    nested = client.get(f"/api/shares/browse/{token}/shared/nested")
    assert nested.status_code == 200
    assert "child.txt" in nested.text

    file_response = client.get(f"/api/shares/browse/{token}/shared/root.txt")
    assert file_response.status_code == 200
    assert file_response.content == b"root"

    rclone = client.get(f"/api/shares/rclone/{token}")
    assert rclone.status_code == 200
    assert "shared/" in rclone.text

    rclone_script = client.get(f"/api/shares/rclone_script/{token}")
    assert rclone_script.status_code == 200
    assert "rclone copy" in rclone_script.text


def test_shared_browser_page_and_entries(
    client: TestClient,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid

    page = client.get(f"/files/share/browse/{token}")
    assert page.status_code == 200
    assert 'id="file-browser-root"' in page.text
    assert "Shared Files" in page.text

    entries = client.get(f"/files/share/browse/{token}/entries/shared")
    assert entries.status_code == 200
    assert "root.txt" in entries.text
    assert "nested/" in entries.text
    assert ".DS_Store" not in entries.text

    invalid_sort = client.get(
        f"/files/share/browse/{token}/entries/shared",
        params={"sort_by": "invalid", "sort_order": "invalid"},
    )
    assert invalid_sort.status_code == 200
    assert "root.txt" in invalid_sort.text

    assert client.get(
        f"/files/share/browse/{token}/entries/shared",
        params={"page": -1},
    ).status_code == 422

    file_response = client.get(f"/files/share/browse/{token}/shared/root.txt")
    assert file_response.status_code == 200
    assert file_response.content == b"root"


def test_share_routes_reject_invalid_expired_and_unshared_paths(
    client: TestClient,
    session: SyncSession,
    user: models.User,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid

    assert client.get("/api/shares/validate/not-a-token").status_code == 404
    unshared = client.get(f"/api/shares/browse/{token}/unshared.txt")
    assert unshared.status_code == 200
    assert "private" not in unshared.text

    expired = session.save(Q.share_token.create(
        owner=user,
        time_valid_min=60,
        paths=["shared"],
    ), flush=True)
    expired._expired = True
    session.save(expired)
    session.commit()

    assert client.get(f"/api/shares/validate/{expired.uuid}").status_code == 403
    assert client.get(f"/files/share/browse/{expired.uuid}").status_code == 403
    assert client.get(f"/api/webdav/{expired.uuid}").status_code == 403


def test_webdav_methods_and_file_metadata(
    client: TestClient,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid
    root_url = f"/api/webdav/{token}/shared"
    file_url = f"{root_url}/root.txt"

    options = client.options(root_url)
    assert options.status_code == 200
    assert options.headers["DAV"] == "1, 2"
    assert "PROPFIND" in options.headers["Allow"]

    propfind_root = client.request("PROPFIND", root_url, headers={"Depth": "0"})
    assert propfind_root.status_code == 207
    assert "application/xml" in propfind_root.headers["content-type"]
    assert "root.txt" not in propfind_root.text

    propfind_children = client.request("PROPFIND", root_url, headers={"Depth": "1"})
    assert propfind_children.status_code == 207
    assert "root.txt" in propfind_children.text
    assert "nested/" in propfind_children.text
    assert "<D:getcontentlength>4</D:getcontentlength>" in propfind_children.text
    assert ".DS_Store" not in propfind_children.text

    head = client.head(file_url)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers.get("content-length") in (None, "0")
    assert "ETag" in head.headers

    get_file = client.get(file_url)
    assert get_file.status_code == 200
    assert get_file.content == b"root"

    assert client.request("LOCK", root_url).status_code == 204
    assert client.request("UNLOCK", root_url).status_code == 204


def test_webdav_rejects_invalid_junk_and_unshared_paths(
    client: TestClient,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid

    assert client.get("/api/webdav/not-a-token").status_code == 404
    assert client.get(f"/api/webdav/{token}/shared/.DS_Store").status_code == 404
    assert client.get(f"/api/webdav/{token}/unshared.txt").status_code == 404


def test_share_and_webdav_listing_cache_returns_identical_response(
    client: TestClient,
    share_fixture: ShareFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "prod")
    token = share_fixture.token.uuid
    redis = Redis(connection_pool=client.app.state.redis_pool)

    browse_url = f"/api/shares/browse/{token}"
    assert not list(redis.scan_iter(match=f"share-fs:{token}:list:*"))
    first_browse = client.get(browse_url)
    assert first_browse.status_code == 200
    assert list(redis.scan_iter(match=f"share-fs:{token}:list:*"))
    assert redis.get(f"share-token:{token}") is not None

    (share_fixture.root / "shared" / "root.txt").unlink()
    with patch.object(type(dependencies.ctx), "session", new_callable=PropertyMock) as session:
        session.side_effect = AssertionError("database session accessed on cache hit")
        second_browse = client.get(browse_url)

    assert second_browse.status_code == 200
    assert second_browse.content == first_browse.content

    propfind_url = f"/api/webdav/{token}/shared"
    first_propfind = client.request("PROPFIND", propfind_url, headers={"Depth": "1"})
    assert first_propfind.status_code == 207
    assert list(redis.scan_iter(match=f"share-fs:{token}:propfind:*"))

    (share_fixture.root / "shared" / "nested" / "child.txt").unlink()
    second_propfind = client.request("PROPFIND", propfind_url, headers={"Depth": "1"})
    assert second_propfind.status_code == 207
    assert second_propfind.content == first_propfind.content


def test_share_access_audit_is_debounced_per_token(
    client: TestClient,
    share_fixture: ShareFixture,
):
    token = share_fixture.token.uuid
    redis = Redis(connection_pool=client.app.state.redis_pool)
    assert not list(redis.scan_iter(match=f"share-audit:{token}:*"))

    assert client.get(f"/api/shares/browse/{token}").status_code == 200
    keys = list(redis.scan_iter(match=f"share-audit:{token}:*"))
    assert len(keys) == 1

    assert client.get(f"/api/shares/browse/{token}/shared").status_code == 200
    assert client.get(f"/api/webdav/{token}/shared/root.txt").status_code == 200
    assert client.get(f"/files/share/browse/{token}").status_code == 200
    assert list(redis.scan_iter(match=f"share-audit:{token}:*")) == keys
