"""Integration tests for the FastAPI SeqRequestForm."""

import re
from uuid import uuid4

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ...db.create_units import create_contact, create_group, create_seq_request
from .._http import assert_form_invalid, get, post_form
from .._profile import set_profile, PI_NAME, PI_EMAIL


def _request_payload(name: str, **overrides: str | None) -> dict[str, str]:
    """Return a complete valid create payload using the form's field names."""
    payload: dict[str, str] = {
        "disclaimer-accepted": "true",
        "basic_info-name": name,
        "basic_info-description": "A complete test sequencing request",
        "submission-submission_type": str(C.SubmissionType.POOLED_LIBRARIES.id),
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


def test_billing_can_reuse_organization_name_and_address(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    name = f"organization-billing-{uuid4().hex}"
    response = post_form(
        client,
        "/htmx/seq_requests/create",
        _request_payload(
            name,
            **{
                "billing-name": "Test Organization",
                "billing-address": "1 Organization Street",
            },
        ),
        token=user_token,
    )

    assert response.status_code == 204
    request = _created_request(session, name)
    assert request is not None
    assert request.billing_contact.name == "Test Organization"
    assert request.billing_contact.address == "1 Organization Street"


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
    assert created_user.role == C.UserRole.DEACTIVATED
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


def test_edit_persists_every_field(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    request.billing_contact = create_contact(session)  # the fixture shares one contact for person and billing
    session.commit()

    new_name = f"edited-{uuid4().hex}"
    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(
            new_name,
            **{
                "basic_info-description": "Edited description",
                "technical_info-read_type": str(C.ReadType.SINGLE_END.id),
                "technical_info-read_length": "75",
                "technical_info-num_lanes": "3",
                "technical_info-data_delivery_mode": str(C.DataDeliveryMode.READS_ONLY.id),
                "technical_info-special_requirements": "Edited requirements",
                "contact-name": "Edited Contact",
                "contact-email": "edited-contact@example.com",
                "contact-phone": "+1 555 0300",
                "bioinformatician-name": "Edited Bioinformatician",
                "bioinformatician-email": "bioinf@example.com",
                "bioinformatician-phone": "+1 555 0400",
                "organization-name": "Edited Organization",
                "organization-address": "3 Edited Street",
                "billing-code": "EDITED-001",
            },
        ),
        token=user_token,
    )

    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.name == new_name
    assert request.description == "Edited description"
    assert request.submission_type == C.SubmissionType.POOLED_LIBRARIES
    assert request.read_type == C.ReadType.SINGLE_END
    assert request.read_length == 75
    assert request.num_lanes == 3
    assert request.data_delivery_mode == C.DataDeliveryMode.READS_ONLY
    assert request.special_requirements == "Edited requirements"
    assert request.billing_code == "EDITED-001"
    assert request.contact_person.name == "Edited Contact"
    assert request.contact_person.email == "edited-contact@example.com"
    assert request.contact_person.phone == "+1 555 0300"
    assert request.bioinformatician_contact is not None
    assert request.bioinformatician_contact.name == "Edited Bioinformatician"
    assert request.bioinformatician_contact.email == "bioinf@example.com"
    assert request.bioinformatician_contact.phone == "+1 555 0400"
    assert request.organization_contact.name == "Edited Organization"
    assert request.organization_contact.address == "3 Edited Street"
    assert request.billing_contact.name == "Accounts Payable"


def test_edit_rejects_submission_type_change_by_non_admin(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
    insider_token: str,
):
    request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    for token in (user_token, insider_token):
        response = post_form(
            client,
            f"/htmx/seq_requests/{request.id}/edit",
            _request_payload(request.name, **{"submission-submission_type": str(C.SubmissionType.RAW_SAMPLES.id)}),
            token=token,
        )
        assert_form_invalid(response, "Only admins can change the submission type.")

    session.expire_all()
    session.refresh(request)
    assert request.submission_type == C.SubmissionType.POOLED_LIBRARIES


def test_admin_can_change_submission_type_on_edit(
    client: TestClient,
    session: SyncSession,
    user,
    admin_token: str,
):
    request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(request.name, **{"submission-submission_type": str(C.SubmissionType.RAW_SAMPLES.id)}),
        token=admin_token,
    )

    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.submission_type == C.SubmissionType.RAW_SAMPLES


def _submission_type_locked(response) -> bool:
    return bool(re.search(r'name="submission-submission_type" id="[^"]+" value="\d+"[^>]*\bdisabled\b', response.text))


def test_submission_type_is_read_only_on_edit_for_non_admins(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
    insider_token: str,
    admin_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    for token, locked in ((user_token, True), (insider_token, True), (admin_token, False)):
        response = get(client, f"/htmx/seq_requests/{request.id}/edit", token=token, htmx=True)
        assert response.status_code == 200
        assert _submission_type_locked(response) is locked

    response = get(client, "/htmx/seq_requests/create", token=user_token, htmx=True)
    assert response.status_code == 200
    assert not _submission_type_locked(response)


def test_edit_persists_and_clears_group(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    group = create_group(session)
    session.save(Q.affiliation.create(user=user, group=group, type=C.AffiliationType.MEMBER), flush=True)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(request.name, **{"basic_info-group_id": str(group.id)}),
        token=user_token,
    )
    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.group_id == group.id

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(request.name, **{"basic_info-group_id": ""}),
        token=user_token,
    )
    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.group_id is None


def test_edit_rejects_group_requestor_is_not_part_of(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    group = create_group(session)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(request.name, **{"basic_info-group_id": str(group.id)}),
        token=user_token,
    )

    assert_form_invalid(response, "Requestor must be part of the selected group")
    session.expire_all()
    session.refresh(request)
    assert request.group_id is None


def test_edit_form_prefills_submission_type_and_group(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    group = create_group(session)
    request.group = group
    session.commit()

    response = get(client, f"/htmx/seq_requests/{request.id}/edit", token=user_token, htmx=True)

    assert response.status_code == 200
    assert re.search(
        rf'name="submission-submission_type" id="[^"]+" value="{C.SubmissionType.RAW_SAMPLES.id}" autocomplete="off"\s*checked',
        response.text,
    )
    assert re.search(rf'name="basic_info-group_id" value="{group.id}"', response.text)


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
    assert request.pi_contact is not None
    assert request.pi_contact.name == "Principal Investigator"
    assert request.pi_contact.email == "pi@example.com"
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


def _active_step(response) -> str | None:
    match = re.search(r'id="seq_request-step" value="([^"]+)"', response.text)
    return match.group(1) if match else None


def test_step_advances_to_next_step_when_valid(
    client: TestClient,
    user,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(f"step-{uuid4().hex}", step="basic_info"),
        token=user_token,
    )

    assert response.status_code == 200
    assert _active_step(response) == "contact"


def test_step_reports_field_errors_and_stays(
    client: TestClient,
    user,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload("", step="basic_info"),
        token=user_token,
    )

    assert_form_invalid(response, "Request Name is required")
    assert _active_step(response) == "basic_info"


def test_step_revalidates_earlier_steps(
    client: TestClient,
    user,
    user_token: str,
):
    payload = _request_payload(f"step-{uuid4().hex}", step="contact")
    del payload["disclaimer-accepted"]
    response = post_form(client, "/htmx/seq_requests/create/step", payload, token=user_token)

    assert_form_invalid(response, "You must accept the disclaimer")
    assert _active_step(response) == "disclaimer"


def test_submission_type_is_the_step_after_the_disclaimer(
    client: TestClient,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(f"step-{uuid4().hex}", step="disclaimer"),
        token=user_token,
    )

    assert response.status_code == 200
    assert _active_step(response) == "submission"


def test_step_requires_submission_type(
    client: TestClient,
    user_token: str,
):
    payload = _request_payload(f"step-{uuid4().hex}", step="submission")
    del payload["submission-submission_type"]
    response = post_form(client, "/htmx/seq_requests/create/step", payload, token=user_token)

    assert_form_invalid(response, "Submission Type is required")
    assert _active_step(response) == "submission"


def test_create_offers_only_enabled_submission_types(
    client: TestClient,
    user_token: str,
):
    response = get(client, "/htmx/seq_requests/create", token=user_token, htmx=True)

    assert response.status_code == 200
    offered = set(re.findall(r'name="submission-submission_type" id="[^"]+" value="(\d+)"', response.text))
    assert offered == {str(t.id) for t in C.SubmissionType.as_list(include_unpooled_libraries=False)}


def test_step_runs_cross_field_rules(
    client: TestClient,
    user,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(f"step-{uuid4().hex}", step="bioinformatician", **{"bioinformatician-name": "Bio Informatician"}),
        token=user_token,
    )

    assert_form_invalid(response, "Email is required when bioinformatician name is provided")
    assert _active_step(response) == "bioinformatician"


def test_step_ignores_later_steps(
    client: TestClient,
    user,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(f"step-{uuid4().hex}", step="basic_info", **{"billing-name": ""}),
        token=user_token,
    )

    assert response.status_code == 200
    assert _active_step(response) == "contact"


def test_step_rejects_unknown_step(
    client: TestClient,
    user,
    user_token: str,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(f"step-{uuid4().hex}", step="user_selection"),
        token=user_token,
    )

    assert response.status_code == 400


def test_insider_step_validates_requestor_selection(
    client: TestClient,
    insider_token: str,
    user_2,
):
    response = post_form(
        client,
        "/htmx/seq_requests/create/step",
        _request_payload(
            f"step-{uuid4().hex}",
            step="user_selection",
            **{"user_selection-user_id": str(user_2.id), "user_selection-email": "mixed@example.com"},
        ),
        token=insider_token,
    )

    assert_form_invalid(response, "not both")
    assert _active_step(response) == "user_selection"


def test_edit_step_advances_to_next_step(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    session.commit()
    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit/step",
        _request_payload(request.name, step="technical_info"),
        token=user_token,
    )

    assert response.status_code == 200
    assert _active_step(response) == "bioinformatician"


def test_edit_form_has_no_requestor_step_for_insider(
    client: TestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = get(client, f"/htmx/seq_requests/{request.id}/edit", token=insider_token, htmx=True)

    assert response.status_code == 200
    assert "user_selection-user_id" not in response.text

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit/step",
        _request_payload(request.name, step="user_selection"),
        token=insider_token,
    )
    assert response.status_code == 400


def test_edit_ignores_requestor_fields(
    client: TestClient,
    session: SyncSession,
    user,
    user_2,
    insider_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit",
        _request_payload(request.name, **{"user_selection-user_id": str(user_2.id)}),
        token=insider_token,
    )

    assert response.status_code == 204
    session.expire_all()
    session.refresh(request)
    assert request.requestor_id == user.id


def _timeline_states(response) -> list[str]:
    return re.findall(r'class="step-timeline-item step-(\w+)', response.text)


def test_edit_form_opens_with_all_steps_valid(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = get(client, f"/htmx/seq_requests/{request.id}/edit", token=user_token, htmx=True)

    assert response.status_code == 200
    states = _timeline_states(response)
    assert len(states) == 8
    assert set(states) == {"ok"}
    assert _active_step(response) == "submission"


def test_edit_step_flags_later_step_errors_without_blocking(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit/step",
        _request_payload(request.name, step="basic_info", **{"billing-name": ""}),
        token=user_token,
    )

    assert response.status_code == 200
    assert _active_step(response) == "contact"
    states = _timeline_states(response)
    assert states[-1] == "error"
    assert set(states[:-1]) == {"ok"}


def test_edit_step_stays_on_step_with_errors(
    client: TestClient,
    session: SyncSession,
    user,
    user_token: str,
):
    request = create_seq_request(session, user)
    session.commit()

    response = post_form(
        client,
        f"/htmx/seq_requests/{request.id}/edit/step",
        _request_payload(request.name, step="contact", **{"basic_info-name": ""}),
        token=user_token,
    )

    assert_form_invalid(response, "Request Name is required")
    assert _active_step(response) == "basic_info"


# ── PI prefilled from the requestor's profile ───────────────────────────────


def _input_value(response, field_id: str) -> str:
    match = re.search(rf'id="{field_id}" value="([^"]*)"', response.text)
    assert match is not None, field_id
    return match.group(1)


def _pi(response) -> tuple[str, str]:
    return _input_value(response, "contact-pi_name"), _input_value(response, "contact-pi_email")


def test_create_form_prefills_customer_pi(client: TestClient, session: SyncSession, user, user_token: str):
    set_profile(session, user)
    session.commit()

    assert _pi(get(client, "/htmx/seq_requests/create", user_token)) == (PI_NAME, PI_EMAIL)


def test_create_form_without_pi_leaves_it_empty(client: TestClient, user_token: str):
    assert _pi(get(client, "/htmx/seq_requests/create", user_token)) == ("", "")


def test_create_form_does_not_prefill_insider_pi(client: TestClient, session: SyncSession, insider, insider_token: str):
    set_profile(session, insider)
    session.commit()

    assert _pi(get(client, "/htmx/seq_requests/create", insider_token)) == ("", "")


def _requestor_step(client: TestClient, insider_token: str, **overrides: str):
    payload = _request_payload(
        f"step-{uuid4().hex}", step="user_selection",
        **{"contact-pi_name": "", "contact-pi_email": "", **overrides},
    )
    return post_form(client, "/htmx/seq_requests/create/step", payload, token=insider_token)


def test_requestor_step_prefills_requestor_pi(client: TestClient, session: SyncSession, user_2, insider_token: str):
    set_profile(session, user_2)
    session.commit()

    response = _requestor_step(client, insider_token, **{"user_selection-user_id": str(user_2.id)})

    assert _pi(response) == (PI_NAME, PI_EMAIL)


def test_requestor_step_keeps_typed_pi(client: TestClient, session: SyncSession, user_2, insider_token: str):
    set_profile(session, user_2)
    session.commit()

    response = _requestor_step(
        client, insider_token,
        **{"user_selection-user_id": str(user_2.id), "contact-pi_name": "Typed PI", "contact-pi_email": "typed@example.com"},
    )

    assert _pi(response) == ("Typed PI", "typed@example.com")


def test_requestor_step_ignores_insider_and_new_requestors(
    client: TestClient, session: SyncSession, insider, insider_token: str,
):
    set_profile(session, insider)
    session.commit()

    assert _pi(_requestor_step(client, insider_token, **{"user_selection-user_id": str(insider.id)})) == ("", "")
    new_user = {
        "user_selection-email": f"new-{uuid4().hex}@example.com",
        "user_selection-first_name": "New",
        "user_selection-last_name": "Requestor",
    }
    assert _pi(_requestor_step(client, insider_token, **new_user)) == ("", "")


def test_contact_step_is_not_prefilled_again(client: TestClient, session: SyncSession, user_2, insider_token: str):
    """Once the contact step was completed, an emptied PI stays empty."""
    set_profile(session, user_2)
    session.commit()

    payload = _request_payload(
        f"step-{uuid4().hex}", step="contact",
        **{"user_selection-user_id": str(user_2.id), "contact-pi_name": "", "contact-pi_email": ""},
    )
    response = post_form(client, "/htmx/seq_requests/create/step", payload, token=insider_token)

    assert _pi(response) == ("", "")
