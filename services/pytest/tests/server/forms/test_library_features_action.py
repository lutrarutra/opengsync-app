"""LibraryFeaturesAction: render, access, saving features, and validation.

Each spreadsheet row is either a kit feature (``Kit`` + ``Identifier`` and/or
``Feature``: the existing feature of that feature kit is linked) or a custom feature
(``Feature`` + ``Sequence`` + ``Pattern`` + ``Read``: a new ANTIBODY feature is
created). Submitting replaces the library's features.

As legacy ``libraries_htmx.edit_features``: only 10x Antibody Capture and 10x SC ABC
Flex libraries have editable features (400 otherwise); identifiers are normalized to
ASCII and whitespace is removed from sequences.

Access is insider-only for GET and POST (legacy: WRITE on the library — see design
note 5 in ``docs/mirgation/migration_test_plan.md``).

Legacy itself never set ``feature_id`` for kit rows and so raised "Logic error" on every
kit feature; the kit tests assert the evident intent (link the kit's feature, reject an
identifier that is not in the kit), not that crash.
"""

from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...db.create_units import create_feature, create_feature_kit, create_library, create_seq_request
from ..workflows._spreadsheet import query_labels
from ..workflows.library_annotation._workflow import spreadsheet_records
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

PREFIX = "/htmx/libraries"
COLUMNS = ["Kit", "Identifier", "Feature", "Sequence", "Pattern", "Read"]
PATTERN = "5PNNNNNNNNNN(BC)"


def _path(library_id: int) -> str:
    return f"{PREFIX}/{library_id}/edit-features"


def _payload(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Each row maps header → value; missing cells are empty."""
    return spreadsheet_payload(COLUMNS, [[row.get(col, "") for col in COLUMNS] for row in rows])


def _custom(identifier: str, feature: str, sequence: str, read: str = "R2", pattern: str = PATTERN) -> dict[str, str]:
    return {"Identifier": identifier, "Feature": feature, "Sequence": sequence, "Pattern": pattern, "Read": read}


def _kit_label(kit: models.FeatureKit) -> str:
    """The name the kit column shows for a kit id; pasted labels are resolved to the kit too."""
    return f"[{kit.identifier}] {kit.name}"


def _library(session: SyncSession, user: models.User, library_type=C.LibraryType.TENX_ANTIBODY_CAPTURE) -> models.Library:
    library = create_library(session, user, create_seq_request(session, user))
    library.type = library_type
    session.save(library, flush=True)
    return library


def _features(session: SyncSession, library: models.Library) -> list[models.Feature]:
    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    return sorted(library.features, key=lambda f: f.name)


def _num_features(session: SyncSession) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(models.Feature)).scalar_one()


@pytest.fixture
def kit_feature(session: SyncSession) -> models.Feature:
    kit = create_feature_kit(session)
    feature = create_feature(session, kit)
    feature.identifier = "KIT_CD3"
    feature.name = "CD3"
    session.save(feature, flush=True)
    return feature


@pytest.fixture
def library(session: SyncSession, user) -> models.Library:
    """An antibody-capture library that already has one custom feature."""
    library = _library(session, user)
    library.features.append(Q.feature.create(
        identifier="OLD", name="OldFeature", sequence="TTTTTTTTTT", pattern=PATTERN, read="R2",
        type=C.FeatureType.ANTIBODY,
    ))
    session.save(library, flush=True)
    session.commit()
    return library


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_prefills_existing_features(client: TestClient, library: models.Library, insider_token: str):
    response = get(client, _path(library.id), insider_token)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    for text in ("OldFeature", "TTTTTTTTTT", library.name):
        assert text in response.text


def test_render_searches_antibody_feature_kits(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    """Kits are not sent with the page: the column queries the antibody kits on the backend."""
    session.commit()
    response = get(client, _path(library.id), insider_token)

    assert response.status_code == 200
    assert f"/htmx/feature_kits/query?type_in=%5B{C.FeatureType.ANTIBODY.id}%5D" in response.text
    assert _kit_label(kit_feature.feature_kit) not in response.text


def test_render_does_not_change_features(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    assert get(client, _path(library.id), insider_token).status_code == 200
    assert [f.name for f in _features(session, library)] == ["OldFeature"]


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_owner_is_denied(client: TestClient, library: models.Library, user_token: str):
    """Even the library owner is denied: the FastAPI action is insider-only (design note 5)."""
    assert get(client, _path(library.id), user_token).status_code == 403
    assert post_form(client, _path(library.id), _payload([_custom("X", "X", "ACGTACGTAC")]), token=user_token).status_code == 403


def test_client_denied_submit_changes_nothing(
    client: TestClient, session: SyncSession, library: models.Library, user_token: str,
):
    post_form(client, _path(library.id), _payload([_custom("NEW", "NewFeature", "ACGTACGTAC")]), token=user_token)
    assert [f.name for f in _features(session, library)] == ["OldFeature"]


def test_client_with_invalid_submission_is_still_denied(client: TestClient, library: models.Library, user_token: str):
    """The role check must not come after validation (which would render the form back)."""
    assert post_form(client, _path(library.id), {}, token=user_token).status_code == 403


def test_anonymous_is_redirected_to_login(client: TestClient, library: models.Library):
    for response in (get(client, _path(library.id)), post_form(client, _path(library.id), {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_library_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


@pytest.mark.parametrize("library_type", [C.LibraryType.TENX_ANTIBODY_CAPTURE, C.LibraryType.TENX_SC_ABC_FLEX])
def test_antibody_library_types_are_editable(
    client: TestClient, session: SyncSession, user, insider_token: str, library_type,
):
    library = _library(session, user, library_type)
    session.commit()
    assert get(client, _path(library.id), insider_token).status_code == 200


def test_non_antibody_library_is_rejected(
    client: TestClient, session: SyncSession, user, insider_token: str,
):
    """Legacy: 'Only 10x Antibody Capture and 10x SC ABC Flex libraries have features that can be edited.'"""
    library = _library(session, user, C.LibraryType.BULK_RNA_SEQ)
    session.commit()

    assert get(client, _path(library.id), insider_token).status_code == 400
    response = post_form(client, _path(library.id), _payload([_custom("NEW", "NewFeature", "ACGTACGTAC")]), token=insider_token)
    assert response.status_code == 400
    assert _features(session, library) == []


def test_csrf_mismatch_changes_nothing(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form_csrf_mismatch(
        client, _path(library.id), _payload([_custom("NEW", "NewFeature", "ACGTACGTAC")]), token=insider_token,
    )
    assert response.status_code != 204
    assert [f.name for f in _features(session, library)] == ["OldFeature"]


# ── Submit: persistence ─────────────────────────────────────────────────────


def test_custom_feature_replaces_existing_features(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_CD4", "CD4", "ACGTACGTAC"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert_flash(response, "Changes Saved!", category="success")

    features = _features(session, library)
    assert [(f.identifier, f.name, f.sequence, f.pattern, f.read, f.type, f.feature_kit_id) for f in features] == [
        ("CUST_CD4", "CD4", "ACGTACGTAC", PATTERN, "R2", C.FeatureType.ANTIBODY, None),
    ]


def test_multiple_custom_features_are_saved(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_CD4", "CD4", "ACGTACGTAC"),
        _custom("CUST_CD8", "CD8", "GGGGCCCCAA", read="R1"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [(f.name, f.read) for f in _features(session, library)] == [("CD4", "R2"), ("CD8", "R1")]


def test_resubmitting_prefilled_features_keeps_them(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("OLD", "OldFeature", "TTTTTTTTTT"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [(f.identifier, f.name, f.sequence) for f in _features(session, library)] == [("OLD", "OldFeature", "TTTTTTTTTT")]


def test_sequence_whitespace_is_removed(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    """Legacy cleaned sequences with make_alpha_numeric(replace_white_spaces_with="")."""
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_CD4", "CD4", " ACGTA CGTAC "),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.sequence for f in _features(session, library)] == ["ACGTACGTAC"]


def test_identifier_is_normalized_to_ascii(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    """Legacy cleaned identifiers with normalize_to_ascii (Greek letters transliterated)."""
    response = post_form(client, _path(library.id), _payload([
        _custom("TNFα", "TNF", "ACGTACGTAC"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.identifier for f in _features(session, library)] == ["TNFa"]


def test_kit_feature_by_name_links_the_existing_kit_feature(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    num_features = _num_features(session)

    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit_feature.feature_kit), "Identifier": "KIT_CD3", "Feature": "CD3"},
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.id for f in _features(session, library)] == [kit_feature.id]
    assert _num_features(session) == num_features, "no copy of the kit feature is created"


def test_kit_feature_by_identifier_links_the_existing_kit_feature(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()

    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit_feature.feature_kit), "Identifier": "KIT_CD3"},
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.id for f in _features(session, library)] == [kit_feature.id]


def test_kit_and_custom_features_together(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()

    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit_feature.feature_kit), "Identifier": "KIT_CD3", "Feature": "CD3"},
        _custom("CUST_CD4", "CD4", "ACGTACGTAC"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    features = _features(session, library)
    assert [f.name for f in features] == ["CD3", "CD4"]
    assert features[0].id == kit_feature.id


# ── Submit: validation ──────────────────────────────────────────────────────


def _assert_rejected(session: SyncSession, library: models.Library, response, contains: str | None = None) -> None:
    assert_form_invalid(response, contains)
    assert [f.name for f in _features(session, library)] == ["OldFeature"]


def test_row_without_kit_or_full_custom_definition_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        {"Identifier": "CUST_CD4", "Feature": "CD4", "Sequence": "ACGTACGTAC"},  # no pattern, no read
    ]), token=insider_token)

    _assert_rejected(session, library, response, "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified.")


def test_row_with_both_kit_and_custom_definition_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit_feature.feature_kit), **_custom("KIT_CD3", "CD3", "ACGTACGTAC")},
    ]), token=insider_token)

    _assert_rejected(session, library, response, "not both")


def test_missing_identifier_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    row = _custom("", "CD4", "ACGTACGTAC")
    response = post_form(client, _path(library.id), _payload([row]), token=insider_token)

    _assert_rejected(session, library, response)


def test_duplicate_identifier_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("SAME", "CD4", "ACGTACGTAC"),
        _custom("SAME", "CD8", "GGGGCCCCAA"),
    ]), token=insider_token)

    _assert_rejected(session, library, response, "duplicate feature definition")


def test_duplicate_feature_name_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_A", "CD4", "ACGTACGTAC"),
        _custom("CUST_B", "CD4", "GGGGCCCCAA"),
    ]), token=insider_token)

    _assert_rejected(session, library, response, "duplicate feature name")


def test_duplicate_sequence_pattern_read_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_A", "CD4", "ACGTACGTAC"),
        _custom("CUST_B", "CD8", "ACGTACGTAC"),
    ]), token=insider_token)

    _assert_rejected(session, library, response, "Duplicate 'Sequence + Pattern + Read' combination.")


def test_same_sequence_on_different_read_is_allowed(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_A", "CD4", "ACGTACGTAC", read="R1"),
        _custom("CUST_B", "CD8", "ACGTACGTAC", read="R2"),
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.name for f in _features(session, library)] == ["CD4", "CD8"]


def test_invalid_read_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        _custom("CUST_CD4", "CD4", "ACGTACGTAC", read="R3"),
    ]), token=insider_token)

    _assert_rejected(session, library, response)


def test_unknown_kit_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, insider_token: str,
):
    response = post_form(client, _path(library.id), _payload([
        {"Kit": "[NOPE] No such kit", "Identifier": "KIT_CD3", "Feature": "CD3"},
    ]), token=insider_token)

    _assert_rejected(session, library, response, "Unknown kit")


def test_feature_not_in_kit_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    kit = kit_feature.feature_kit
    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit), "Identifier": "KIT_CD3", "Feature": "NotInKit"},
    ]), token=insider_token)

    _assert_rejected(session, library, response, f"Feature 'NotInKit' not found in kit '{kit.identifier}'")


def test_identifier_not_in_kit_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    kit = kit_feature.feature_kit
    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit), "Identifier": "NOT_IN_KIT"},
    ]), token=insider_token)

    _assert_rejected(session, library, response, f"Identifier 'NOT_IN_KIT' not found in kit '{kit.identifier}'")



def test_two_features_of_the_same_kit_are_allowed(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    other = create_feature(session, kit_feature.feature_kit)
    other.identifier = "KIT_CD8"
    other.name = "CD8"
    session.save(other, flush=True)
    session.commit()
    label = _kit_label(kit_feature.feature_kit)

    response = post_form(client, _path(library.id), _payload([
        {"Kit": label, "Identifier": "KIT_CD3"},
        {"Kit": label, "Identifier": "KIT_CD8"},
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert sorted(f.id for f in _features(session, library)) == sorted([kit_feature.id, other.id])


def test_same_kit_feature_twice_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    label = _kit_label(kit_feature.feature_kit)

    response = post_form(client, _path(library.id), _payload([
        {"Kit": label, "Identifier": "KIT_CD3", "Feature": "CD3"},
        {"Kit": label, "Identifier": "KIT_CD3"},
    ]), token=insider_token)

    _assert_rejected(session, library, response, "Duplicate 'Kit' + 'Feature' specified.")


def test_identifier_and_feature_of_different_kit_features_is_rejected(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    other = create_feature(session, kit_feature.feature_kit)
    other.identifier = "KIT_CD8"
    other.name = "CD8"
    session.save(other, flush=True)
    session.commit()

    response = post_form(client, _path(library.id), _payload([
        {"Kit": _kit_label(kit_feature.feature_kit), "Identifier": "KIT_CD3", "Feature": "CD8"},
    ]), token=insider_token)

    _assert_rejected(session, library, response, "refer to different features")


# ── Kit column (QueryColumn: cells hold kit ids) ────────────────────────────


def test_kit_feature_by_kit_id(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    session.commit()
    response = post_form(client, _path(library.id), _payload([
        {"Kit": kit_feature.feature_kit_id, "Identifier": "KIT_CD3"},
    ]), token=insider_token)

    assert_htmx_redirect(response, f"/libraries/{library.id}")
    assert [f.id for f in _features(session, library)] == [kit_feature.id]


def test_render_prefills_kit_features_by_kit_id(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
):
    """Reopening the form shows the kit of a kit feature by its id, named for the editor."""
    library.features.append(kit_feature)
    session.save(library, flush=True)
    session.commit()

    response = get(client, _path(library.id), insider_token)

    assert response.status_code == 200, response.text
    kit_rows = [record for record in spreadsheet_records(response) if record["Identifier"] == "KIT_CD3"]
    assert [record["Kit"] for record in kit_rows] == [kit_feature.feature_kit_id]
    assert query_labels(response, "Kit") == {kit_feature.feature_kit_id: _kit_label(kit_feature.feature_kit)}


@pytest.mark.parametrize("kit, identifier, message", [
    (999_999_999, "KIT_CD3", "Unknown kit"),  # found by the spreadsheet validation
    ("KIT", "NOT_IN_KIT", "not found in kit"),  # found by the route
])
def test_invalid_submission_is_rendered_unchanged(
    client: TestClient, session: SyncSession, library: models.Library, kit_feature: models.Feature, insider_token: str,
    kit, identifier: str, message: str,
):
    session.commit()
    rows = [
        {"Kit": kit_feature.feature_kit_id if kit == "KIT" else kit, "Identifier": identifier},
        _custom("CUST_CD4", "CD4", "ACGTACGTAC"),
    ]
    response = post_form(client, _path(library.id), _payload(rows), token=insider_token)

    _assert_rejected(session, library, response, message)
    assert spreadsheet_records(response) == [{col: row.get(col, "") for col in COLUMNS} for row in rows]
