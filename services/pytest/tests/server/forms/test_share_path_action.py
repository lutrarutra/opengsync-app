"""SharePathAction: share files and folders under the share root by email.

As legacy ``DirectoryShareForm``, extended to several paths: bioinformatician-only; every path must exist
inside the share root (files and folders alike); each submit creates one new share token holding
all paths, with nested and duplicate paths collapsed, and emails the browse link to the
(deduplicated) recipients, naming the sender unless "Anonymous Send" is set.

Traversal/symlink escapes, the basic share and invalid recipients are in ``test_share_root_abuse.py``.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from server.core import config
from server.forms.actions.SharePathAction import TIME_VALID_CHOICES, MAX_SHARE_PATH_LENGTH
from server.utils.file_browser import MAX_SELECTED_PATHS

from .._http import assert_flash, assert_form_invalid, get, post_form

PATH = "/htmx/files/share-path"


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """share/ with a directory ``results/`` (containing ``sub/``) and a file ``notes.txt``."""
    root = tmp_path / "share"
    (root / "results" / "sub").mkdir(parents=True)
    (root / "notes.txt").write_text("notes")
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    return root


def _share(client: TestClient, token: str, paths=("results",), recipients=("a@example.com",), **fields: str):
    return post_form(client, PATH, {
        **{f"paths-{i}-path": path for i, path in enumerate(paths)},
        **{f"recipients-{i}-email": email for i, email in enumerate(recipients)},
        "time_valid_min": str(TIME_VALID_CHOICES[0][0]),
        **fields,
    }, token=token)


def _tokens(session: SyncSession, user: models.User) -> list[models.ShareToken]:
    session.expire_all()
    return session.get_all(Q.share_token.select(owner_id=user.id), limit=None)


def test_render_prefills_the_paths(client: TestClient, bioinformatician_token: str, share_root: Path):
    response = get(client, PATH, bioinformatician_token, params=[("path", "results"), ("path", "notes.txt"), ("path", "results")])

    assert response.status_code == 200, response.text
    # one removable row per path, sorted, duplicates dropped
    assert '<input type="hidden" id="paths-0-path" name="paths-0-path" value="notes.txt">' in response.text
    assert '<input type="hidden" id="paths-1-path" name="paths-1-path" value="results">' in response.text
    assert 'name="paths-2-path"' not in response.text
    assert response.text.count('class="selected-path-remove"') == 2
    assert "not listed" not in response.text
    assert 'name="recipients-0-email"' in response.text


def test_render_leaves_out_paths_inside_a_selected_folder(client: TestClient, bioinformatician_token: str, share_root: Path):
    response = get(client, PATH, bioinformatician_token, params=[("path", "results/sub"), ("path", "results"), ("path", "notes.txt")])

    assert response.status_code == 200, response.text
    assert 'value="results"' in response.text
    assert 'value="notes.txt"' in response.text
    assert 'value="results/sub"' not in response.text
    assert "1 selected path is not listed: already included in a listed folder." in response.text


@pytest.mark.parametrize("from_selection", [True, False])
def test_share_from_the_selection_panel_clears_it(
    client: TestClient, bioinformatician_token: str, share_root: Path, from_selection: bool,
):
    params = [("path", "results")] + ([("from_selection", "true")] if from_selection else [])

    response = get(client, PATH, bioinformatician_token, params=params)

    assert response.status_code == 200, response.text
    assert ("pathSelection?.clear()" in response.text) == from_selection


def test_client_is_denied(client: TestClient, session: SyncSession, user, user_token: str, fake_mailer, share_root: Path):
    assert get(client, PATH, user_token, params={"path": "results"}).status_code == 403
    assert _share(client, user_token).status_code == 403
    assert _tokens(session, user) == []
    assert fake_mailer.sent == []


@pytest.mark.parametrize("minutes", [minutes for minutes, _ in TIME_VALID_CHOICES])
def test_each_validity_period_is_stored_on_the_token(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path, minutes: int,
):
    response = _share(client, bioinformatician_token, time_valid_min=str(minutes))

    assert response.status_code in (200, 204), response.text
    assert_flash(response, "Email Sent!", "success")
    [token] = _tokens(session, bioinformatician)
    assert token.time_valid_min == minutes
    assert not token.is_expired


@pytest.mark.parametrize("minutes", ["999", "-1", "abc"])
def test_validity_outside_the_choices_is_rejected(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path, minutes: str,
):
    response = _share(client, bioinformatician_token, time_valid_min=minutes)

    assert_form_invalid(response)
    assert _tokens(session, bioinformatician) == []
    assert fake_mailer.sent == []


def test_sharing_the_same_directory_twice_creates_two_valid_tokens(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    """As legacy: an earlier directory share is not expired by a new one."""
    _share(client, bioinformatician_token)
    _share(client, bioinformatician_token)

    tokens = _tokens(session, bioinformatician)
    assert len(tokens) == 2
    assert len({token.uuid for token in tokens}) == 2
    assert all(not token.is_expired and [p.path for p in token.paths] == ["results"] for token in tokens)
    assert len(fake_mailer.sent) == 2


def test_duplicate_recipients_get_one_email(client: TestClient, bioinformatician_token: str, fake_mailer, share_root: Path):
    _share(client, bioinformatician_token, recipients=("a@example.com", "b@example.com", "a@example.com"))

    [sent] = fake_mailer.sent
    assert sorted(sent["kwargs"]["recipients"]) == ["a@example.com", "b@example.com"]


@pytest.mark.parametrize("anonymous", [True, False])
def test_anonymous_send_hides_the_sender(
    client: TestClient, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path, anonymous: bool,
):
    fields = {"anonymous_send": "true"} if anonymous else {}

    _share(client, bioinformatician_token, **fields)

    [sent] = fake_mailer.sent
    author = sent["kwargs"]["author"]
    assert (author is None) if anonymous else (author.id == bioinformatician.id)


def test_browse_link_points_to_the_new_token(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    _share(client, bioinformatician_token)

    [token] = _tokens(session, bioinformatician)
    [sent] = fake_mailer.sent
    assert token.uuid in sent["kwargs"]["browse_link"]


@pytest.mark.parametrize("paths, error", [
    (("missing",), "No longer exists on the share"),
    (("",), None),
    ((".",), "share root itself"),
    ((), "At least 1"),
])
def test_missing_empty_or_root_path_is_rejected(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
    paths: tuple[str, ...], error: str | None,
):
    response = _share(client, bioinformatician_token, paths=paths)

    assert_form_invalid(response, error)
    assert _tokens(session, bioinformatician) == []
    assert fake_mailer.sent == []


def test_shares_a_single_file(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    response = _share(client, bioinformatician_token, paths=("notes.txt",))

    assert response.status_code in (200, 204), response.text
    [token] = _tokens(session, bioinformatician)
    assert [p.path for p in token.paths] == ["notes.txt"]
    assert len(fake_mailer.sent) == 1


def test_shares_files_and_directories_in_one_token(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    response = _share(client, bioinformatician_token, paths=("results", "notes.txt"))

    assert response.status_code in (200, 204), response.text
    [token] = _tokens(session, bioinformatician)
    assert sorted(p.path for p in token.paths) == ["notes.txt", "results"]
    [sent] = fake_mailer.sent
    assert sent["kwargs"]["share_token"].uuid == token.uuid


def test_nested_and_duplicate_paths_are_collapsed(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    _share(client, bioinformatician_token, paths=("results/sub", "results", "results/../results"))

    [token] = _tokens(session, bioinformatician)
    assert [p.path for p in token.paths] == ["results"]


def test_email_lists_every_shared_path(
    client: TestClient, bioinformatician_token: str, share_root: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Rendered by the real Mailer, inside the request, with only the SMTP send replaced."""
    from server.core.mailer import Mailer

    sent: list[dict] = []
    monkeypatch.setattr(Mailer, "_Mailer__send_email", lambda self, **kwargs: sent.append(kwargs))
    monkeypatch.setattr(Mailer, "_get_email_style", lambda self: "")
    monkeypatch.setattr(client.app.state, "mailer", Mailer())

    response = _share(client, bioinformatician_token, paths=("results", "notes.txt"))

    assert response.status_code in (200, 204), response.text
    [email] = sent
    assert email["subject"].endswith("Shared Data with You")
    assert "<code>notes.txt</code>" in email["body"]
    assert "<code>results</code>" in email["body"]


def test_each_invalid_path_reports_its_own_error(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    """One bad path rejects the whole share, and the error is shown on that path's row."""
    response = _share(client, bioinformatician_token, paths=("results", "missing"))

    assert_form_invalid(response, "No longer exists on the share")
    assert 'id="paths-1-path"' in response.text
    assert response.text.count("No longer exists on the share") == 1
    assert _tokens(session, bioinformatician) == []
    assert fake_mailer.sent == []


def test_too_many_paths_is_rejected(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    for i in range(MAX_SELECTED_PATHS + 1):
        (share_root / f"file-{i}.txt").write_text("")

    response = _share(client, bioinformatician_token, paths=[f"file-{i}.txt" for i in range(MAX_SELECTED_PATHS + 1)])

    assert_form_invalid(response, f"At most {MAX_SELECTED_PATHS} paths")
    assert _tokens(session, bioinformatician) == []
    assert fake_mailer.sent == []


def test_path_longer_than_the_share_path_column_is_rejected(
    client: TestClient, session: SyncSession, bioinformatician, bioinformatician_token: str, fake_mailer, share_root: Path,
):
    """SharePath.path holds 512 characters: a longer path is a form error, not a database error."""
    deep = share_root
    while len(deep.relative_to(share_root).as_posix()) <= MAX_SHARE_PATH_LENGTH:
        deep = deep / ("d" * 100)
    deep.mkdir(parents=True)

    response = _share(client, bioinformatician_token, paths=(deep.relative_to(share_root).as_posix(),))

    assert_form_invalid(response, f"longer than {MAX_SHARE_PATH_LENGTH} characters")
    assert _tokens(session, bioinformatician) == []
    assert fake_mailer.sent == []
