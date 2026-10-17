"""LabPrepForm: create and edit — rendering, permissions, field validation, and persistence.

Now uses the ``@htmx_route`` decorator pattern consistent with other model forms
(PoolForm, ProjectForm, etc.).  The lab_preps router requires ``require_insider``
at the router level, so every endpoint is insider-only.
"""

import re

import sqlalchemy as sa

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
)

CREATE = "/htmx/lab_preps/create"
EDIT = "/htmx/lab_preps/{lab_prep_id}/edit"
CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"


def _edit_path(lab_prep_id: int) -> str:
    return EDIT.format(lab_prep_id=lab_prep_id)


def _payload(**overrides: object) -> dict[str, str]:
    data: dict[str, str] = {
        "checklist_type": str(C.LabChecklistType.RNA_SEQ.id),
        "service_type": str(C.ServiceType.BULK_RNA_SEQ.id),
        "name": "",
    }
    data.update({key: str(value) for key, value in overrides.items() if value is not None})
    return data


def _lab_prep_by_name(session: SyncSession, name: str) -> models.LabPrep | None:
    session.expire_all()
    return session.first(sa.select(models.LabPrep).where(models.LabPrep.name == name))


def _create_lab_prep(session: SyncSession, insider) -> models.LabPrep:
    """Factory helper: create a lab prep fixture in the DB."""
    prep = session.save(
        Q.lab_prep.create(
            name="Test_Prep_001",
            creator=insider,
            number=1,
            checklist_type=C.LabChecklistType.RNA_SEQ,
            service_type=C.ServiceType.BULK_RNA_SEQ,
        ),
        flush=True,
    )
    session.commit()
    return prep


def _commit(session: SyncSession) -> None:
    session.commit()


# ── Create ──────────────────────────────────────────────────────────────────


def test_create_form_get_requires_insider(
    client: TestClient,
    user_token: str,
    insider_token: str,
):
    """GET create is insider-only (router-level dep)."""
    denied = get(client, CREATE, user_token)
    assert denied.status_code == 403

    allowed = get(client, CREATE, insider_token)
    assert allowed.status_code == 200
    assert 'name="checklist_type"' in allowed.text
    assert 'name="service_type"' in allowed.text
    assert 'name="name"' in allowed.text


def test_create_form_get_anonymous_redirects(client: TestClient):
    response = get(client, CREATE)
    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_create_requires_insider(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(),
        token=user_token,
    )
    assert response.status_code == 403


def test_create_persists_with_auto_name(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    """When name is empty the form auto-generates it as
    ``{checklist_type.identifier}{prep_number:04d}``."""
    response = post_form(
        client,
        CREATE,
        _payload(name=""),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/lab_preps/")
    assert_flash(response, "Prep created!", category="success")

    prep = session.first(
        sa.select(models.LabPrep).order_by(models.LabPrep.id.desc())
    )
    assert prep is not None
    assert prep.name == "R0001"
    assert prep.checklist_type == C.LabChecklistType.RNA_SEQ
    assert prep.service_type == C.ServiceType.BULK_RNA_SEQ
    assert prep.status == C.PrepStatus.PREPARING


def test_create_persists_with_explicit_name(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    name = "My_Custom_Prep"
    response = post_form(
        client,
        CREATE,
        _payload(name=name),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/lab_preps/")
    assert_flash(response, "Prep created!", category="success")

    prep = _lab_prep_by_name(session, name)
    assert prep is not None
    assert prep.checklist_type == C.LabChecklistType.RNA_SEQ
    assert prep.service_type == C.ServiceType.BULK_RNA_SEQ


def test_create_prep_number_increments(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    """Each new prep of the same checklist type gets the next number."""
    first = post_form(client, CREATE, _payload(name=""), token=insider_token)
    assert first.status_code == 204

    second = post_form(client, CREATE, _payload(name=""), token=insider_token)
    assert second.status_code == 204

    preps = session.get_all(
        sa.select(models.LabPrep).order_by(models.LabPrep.id).limit(2),
        limit=2,
    )
    assert preps[0].prep_number == 1
    assert preps[0].name == "R0001"
    assert preps[1].prep_number == 2
    assert preps[1].name == "R0002"


def test_create_rejects_missing_checklist_type(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(checklist_type=""),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Checklist" in response.text


def test_create_rejects_invalid_checklist_type(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(checklist_type=999, service_type=C.ServiceType.BULK_RNA_SEQ.id),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Invalid protocol" in response.text


def test_create_rejects_invalid_service_type(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    response = post_form(
        client,
        CREATE,
        _payload(service_type=999),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Invalid assay type" in response.text


def test_create_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    response = post_form_csrf_mismatch(
        client,
        CREATE,
        _payload(),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")


# ── Edit ────────────────────────────────────────────────────────────────────


def test_edit_form_get_renders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = get(client, _edit_path(prep.id), insider_token)

    assert response.status_code == 200
    assert "Test_Prep_001" in response.text
    assert 'name="checklist_type"' in response.text
    assert 'name="service_type"' in response.text
    assert 'name="name"' in response.text


def test_edit_form_get_denied_for_client(
    client: TestClient,
    session: SyncSession,
    insider,
    user_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = get(client, _edit_path(prep.id), user_token)

    assert response.status_code == 403


def test_edit_form_get_unknown_prep_is_404(
    client: TestClient,
    insider_token: str,
):
    response = get(client, _edit_path(999999), insider_token)

    assert response.status_code == 404


def test_edit_requires_insider(
    client: TestClient,
    session: SyncSession,
    insider,
    user_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = post_form(
        client,
        _edit_path(prep.id),
        _payload(name="Updated_Prep"),
        token=user_token,
    )

    assert response.status_code == 403


def test_edit_persists_name_and_service_type(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = post_form(
        client,
        _edit_path(prep.id),
        _payload(
            name="Renamed_Prep",
            service_type=C.ServiceType.WGS.id,
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/lab_preps/")
    assert_flash(response, "Changes saved!", category="success")

    session.expire_all()
    session.refresh(prep)
    assert prep.name == "Renamed_Prep"
    assert prep.service_type == C.ServiceType.WGS
    assert prep.checklist_type == C.LabChecklistType.RNA_SEQ


def test_edit_rejects_changed_checklist_type(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = post_form(
        client,
        _edit_path(prep.id),
        _payload(
            name="Changed_Checklist",
            checklist_type=C.LabChecklistType.TENX.id,
        ),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Cannot change checklist type" in response.text
    session.expire_all()
    session.refresh(prep)
    assert prep.checklist_type == C.LabChecklistType.RNA_SEQ


def test_edit_requires_name(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = post_form(
        client,
        _edit_path(prep.id),
        _payload(name=""),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert "Name is required" in response.text
    session.expire_all()
    session.refresh(prep)
    assert prep.name == "Test_Prep_001"


def test_edit_csrf_mismatch_rerenders(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    prep = _create_lab_prep(session, insider)

    response = post_form_csrf_mismatch(
        client,
        _edit_path(prep.id),
        _payload(name="CSRF_Prep"),
        token=insider_token,
    )

    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    session.expire_all()
    session.refresh(prep)
    assert prep.name == "Test_Prep_001"


def test_edit_unknown_prep_is_404(
    client: TestClient,
    insider_token: str,
):
    response = post_form(
        client,
        _edit_path(999999),
        _payload(name="Ghost_Prep"),
        token=insider_token,
    )

    assert response.status_code == 404

def _selected_option(html: str, field_name: str) -> str | None:
    """Return the value of the ``selected`` option inside the ``<select name=field_name>``."""
    select = re.search(rf'<select[^>]*name="{field_name}"[^>]*>(.*?)</select>', html, re.S)
    assert select is not None, f"select {field_name!r} not rendered"
    option = re.search(r'<option value="([^"]*)"\s*(?:disabled\s*)?selected', select.group(1))
    return option.group(1) if option else None


def test_edit_form_prefills_every_field(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    """Regression: the edit GET prefills checklist_type, service_type and name from the
    DB (use non-default values so a fallback to the first option cannot pass)."""
    prep = session.save(
        Q.lab_prep.create(
            name="Prefill_Prep_042",
            creator=insider,
            number=42,
            checklist_type=C.LabChecklistType.TENX,
            service_type=C.ServiceType.WGS,
        ),
        flush=True,
    )
    session.commit()

    response = get(client, _edit_path(prep.id), insider_token, htmx=True)

    assert response.status_code == 200
    assert _selected_option(response.text, "checklist_type") == str(C.LabChecklistType.TENX.id)
    assert _selected_option(response.text, "service_type") == str(C.ServiceType.WGS.id)
    assert re.search(r'value="Prefill_Prep_042"\s*name="name"', response.text)


def test_edit_persists_every_field(
    client: TestClient,
    session: SyncSession,
    insider,
    insider_token: str,
):
    """Regression: every editable field (name, service_type) is written on the edit POST;
    checklist_type (not editable in legacy) and the non-form columns are left untouched."""
    prep = _create_lab_prep(session, insider)
    original_number = prep.prep_number
    original_creator_id = prep.creator_id
    original_status = prep.status

    response = post_form(
        client,
        _edit_path(prep.id),
        _payload(
            checklist_type=C.LabChecklistType.RNA_SEQ.id,
            service_type=C.ServiceType.WGS.id,
            name="  Every_Field_Prep  ",
        ),
        token=insider_token,
    )

    assert_htmx_redirect(response, "/lab_preps/")
    assert_flash(response, "Changes saved!", category="success")

    session.expire_all()
    session.refresh(prep)
    assert prep.name == "Every_Field_Prep"
    assert prep.service_type == C.ServiceType.WGS
    assert prep.checklist_type == C.LabChecklistType.RNA_SEQ
    assert prep.prep_number == original_number
    assert prep.creator_id == original_creator_id
    assert prep.status == original_status

    # The edit GET afterwards shows the saved values.
    rendered = get(client, _edit_path(prep.id), insider_token, htmx=True)
    assert rendered.status_code == 200
    assert _selected_option(rendered.text, "service_type") == str(C.ServiceType.WGS.id)
    assert re.search(r'value="Every_Field_Prep"\s*name="name"', rendered.text)
