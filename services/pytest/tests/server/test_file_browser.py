from pathlib import Path

from fastapi.testclient import TestClient

from server.core import config

from ._http import get


def test_file_browser_renders_list_and_lazy_directory_fragments(
    client: TestClient,
    insider_token: str,
    tmp_path: Path,
):
    share_root = tmp_path / "share"
    nested = share_root / "nested"
    nested.mkdir(parents=True)
    (share_root / "root.txt").write_text("root")
    (nested / "child.txt").write_text("child")

    original_share_root = config.settings.app_config.share_root
    config.settings.app_config.share_root = str(share_root)
    try:
        page = get(client, "/browser/", insider_token)
        assert page.status_code == 200
        assert 'id="file-browser-root"' in page.text
        assert "hx-trigger=\"load\"" in page.text
        assert "<table" not in page.text

        root = get(client, "/htmx/files/", insider_token)
        assert root.status_code == 200
        assert "nested/" in root.text
        assert 'hx-trigger="click once"' in root.text
        assert "browser-children" in root.text

        children = get(client, "/htmx/files/nested", insider_token)
        assert children.status_code == 200
        assert "child.txt" in children.text
    finally:
        config.settings.app_config.share_root = original_share_root
