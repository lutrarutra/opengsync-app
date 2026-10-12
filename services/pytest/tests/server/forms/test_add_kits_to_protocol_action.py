"""AddKitsToProtocolAction: render, access, saving kit combinations, and validation.

As legacy ``add_kits_to_protocol_workflow`` / ``AddKitCombinationsFrom``: insider-only;
the spreadsheet (``Kit`` + ``Combination``) is prefilled with the protocol's current kit
links and submitting replaces them. If no row has a combination number, all rows get
combination 1; otherwise every row needs one. A kit may appear once per combination.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q

from ...db.create_units import create_kit, create_protocol
from .._http import (
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

PREFIX = "/htmx/protocols"
COLUMNS = ["Kit", "Combination"]


def _path(protocol_id: int) -> str:
    return f"{PREFIX}/{protocol_id}/add-kits"


def _label(kit: models.Kit) -> str:
    """The dropdown submits the category label, not the identifier."""
    return f"[{kit.identifier}] {kit.name}"


def _payload(rows: list[tuple[models.Kit | str, Any]]) -> dict[str, str]:
    """Rows of (kit or raw label, combination number or '')."""
    return spreadsheet_payload(COLUMNS, [
        [kit if isinstance(kit, str) else _label(kit), combination] for kit, combination in rows
    ])


def _links(session: SyncSession, protocol: models.Protocol) -> list[tuple[int, int]]:
    """The protocol's kit links as sorted (kit_id, combination_num)."""
    session.expire_all()
    protocol = session.get_one(Q.protocol.select(id=protocol.id))
    return sorted((link.kit_id, link.combination_num) for link in protocol.kit_links)


@pytest.fixture
def kits(session: SyncSession) -> list[models.Kit]:
    return [create_kit(session) for _ in range(3)]


@pytest.fixture
def protocol(session: SyncSession, kits: list[models.Kit]) -> models.Protocol:
    """A protocol with one existing kit link: kits[0] in combination 1."""
    protocol = create_protocol(session)
    protocol.kit_links.append(models.links.ProtocolKitLink(protocol_id=protocol.id, kit_id=kits[0].id, combination_num=1))
    session.save(protocol, flush=True)
    session.commit()
    return protocol


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_lists_kits(client: TestClient, protocol: models.Protocol, kits: list[models.Kit], insider_token: str):
    response = get(client, _path(protocol.id), insider_token)

    assert response.status_code == 200, response.text
    assert "csrf_token" in response.text
    for kit in kits:
        assert _label(kit) in response.text


def test_render_prefills_existing_kit_links(
    client: TestClient, session: SyncSession, kits: list[models.Kit], insider_token: str,
):
    """Legacy prefilled the spreadsheet with Q.pd.protocol_kits; without it a resubmit drops existing links."""
    protocol = create_protocol(session)
    protocol.kit_links.append(models.links.ProtocolKitLink(protocol_id=protocol.id, kit_id=kits[1].id, combination_num=7))
    session.save(protocol, flush=True)
    session.commit()

    response = get(client, _path(protocol.id), insider_token)

    assert response.status_code == 200, response.text
    # The spreadsheet data is embedded as JSON; the linked kit's label is in a data row, not only in the dropdown source.
    assert response.text.count(_label(kits[1])) >= 2
    assert '7' in response.text


def test_render_does_not_change_links(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    get(client, _path(protocol.id), insider_token)
    assert _links(session, protocol) == [(kits[0].id, 1)]


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, protocol: models.Protocol, kits: list[models.Kit], user_token: str):
    assert get(client, _path(protocol.id), user_token).status_code == 403
    assert post_form(client, _path(protocol.id), _payload([(kits[1], 1)]), token=user_token).status_code == 403


def test_client_denied_submit_changes_nothing(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], user_token: str,
):
    post_form(client, _path(protocol.id), _payload([(kits[1], 1)]), token=user_token)
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_client_with_invalid_submission_is_still_denied(client: TestClient, protocol: models.Protocol, user_token: str):
    """The role check must not come after validation (which would render the form back)."""
    assert post_form(client, _path(protocol.id), {}, token=user_token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, protocol: models.Protocol):
    for response in (get(client, _path(protocol.id)), post_form(client, _path(protocol.id), {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_protocol_is_404(client: TestClient, kits: list[models.Kit], insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404
    assert post_form(client, _path(999999), _payload([(kits[0], 1)]), token=insider_token).status_code == 404


def test_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form_csrf_mismatch(client, _path(protocol.id), _payload([(kits[1], 1)]), token=insider_token)
    assert response.status_code != 204
    assert _links(session, protocol) == [(kits[0].id, 1)]


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_submit_replaces_kit_links(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1), (kits[2], 2)]), token=insider_token)

    assert_htmx_redirect(response, f"/protocols/{protocol.id}")
    assert _links(session, protocol) == sorted([(kits[1].id, 1), (kits[2].id, 2)])


def test_redirect_opens_kits_tab(
    client: TestClient, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1)]), token=insider_token)

    assert_htmx_redirect(response, "tab=protocol-kits-tab")
    assert "success" in response.headers.get("HX-Trigger", "") + response.headers.get("set-cookie", "")


def test_resubmitting_existing_links_keeps_them(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[0], 1), (kits[1], 1)]), token=insider_token)

    assert_htmx_redirect(response, f"/protocols/{protocol.id}")
    assert _links(session, protocol) == sorted([(kits[0].id, 1), (kits[1].id, 1)])


def test_missing_combination_numbers_default_to_one(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], ""), (kits[2], "")]), token=insider_token)

    assert_htmx_redirect(response, f"/protocols/{protocol.id}")
    assert _links(session, protocol) == sorted([(kits[1].id, 1), (kits[2].id, 1)])


def test_same_kit_in_different_combinations_is_allowed(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1), (kits[1], 2)]), token=insider_token)

    assert_htmx_redirect(response, f"/protocols/{protocol.id}")
    assert _links(session, protocol) == [(kits[1].id, 1), (kits[1].id, 2)]


def test_other_protocols_are_untouched(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    other = create_protocol(session)
    other.kit_links.append(models.links.ProtocolKitLink(protocol_id=other.id, kit_id=kits[0].id, combination_num=1))
    session.save(other, flush=True)
    session.commit()

    post_form(client, _path(protocol.id), _payload([(kits[2], 1)]), token=insider_token)

    assert _links(session, other) == [(kits[0].id, 1)]


# ── Submit: validation ──────────────────────────────────────────────────────


def test_duplicate_kit_and_combination_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1), (kits[1], 1)]), token=insider_token)

    assert_form_invalid(response, "Duplicate kit and combination number.")
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_duplicate_kit_without_combinations_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    """Both rows default to combination 1, so they collide."""
    response = post_form(client, _path(protocol.id), _payload([(kits[1], ""), (kits[1], "")]), token=insider_token)

    assert_form_invalid(response, "Duplicate kit and combination number.")
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_partially_missing_combination_numbers_are_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1), (kits[2], "")]), token=insider_token)

    assert_form_invalid(response, "Combination number is required.")
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_unknown_kit_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([("[NOPE] Not a kit", 1)]), token=insider_token)

    assert_form_invalid(response)
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_missing_kit_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], 1), ("", 2)]), token=insider_token)

    assert_form_invalid(response)
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_non_integer_combination_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    response = post_form(client, _path(protocol.id), _payload([(kits[1], "abc")]), token=insider_token)

    assert_form_invalid(response)
    assert _links(session, protocol) == [(kits[0].id, 1)]


def test_empty_spreadsheet_is_rejected(
    client: TestClient, session: SyncSession, protocol: models.Protocol, kits: list[models.Kit], insider_token: str,
):
    """Legacy SpreadsheetInput defaulted to can_be_empty=False."""
    response = post_form(client, _path(protocol.id), spreadsheet_payload(COLUMNS, [["", ""]]), token=insider_token)

    assert_form_invalid(response)
    assert _links(session, protocol) == [(kits[0].id, 1)]
