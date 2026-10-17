"""ShareDirectoryAction: share a directory under the share root by email.

As legacy ``DirectoryShareForm``: insider-only; the path must be an existing directory inside
the share root; each submit creates a new share token with the chosen validity and emails the
browse link to the (deduplicated) recipients, naming the sender unless "Anonymous Send" is set.

Traversal/symlink escapes, the basic share and invalid recipients are in ``test_share_root_abuse.py``.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from server.core import config
from server.forms.actions.ShareDirectoryAction import TIME_VALID_CHOICES

from .._http import assert_flash, assert_form_invalid, get, post_form

PATH = "/htmx/files/share-directory"


@pytest.fixture
def share_root(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """share/ with a directory ``results/`` and a file ``notes.txt``."""
    root = tmp_path / "share"
    (root / "results").mkdir(parents=True)
    (root / "notes.txt").write_text("notes")
    monkeypatch.setattr(config.settings.app_config, "share_root", str(root))
    return root


def _share(client: TestClient, token: str, directory_path: str = "results", recipients=("a@example.com",), **fields: str):
    return post_form(client, PATH, {
        "directory_path": directory_path,
        **{f"recipients-{i}-email": email for i, email in enumerate(recipients)},
        "time_valid_min": str(TIME_VALID_CHOICES[0][0]),
        **fields,
    }, token=token)


def _tokens(session: SyncSession, user: models.User) -> list[models.ShareToken]:
    session.expire_all()
    return session.get_all(Q.share_token.select(owner_id=user.id), limit=None)


def test_render_prefills_the_path(client: TestClient, insider_token: str, share_root: Path):
    response = get(client, PATH, insider_token, params={"path": "results"})

    assert response.status_code == 200, response.text
    assert 'value="results"' in response.text
    assert 'name="recipients-0-email"' in response.text


def test_client_is_denied(client: TestClient, session: SyncSession, user, user_token: str, fake_mailer, share_root: Path):
    assert get(client, PATH, user_token, params={"path": "results"}).status_code == 403
    assert _share(client, user_token).status_code == 403
    assert _tokens(session, user) == []
    assert fake_mailer.sent == []


@pytest.mark.parametrize("minutes", [minutes for minutes, _ in TIME_VALID_CHOICES])
def test_each_validity_period_is_stored_on_the_token(
    client: TestClient, session: SyncSession, insider, insider_token: str, fake_mailer, share_root: Path, minutes: int,
):
    response = _share(client, insider_token, time_valid_min=str(minutes))

    assert response.status_code in (200, 204), response.text
    assert_flash(response, "Email Sent!", "success")
    [token] = _tokens(session, insider)
    assert token.time_valid_min == minutes
    assert not token.is_expired


@pytest.mark.parametrize("minutes", ["999", "-1", "abc"])
def test_validity_outside_the_choices_is_rejected(
    client: TestClient, session: SyncSession, insider, insider_token: str, fake_mailer, share_root: Path, minutes: str,
):
    response = _share(client, insider_token, time_valid_min=minutes)

    assert_form_invalid(response)
    assert _tokens(session, insider) == []
    assert fake_mailer.sent == []


def test_sharing_the_same_directory_twice_creates_two_valid_tokens(
    client: TestClient, session: SyncSession, insider, insider_token: str, fake_mailer, share_root: Path,
):
    """As legacy: an earlier directory share is not expired by a new one."""
    _share(client, insider_token)
    _share(client, insider_token)

    tokens = _tokens(session, insider)
    assert len(tokens) == 2
    assert len({token.uuid for token in tokens}) == 2
    assert all(not token.is_expired and [p.path for p in token.paths] == ["results"] for token in tokens)
    assert len(fake_mailer.sent) == 2


def test_duplicate_recipients_get_one_email(client: TestClient, insider_token: str, fake_mailer, share_root: Path):
    _share(client, insider_token, recipients=("a@example.com", "b@example.com", "a@example.com"))

    [sent] = fake_mailer.sent
    assert sorted(sent["kwargs"]["recipients"]) == ["a@example.com", "b@example.com"]


@pytest.mark.parametrize("anonymous", [True, False])
def test_anonymous_send_hides_the_sender(
    client: TestClient, insider, insider_token: str, fake_mailer, share_root: Path, anonymous: bool,
):
    fields = {"anonymous_send": "true"} if anonymous else {}

    _share(client, insider_token, **fields)

    [sent] = fake_mailer.sent
    author = sent["kwargs"]["author"]
    assert (author is None) if anonymous else (author.id == insider.id)


def test_browse_link_points_to_the_new_token(
    client: TestClient, session: SyncSession, insider, insider_token: str, fake_mailer, share_root: Path,
):
    _share(client, insider_token)

    [token] = _tokens(session, insider)
    [sent] = fake_mailer.sent
    assert token.uuid in sent["kwargs"]["browse_link"]


@pytest.mark.parametrize("directory_path, error", [
    ("notes.txt", "must be a directory"),
    ("missing", "does not exist"),
    ("", None),
])
def test_file_missing_or_empty_path_is_rejected(
    client: TestClient, session: SyncSession, insider, insider_token: str, fake_mailer, share_root: Path,
    directory_path: str, error: str | None,
):
    response = _share(client, insider_token, directory_path=directory_path)

    assert_form_invalid(response, error)
    assert _tokens(session, insider) == []
    assert fake_mailer.sent == []
