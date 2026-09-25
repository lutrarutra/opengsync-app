""".ngsignore: gitignore-style files that hide paths from share links.

`ShareIgnore` is tested directly for the matching rules; the public share routes are
tested for enforcement (listings, direct access, the curl script); the insider file
browser must be unaffected.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from server.core import config
from server.utils import share_ignore
from server.utils.share_ignore import IGNORE_FILENAME, ShareIgnore

from ._http import get
from .test_share_root_abuse import PUBLIC_ROUTES, _public


# ── ShareIgnore rules ───────────────────────────────────────────────────────


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "share"
    root.mkdir()
    return root


def make(root: Path, tree: dict[str, str | None]) -> Callable[[str], bool]:
    """Create `tree` under root (None = directory); return a root-relative `is_ignored`."""
    for rel, content in tree.items():
        path = root / rel
        if content is None:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    ignore = ShareIgnore(root)
    return lambda rel: ignore.is_ignored(root / rel)


def test_unanchored_pattern_matches_at_any_depth(root: Path):
    ignored = make(root, {IGNORE_FILENAME: "*.bam\n", "a.bam": "", "sub/deep/b.bam": "", "a.txt": ""})
    assert ignored("a.bam")
    assert ignored("sub/deep/b.bam")
    assert not ignored("a.txt")


def test_anchored_pattern_is_relative_to_ignore_file(root: Path):
    ignored = make(root, {
        f"sub/{IGNORE_FILENAME}": "/report.txt\nraw/*.fq\n",
        "sub/report.txt": "", "sub/deeper/report.txt": "", "report.txt": "",
        "sub/raw/a.fq": "", "sub/x/raw/a.fq": "",
    })
    assert ignored("sub/report.txt")
    assert not ignored("sub/deeper/report.txt")
    assert not ignored("report.txt")
    assert ignored("sub/raw/a.fq")
    assert not ignored("sub/x/raw/a.fq")


def test_directory_only_pattern(root: Path):
    ignored = make(root, {IGNORE_FILENAME: "tmp/\n", "tmp/secret.txt": "", "sub/tmp": None, "other/tmp": ""})
    assert ignored("tmp")
    assert ignored("tmp/secret.txt")
    assert ignored("sub/tmp")
    assert not ignored("other/tmp"), "a file named like a dir-only pattern is not ignored"


def test_double_star(root: Path):
    ignored = make(root, {
        IGNORE_FILENAME: "raw/**/*.fastq.gz\n",
        "raw/r1.fastq.gz": "", "raw/a/b/r2.fastq.gz": "", "raw/a/r.txt": "", "other/r3.fastq.gz": "",
    })
    assert ignored("raw/r1.fastq.gz")
    assert ignored("raw/a/b/r2.fastq.gz")
    assert not ignored("raw/a/r.txt")
    assert not ignored("other/r3.fastq.gz")


def test_negation_in_same_file(root: Path):
    ignored = make(root, {IGNORE_FILENAME: "*.bam\n!keep.bam\n", "a.bam": "", "keep.bam": "", "sub/keep.bam": ""})
    assert ignored("a.bam")
    assert not ignored("keep.bam")
    assert not ignored("sub/keep.bam")


def test_nested_ignore_file_applies_only_to_its_subtree(root: Path):
    ignored = make(root, {f"a/{IGNORE_FILENAME}": "*.log\n", "a/x.log": "", "a/deep/y.log": "", "b/x.log": "", "x.log": ""})
    assert ignored("a/x.log")
    assert ignored("a/deep/y.log")
    assert not ignored("b/x.log")
    assert not ignored("x.log")


def test_nearest_ignore_file_wins(root: Path):
    ignored = make(root, {
        IGNORE_FILENAME: "*.bam\n!notes.txt\n",
        f"child/{IGNORE_FILENAME}": "!*.bam\nnotes.txt\n",
        "a.bam": "", "child/a.bam": "", "child/deep/b.bam": "", "notes.txt": "", "child/notes.txt": "",
    })
    assert ignored("a.bam")
    assert not ignored("child/a.bam")
    assert not ignored("child/deep/b.bam")
    assert not ignored("notes.txt")
    assert ignored("child/notes.txt")


def test_ignored_directory_cannot_be_reincluded(root: Path):
    ignored = make(root, {
        IGNORE_FILENAME: "raw/\n!raw/keep.txt\n",
        f"raw/{IGNORE_FILENAME}": "!keep2.txt\n",
        "raw/keep.txt": "", "raw/keep2.txt": "",
    })
    assert ignored("raw/keep.txt")
    assert ignored("raw/keep2.txt")


def test_ignore_files_are_always_hidden(root: Path):
    ignored = make(root, {IGNORE_FILENAME: "", f"sub/{IGNORE_FILENAME}": f"!{IGNORE_FILENAME}\n"})
    assert ignored(IGNORE_FILENAME)
    assert ignored(f"sub/{IGNORE_FILENAME}")


def test_comments_blank_lines_and_invalid_patterns(root: Path):
    ignored = make(root, {
        IGNORE_FILENAME: "# comment\n\n!\n\\#literal\n*.bam\n",
        "a.bam": "", "#literal": "", "# comment": "",
    })
    assert ignored("a.bam"), "an invalid line must not disable the other rules"
    assert ignored("#literal")
    assert not ignored("# comment")


def test_non_utf8_ignore_file(root: Path):
    (root / IGNORE_FILENAME).write_bytes(b"*.bam\n\xff\xfe\n")
    ignored = make(root, {"a.bam": "", "a.txt": ""})
    assert ignored("a.bam")
    assert not ignored("a.txt")


def test_unreadable_ignore_file_hides_its_directory(root: Path, monkeypatch: pytest.MonkeyPatch):
    unreadable = str(root / "sub" / IGNORE_FILENAME)

    def fake_open(file, *args, **kwargs):
        if str(file) == unreadable:
            raise PermissionError(13, "Permission denied", str(file))
        return open(file, *args, **kwargs)

    monkeypatch.setattr(share_ignore, "open", fake_open, raising=False)
    ignored = make(root, {f"sub/{IGNORE_FILENAME}": "", "sub/a.txt": "", "sub/deep/b.txt": "", "other/a.txt": ""})
    assert ignored("sub/a.txt")
    assert ignored("sub/deep/b.txt")
    assert not ignored("other/a.txt")


def test_symlink_to_ignored_target_is_hidden(root: Path):
    ignored = make(root, {IGNORE_FILENAME: "private/\n", "private/data.txt": "", "public": None})
    (root / "public" / "link").symlink_to(root / "private" / "data.txt")
    (root / "public" / "dirlink").symlink_to(root / "private", target_is_directory=True)
    assert ignored("public/link")
    assert ignored("public/dirlink")
    assert ignored("public/dirlink/data.txt")


def test_paths_outside_root_are_not_ignored(root: Path, tmp_path: Path):
    (root / IGNORE_FILENAME).write_text("*\n")
    ignore = ShareIgnore(root)
    assert not ignore.is_ignored(tmp_path / "elsewhere.txt")
    assert not ignore.is_ignored(root / ".." / "elsewhere.txt")
    assert not ignore.is_ignored(root)


# ── Public share routes ─────────────────────────────────────────────────────


IGNORED = "IGNORED-CONTENT"
RULES_MARKER = "ngsignore-rules-marker"  # only appears inside an ignore file
SHARED = "shared report content"
KEPT = "kept"


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Requests `client` so the app config exists before share_root is patched.

    share/                      <- share_root
      .ngsignore                "*.vcf"  (above the shared folder, still applies)
      shared/                   <- the path the share link exposes
        .ngsignore              "*.bam", "hidden-dir/"
        report.txt              SHARED
        sample.bam              IGNORED
        calls.vcf               IGNORED
        hidden-dir/secret.txt   IGNORED
        sub/.ngsignore          "!keep.bam"
        sub/keep.bam            KEPT (re-included)
        link-to-bam     -> sample.bam     hidden: its target is ignored
        link-to-hidden  -> hidden-dir     hidden: its target is ignored
        link-to-report  -> report.txt     visible
        link-to-sub     -> sub            visible
    """
    root = tmp_path / "share"
    shared = root / "shared"
    (shared / "hidden-dir").mkdir(parents=True)
    (shared / "sub").mkdir()
    (root / IGNORE_FILENAME).write_text(f"# {RULES_MARKER}\n*.vcf\n")
    (shared / IGNORE_FILENAME).write_text(f"# {RULES_MARKER}\n*.bam\nhidden-dir/\n")
    (shared / "report.txt").write_text(SHARED)
    (shared / "sample.bam").write_text(IGNORED)
    (shared / "calls.vcf").write_text(IGNORED)
    (shared / "hidden-dir" / "secret.txt").write_text(IGNORED)
    (shared / "sub" / IGNORE_FILENAME).write_text(f"# {RULES_MARKER}\n!keep.bam\n")
    (shared / "sub" / "keep.bam").write_text(KEPT)
    (shared / "link-to-bam").symlink_to(shared / "sample.bam")
    (shared / "link-to-hidden").symlink_to(shared / "hidden-dir", target_is_directory=True)
    (shared / "link-to-report").symlink_to(shared / "report.txt")
    (shared / "link-to-sub").symlink_to(shared / "sub", target_is_directory=True)

    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "test")
    return root


@pytest.fixture
def share_link(session: SyncSession, user: models.User, share_root: Path) -> str:
    token = session.save(Q.share_token.create(owner=user, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()
    return token.uuid


HIDDEN_NAMES = ["sample.bam", "calls.vcf", "hidden-dir", "secret.txt", "link-to-bam", "link-to-hidden", IGNORE_FILENAME]

# (id, ignored path, the same path form at a visible file or None, kind): "file" targets content,
# "dir" targets a listing. Manipulated forms are percent-encoded because HTTP clients normalise
# literal "." and "..", but the server decodes them back before routing.
TARGETS = [
    ("direct", "shared/sample.bam", "shared/report.txt", "file"),
    ("rule-above-share", "shared/calls.vcf", None, "file"),
    ("in-ignored-dir", "shared/hidden-dir/secret.txt", "shared/sub/keep.bam", "file"),
    ("ignore-file", f"shared/{IGNORE_FILENAME}", None, "file"),
    ("encoded-dotdot", "shared/sub/%2e%2e/sample.bam", "shared/sub/%2e%2e/report.txt", "file"),
    ("encoded-slash-dotdot", "shared/sub/..%2fsample.bam", "shared/sub/..%2freport.txt", "file"),
    ("encoded-dot", "shared/%2e/sample.bam", "shared/%2e/report.txt", "file"),
    ("double-slash", "shared//sample.bam", "shared//report.txt", "file"),
    ("trailing-slash", "shared/sample.bam/", "shared/report.txt/", "file"),
    ("encoded-slash", "shared/hidden-dir%2fsecret.txt", "shared/sub%2fkeep.bam", "file"),
    ("dotdot-into-ignored-dir", "shared/sub/%2e%2e/hidden-dir/secret.txt", "shared/sub/%2e%2e/sub/keep.bam", "file"),
    ("dotdot-to-ignore-file", f"shared/sub/%2e%2e/%2e%2e/shared/{IGNORE_FILENAME}", None, "file"),
    ("symlink-to-ignored-file", "shared/link-to-bam", "shared/link-to-report", "file"),
    ("via-symlink-to-ignored-dir", "shared/link-to-hidden/secret.txt", "shared/link-to-sub/keep.bam", "file"),
    ("ignored-dir", "shared/hidden-dir", None, "dir"),
    ("symlink-to-ignored-dir", "shared/link-to-hidden", None, "dir"),
]


def _cases(with_control: bool):
    return [
        pytest.param(method, route, control if with_control else path, kind, id=f"{rid}-{tid}")
        for rid, method, route, kinds in PUBLIC_ROUTES
        for tid, path, control, kind in TARGETS
        if kind in kinds and (control is not None or not with_control)
    ]


@pytest.mark.parametrize("method,route,path,kind", _cases(with_control=False))
def test_public_share_refuses_ignored_paths(
    client: TestClient, share_link: str, method: str, route: str, path: str, kind: str,
):
    response = _public(client, method, route, share_link, path)
    assert IGNORED not in response.text, f"ignored file content leaked ({response.status_code})"
    assert RULES_MARKER not in response.text, "ignore file content leaked"
    assert "content-disposition" not in response.headers, "a file was served"
    if kind == "dir":
        assert "secret.txt" not in response.text, "ignored directory was listed"
    if route.startswith("/api/webdav"):
        # same as a missing file, so the response does not reveal that the file exists
        assert response.status_code == 404
        assert "<D:response>" not in response.text


@pytest.mark.parametrize("method,route,path,kind", _cases(with_control=True))
def test_public_share_serves_visible_file_through_same_path_form(
    client: TestClient, share_link: str, method: str, route: str, path: str, kind: str,
):
    """The path forms above do reach files, so the refusals are down to the ignore rules."""
    response = _public(client, method, route, share_link, path)
    if method == "GET":
        assert response.status_code == 200, response.text
        assert response.text in (SHARED, KEPT)
    elif method == "HEAD":
        assert response.status_code == 200
    else:
        assert response.status_code == 207, response.text
        assert "<D:response>" in response.text


@pytest.mark.parametrize("method,route", [pytest.param(m, r, id=rid) for rid, m, r, kinds in PUBLIC_ROUTES if "dir" in kinds])
def test_public_share_listing_hides_ignored_entries(client: TestClient, share_link: str, method: str, route: str):
    shared = _public(client, method, route, share_link, "shared")
    assert shared.status_code in (200, 207), shared.text
    assert "report.txt" in shared.text
    assert "link-to-report" in shared.text
    assert "sub" in shared.text
    for name in HIDDEN_NAMES:
        assert name not in shared.text, name

    sub = _public(client, method, route, share_link, "shared/sub")
    assert sub.status_code in (200, 207), sub.text
    assert "keep.bam" in sub.text, "a nested !pattern re-includes the file"
    assert IGNORE_FILENAME not in sub.text


def test_insider_file_browser_ignores_ngsignore(client: TestClient, insider_token: str, share_root: Path):
    response = get(client, "/htmx/files/shared", insider_token)
    assert response.status_code == 200
    for name in ["report.txt", "sample.bam", "calls.vcf", "hidden-dir", IGNORE_FILENAME]:
        assert name in response.text, name
