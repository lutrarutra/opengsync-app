"""EditKitFeaturesAction: edit a feature kit's features as a spreadsheet.

As legacy ``feature_kits_htmx.edit_features`` / ``EditKitFeaturesForm``: the spreadsheet is
prefilled with the kit's features and submitting replaces them (new features of the kit's
type, sorted by name). Identifiers are normalized to ASCII, checked and unique; whitespace
is removed from sequence, read and target name/ID; the pattern is stripped. Sequence +
pattern + read must be unique; names must be unique in CMO kits.

Access is insider-only (legacy: admin-only — see design note 5).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_feature_kit
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

PREFIX = "/htmx/kits"
COLUMNS = ["Name", "Identifier", "Sequence", "Pattern", "Read", "Target Name", "Target ID"]
KEYS = ["name", "identifier", "sequence", "pattern", "read", "target_name", "target_id"]
PATTERN = "5PNNNNNNNNNN(BC)"


def _path(feature_kit_id: int) -> str:
    return f"{PREFIX}/{feature_kit_id}/edit-features"


def _feature(name: str, sequence: str, identifier: str = "", read: str = "R2", pattern: str = PATTERN,
             target_name: str = "", target_id: str = "") -> list[str]:
    return [name, identifier, sequence, pattern, read, target_name, target_id]


def _payload(rows: list[list[Any]]) -> dict[str, str]:
    return spreadsheet_payload(COLUMNS, rows)


def _features(session: SyncSession, kit: models.FeatureKit) -> list[dict[str, Any]]:
    session.expire_all()
    kit = session.get_one(Q.feature_kit.select(id=kit.id))
    return [
        {key: getattr(f, key) for key in KEYS} | {"type": f.type}
        for f in sorted(kit.features, key=lambda f: f.name)
    ]


def _kit(session: SyncSession, type: C.FeatureTypeEnum = C.FeatureType.ANTIBODY) -> models.FeatureKit:
    kit = create_feature_kit(session)
    kit.type = type
    session.save(kit, flush=True)
    return kit


@pytest.fixture
def kit(session: SyncSession) -> models.FeatureKit:
    """An antibody kit with one feature 'OldFeature'."""
    kit = _kit(session)
    kit.features.append(Q.feature.create(
        identifier="OLD", name="OldFeature", sequence="TTTTTTTTTT", pattern=PATTERN, read="R2",
        type=C.FeatureType.ANTIBODY, feature_kit_id=kit.id,
    ))
    session.save(kit, flush=True)
    session.commit()
    return kit


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_prefills_features(client: TestClient, kit: models.FeatureKit, insider_token: str):
    response = get(client, _path(kit.id), insider_token)

    assert response.status_code == 200, response.text
    for text in ("OldFeature", "TTTTTTTTTT", "OLD", "csrf_token"):
        assert text in response.text


def test_render_does_not_change_features(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    get(client, _path(kit.id), insider_token)
    assert [f["name"] for f in _features(session, kit)] == ["OldFeature"]


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, session: SyncSession, kit: models.FeatureKit, user_token: str):
    assert get(client, _path(kit.id), user_token).status_code == 403
    response = post_form(client, _path(kit.id), _payload([_feature("NewFeature", "ACGTACGTAC")]), token=user_token)
    assert response.status_code == 403
    assert [f["name"] for f in _features(session, kit)] == ["OldFeature"]


def test_client_with_invalid_submission_is_still_denied(client: TestClient, kit: models.FeatureKit, user_token: str):
    """The role check must not come after validation (which would render the form back)."""
    assert post_form(client, _path(kit.id), {}, token=user_token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, kit: models.FeatureKit):
    for response in (get(client, _path(kit.id)), post_form(client, _path(kit.id), {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_kit_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404
    response = post_form(client, _path(999999), _payload([_feature("NewFeature", "ACGTACGTAC")]), token=insider_token)
    assert response.status_code == 404


def test_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form_csrf_mismatch(client, _path(kit.id), _payload([_feature("NewFeature", "ACGTACGTAC")]), token=insider_token)

    assert response.status_code != 204
    assert [f["name"] for f in _features(session, kit)] == ["OldFeature"]


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_submit_replaces_features(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD8", "GGGGCCCCAA", identifier="ID_CD8", read="R1", target_name="CD8A", target_id="P01732"),
        _feature("CD4", "ACGTACGTAC"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    assert_flash(response, "Changes saved!", category="success")
    assert _features(session, kit) == [
        {"name": "CD4", "identifier": None, "sequence": "ACGTACGTAC", "pattern": PATTERN, "read": "R2",
         "target_name": None, "target_id": None, "type": C.FeatureType.ANTIBODY},
        {"name": "CD8", "identifier": "ID_CD8", "sequence": "GGGGCCCCAA", "pattern": PATTERN, "read": "R1",
         "target_name": "CD8A", "target_id": "P01732", "type": C.FeatureType.ANTIBODY},
    ]


def test_resubmitting_prefill_keeps_features(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form(client, _path(kit.id), _payload([_feature("OldFeature", "TTTTTTTTTT", identifier="OLD")]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    assert [(f["name"], f["identifier"], f["sequence"]) for f in _features(session, kit)] == [("OldFeature", "OLD", "TTTTTTTTTT")]


def test_features_take_the_kit_type(client: TestClient, session: SyncSession, insider_token: str):
    cmo_kit = _kit(session, C.FeatureType.CMO)
    session.commit()

    response = post_form(client, _path(cmo_kit.id), _payload([_feature("CMO301", "ATGAGGAATTCCTGC")]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{cmo_kit.id}")
    assert [f["type"] for f in _features(session, cmo_kit)] == [C.FeatureType.CMO]


def test_other_kits_are_untouched(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    other = _kit(session)
    other.features.append(Q.feature.create(
        identifier=None, name="OtherFeature", sequence="AAAAACCCCC", pattern=PATTERN, read="R2", type=C.FeatureType.ANTIBODY,
        feature_kit_id=other.id,
    ))
    session.save(other, flush=True)
    session.commit()

    post_form(client, _path(kit.id), _payload([_feature("CD4", "ACGTACGTAC")]), token=insider_token)

    assert [f["name"] for f in _features(session, other)] == ["OtherFeature"]


# ── Submit: clean-up (legacy clean_up_fnc) ──────────────────────────────────


def test_whitespace_is_removed(client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str):
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD4", " ACGT ACGT AC ", read=" R 2 ", pattern=f"  {PATTERN} ", target_name=" CD 4 ", target_id=" P0 1730 "),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    [feature] = _features(session, kit)
    assert (feature["sequence"], feature["read"], feature["pattern"], feature["target_name"], feature["target_id"]) == (
        "ACGTACGTAC", "R2", PATTERN, "CD4", "P01730",
    )


def test_identifier_is_normalized_to_ascii(client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str):
    response = post_form(client, _path(kit.id), _payload([_feature("CD4", "ACGTACGTAC", identifier="Ä_CD4")]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    assert [f["identifier"] for f in _features(session, kit)] == ["A_CD4"]


# ── Submit: validation ──────────────────────────────────────────────────────


def _assert_unchanged(session: SyncSession, kit: models.FeatureKit) -> None:
    assert [f["name"] for f in _features(session, kit)] == ["OldFeature"]


def test_duplicate_sequence_pattern_read_is_rejected(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD4", "ACGTACGTAC"), _feature("CD8", "ACGTACGTAC"),
    ]), token=insider_token)

    assert_form_invalid(response, "Duplicate sequence + pattern + read combination.")
    _assert_unchanged(session, kit)


def test_same_sequence_on_other_read_is_allowed(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD4", "ACGTACGTAC", read="R1"), _feature("CD8", "ACGTACGTAC", read="R2"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")


def test_duplicate_name_is_rejected_in_cmo_kit(client: TestClient, session: SyncSession, insider_token: str):
    cmo_kit = _kit(session, C.FeatureType.CMO)
    session.commit()

    response = post_form(client, _path(cmo_kit.id), _payload([
        _feature("CMO301", "ATGAGGAATTCCTGC"), _feature("CMO301", "CATGCCAATAGAGCG"),
    ]), token=insider_token)

    assert_form_invalid(response, "Duplicate feature name not allowed in 'CMO'-kit.")
    assert _features(session, cmo_kit) == []


def test_duplicate_name_is_allowed_in_antibody_kit(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD4", "ACGTACGTAC"), _feature("CD4", "GGGGCCCCAA"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    assert [f["name"] for f in _features(session, kit)] == ["CD4", "CD4"]


def test_duplicate_identifier_is_rejected(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    """Legacy: identifier column unique=True."""
    response = post_form(client, _path(kit.id), _payload([
        _feature("CD4", "ACGTACGTAC", identifier="SAME"), _feature("CD8", "GGGGCCCCAA", identifier="SAME"),
    ]), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, kit)


def test_disallowed_identifier_characters_are_removed(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str,
):
    """Legacy normalize_to_ascii keeps only letters, digits and _ . -, spaces become _ (so check_string then passes)."""
    response = post_form(client, _path(kit.id), _payload([_feature("CD4", "ACGTACGTAC", identifier="CD4;CD8 x")]), token=insider_token)

    assert_htmx_redirect(response, f"/feature-kits/{kit.id}")
    assert [f["identifier"] for f in _features(session, kit)] == ["CD4CD8_x"]


@pytest.mark.parametrize("missing", ["Name", "Sequence", "Pattern", "Read"])
def test_missing_required_value_is_rejected(
    client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str, missing: str,
):
    row = _feature("CD4", "ACGTACGTAC")
    row[COLUMNS.index(missing)] = ""

    response = post_form(client, _path(kit.id), _payload([row]), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, kit)


def test_short_name_is_rejected(client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str):
    response = post_form(client, _path(kit.id), _payload([_feature("C4", "ACGTACGTAC")]), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, kit)


def test_too_long_sequence_is_rejected(client: TestClient, session: SyncSession, kit: models.FeatureKit, insider_token: str):
    too_long = "A" * (models.Feature.sequence.type.length + 1)
    response = post_form(client, _path(kit.id), _payload([_feature("CD4", too_long)]), token=insider_token)

    assert_form_invalid(response)
    _assert_unchanged(session, kit)
