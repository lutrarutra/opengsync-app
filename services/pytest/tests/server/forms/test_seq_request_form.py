"""Integration tests for the FastAPI SeqRequestForm."""

from uuid import uuid4

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ...db.create_units import create_seq_request
from .._http import assert_form_invalid, post_form


def _request_payload(name: str, **overrides: str | None) -> dict[str, str]:
    """Return a complete valid create payload using the form's field names."""
    payload: dict[str, str] = {
        "disclaimer-accepted": "true",
        "basic_info-name": name,
        "basic_info-description": "A complete test sequencing request",
        "technical_info-submission_type": str(C.SubmissionType.POOLED_LIBRARIES.id),
        "technical_info-read_type": str(C.ReadType.PAIRED_END.id),
        "technical_info-read_length": "150",
        "technical_info-num_lanes": "2",
        "technical_info-data_delivery_mode": str(C.DataDeliveryMode.ALIGNMENT.id),
        "technical_info-special_requirements": "No special requirements",
        "contact-name": "Primary Contact",
        "contact-email": "contact@example.com",
        "contact-phone": "+1 555 0100",
        "contact-pi_name": "Principal Investigator",
        "contact-pi_email": "pi@example.com",
        "bioinformatician-name": "",
        "bioinformatician-email": "",
        "bioinformatician-phone": "",
        "organization-name": "Test Organization",
        "organization-address": "1 Organization Street",
        "billing-name": "Accounts Payable",
        "billing-email": "billing@example.com",
        "billing-phone": "+1 555 0200",
        "billing-address": "2 Billing Street",
        "billing-code": "TEST-001",
    }
    payload.update({key: value for key, value in overrides.items() if value is not None})
    return payload


def _created_request(session: SyncSession, name: str):
    return session.first(Q.seq_request.select(name=name))


def test_insider_can_assign_existing_user_as_requestor(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
    user_2,
):
    name = f"existing-requestor-{uuid4().hex}"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(name, **{"user_selection-user_id": str(user_2.id)}),
        token=insider_token,
    )

    assert response.status_code == 204
    request = _created_request(session, name)
    assert request is not None
    assert request.requestor_id == user_2.id
    assert request.billing_contact.address == "2 Billing Street"
    assert request.pi_contact is not None
    assert request.pi_contact.name == "Principal Investigator"
    assert request.pi_contact.email == "pi@example.com"


def test_insider_can_create_deactivated_user_as_requestor(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    name = f"manual-requestor-{uuid4().hex}"
    email = f"new-requestor-{uuid4().hex}@example.com"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(
            name,
            **{
                "user_selection-email": email,
                "user_selection-first_name": " New ",
                "user_selection-last_name": " Requestor ",
            },
        ),
        token=insider_token,
    )

    assert response.status_code == 204
    request = _created_request(session, name)
    assert request is not None
    created_user = session.first(Q.user.select(email=email))
    assert created_user is not None
    assert created_user.first_name == "New"
    assert created_user.last_name == "Requestor"
    assert created_user.role_id == C.UserRole.DEACTIVATED.id
    assert created_user.password
    assert request.requestor_id == created_user.id


def test_requestor_selection_rejects_mixed_existing_and_manual_details(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
    user_2,
):
    name = f"mixed-requestor-{uuid4().hex}"
    email = f"mixed-{uuid4().hex}@example.com"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(
            name,
            **{
                "user_selection-user_id": str(user_2.id),
                "user_selection-email": email,
                "user_selection-first_name": "Mixed",
                "user_selection-last_name": "User",
            },
        ),
        token=insider_token,
    )

    assert_form_invalid(response, "not both")
    assert _created_request(session, name) is None
    assert session.first(Q.user.select(email=email)) is None


def test_requestor_selection_rejects_partial_manual_details(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    name = f"partial-requestor-{uuid4().hex}"
    email = f"partial-{uuid4().hex}@example.com"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(
            name,
            **{
                "user_selection-email": email,
                "user_selection-first_name": "Only",
            },
        ),
        token=insider_token,
    )

    assert_form_invalid(response, "required for a new user")
    assert _created_request(session, name) is None
    assert session.first(Q.user.select(email=email)) is None


def test_requestor_selection_rejects_duplicate_email(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
    user_2,
):
    name = f"duplicate-requestor-{uuid4().hex}"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(
            name,
            **{
                "user_selection-email": user_2.email,
                "user_selection-first_name": "Duplicate",
                "user_selection-last_name": "User",
            },
        ),
        token=insider_token,
    )

    assert_form_invalid(response, "already registered")
    assert _created_request(session, name) is None


def test_edit_persists_all_billing_contact_fields(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    request.billing_contact.name = "Old Billing"
    request.billing_contact.email = "old-billing@example.com"
    request.billing_contact.phone = "old phone"
    request.billing_contact.address = "Old address"
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(
            request.name,
            **{
                "billing-name": "New Billing",
                "billing-email": "new-billing@example.com",
                "billing-phone": "new phone",
                "billing-address": "New address",
            },
        ),
        token=user_token,
    )

    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.billing_contact.name == "New Billing"
    assert request.billing_contact.email == "new-billing@example.com"
    assert request.billing_contact.phone == "new phone"
    assert request.billing_contact.address == "New address"


def test_edit_persists_pi_contact_fields(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(
            request.name,
            **{
                "contact-pi_name": "Updated PI",
                "contact-pi_email": "updated-pi@example.com",
            },
        ),
        token=user_token,
    )

    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.pi_contact is not None
    assert request.pi_contact.name == "Updated PI"
    assert request.pi_contact.email == "updated-pi@example.com"


def test_optional_fields_can_be_omitted_on_create(
    client: TestClient,
    session: SyncSession,
    user_token: str,
    user,
):
    name = f"optional-fields-{uuid4().hex}"
    payload = _request_payload(name)
    for field in (
        "basic_info-description",
        "technical_info-read_length",
        "technical_info-num_lanes",
        "technical_info-special_requirements",
        "contact-pi_name",
        "contact-pi_email",
        "bioinformatician-name",
        "bioinformatician-email",
        "bioinformatician-phone",
        "billing-phone",
        "billing-code",
    ):
        payload.pop(field)

    response = post_form(
        client,
        "/htmx/seq_requests/create",
        payload,
        token=user_token,
    )

    assert response.status_code == 204
    request = _created_request(session, name)
    assert request is not None
    assert request.description is None
    assert request.read_length is None
    assert request.num_lanes is None
    assert request.special_requirements is None
    assert request.bioinformatician_contact is None
    assert request.pi_contact is None
    assert request.billing_contact.phone is None
    assert request.billing_code is None


def test_create_form_keeps_legacy_defaults_for_unchanged_inputs():
    from server.forms.models.SeqRequestForm import SeqRequestForm

    form = SeqRequestForm(form_type="create")

    assert form.technical_info.read_type.data == C.ReadType.PAIRED_END.id
    assert form.user_selection.user_id.data is None
    assert form.user_selection.email.data is None
    assert form.user_selection.first_name.data is None
    assert form.user_selection.last_name.data is None
    assert form.contact.current_user_is_contact.data is False


def test_number_of_lanes_matches_legacy_upper_bound(
    client: TestClient,
    session: SyncSession,
    insider_token: str,
):
    name = f"lane-bound-{uuid4().hex}"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(name, **{"technical_info-num_lanes": "9"}),
        token=insider_token,
    )

    assert_form_invalid(response, "Value must be <= 8")
    assert _created_request(session, name) is None
