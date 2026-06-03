"""
SeqRequestForm — FastAPI HTMXForm for creating and editing sequencing requests.

Ported from Flask/WTForms SeqRequestForm. Uses the same @staticmethod
async def process_request() pattern as LoginForm, with Depends() for DI.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Depends, Request, Response
from sqlalchemy import select

from opengsync_db.models import (
    Contact,
    SeqRequest,
    User,
)
from opengsync_db import categories as C, AsyncSession, queries as Q

from .. import HTMXForm
from ...components.inputs import (
    InputField,
    selectable,
    string
)


# ---------------------------------------------------------------------------
# Sub-form field groups (mirrors the Flask sub-form structure)
# ---------------------------------------------------------------------------

class _UserSelectFields:
    """User selection — insider-only: pick an existing user or create a new one."""

    user_id = selectable.SelectableInputField(
        "user_id",
        description="User",
        options=[],
        required=False,
    )
    new_user_email = string.EmailInputField("new_user_email", description="New User Email", required=False)
    new_user_name = string.StringInputField("new_user_name", description="New User Name", required=False)


class _BasicInfoFields:
    name = string.StringInputField("name", description="Request Name", required=True)
    description = string.StringInputField("description", description="Description", required=False)


class _TechnicalInfoFields:
    read_type = selectable.SelectableInputField(
        "read_type",
        description="Read Type",
        options=[
            ("single_end", "Single End"),
            ("paired_end", "Paired End"),
        ],
        required=True,
    )
    read_length = string.StringInputField("read_length", description="Read Length", required=True, placeholder="e.g. 150")
    num_lanes = string.StringInputField("num_lanes", description="Number of Lanes", required=True, placeholder="e.g. 1")
    data_delivery_mode = selectable.SelectableInputField(
        "data_delivery_mode",
        description="Data Delivery Mode",
        options=[
            ("download", "Download"),
            ("hard_drive", "Hard Drive"),
        ],
        required=True,
    )
    special_requirements = string.StringInputField(
        "special_requirements",
        description="Special Requirements",
        required=False,
    )


class _DataProcessingFields:
    """Currently a placeholder — no fields in Flask version."""


class _ContactFields:
    contact_person_name = string.StringInputField("contact_person_name", description="Contact Person Name", required=True)
    contact_person_email = string.EmailInputField("contact_person_email", description="Contact Person Email", required=True)
    contact_person_phone = string.StringInputField("contact_person_phone", description="Contact Person Phone", required=False)
    contact_person_address = string.StringInputField("contact_person_address", description="Contact Person Address", required=False)


class _BioinformaticianFields:
    bioinformatician_name = string.StringInputField("bioinformatician_name", description="Bioinformatician Name", required=False)
    bioinformatician_email = string.EmailInputField("bioinformatician_email", description="Bioinformatician Email", required=False)
    bioinformatician_phone = string.StringInputField("bioinformatician_phone", description="Bioinformatician Phone", required=False)
    bioinformatician_address = string.StringInputField("bioinformatician_address", description="Bioinformatician Address", required=False)


class _OrganizationFields:
    organization_name = string.StringInputField("organization_name", description="Organization Name", required=False)
    organization_email = string.EmailInputField("organization_email", description="Organization Email", required=False)
    organization_phone = string.StringInputField("organization_phone", description="Organization Phone", required=False)
    organization_address = string.StringInputField("organization_address", description="Organization Address", required=False)


class _BillingFields:
    billing_code = string.StringInputField("billing_code", description="Billing Code", required=False)
    billing_contact_name = string.StringInputField("billing_contact_name", description="Billing Contact Name", required=False)
    billing_contact_email = string.EmailInputField("billing_contact_email", description="Billing Contact Email", required=False)
    billing_contact_phone = string.StringInputField("billing_contact_phone", description="Billing Contact Phone", required=False)
    billing_contact_address = string.StringInputField("billing_contact_address", description="Billing Contact Address", required=False)


class _SubmissionFields:
    submission_type = selectable.SelectableInputField(
        "submission_type",
        options=C.SubmissionType.as_selectable(),
        required=True,
    )
    # delivery_emails = selectable.StringInputField(
    #     "delivery_emails",
    #     "Delivery Emails",
    #     required=False,
    #     placeholder="Comma-separated email addresses",
    # )


# ---------------------------------------------------------------------------
# Main SeqRequestForm
# ---------------------------------------------------------------------------

class SeqRequestForm(HTMXForm):
    """HTMX form for creating and editing sequencing requests.

    Usage in routes:
        @router.get("/create")
        async def create_seq_request(request: Request, ...):
            form = SeqRequestForm(request, form_type="create")
            return form.make_response(request, ...)

        @router.post("/create")
        async def create_seq_request_post(request: Request, ...):
            return await SeqRequestForm.process_request(request, ...)

        @router.get("/edit/{seq_request_id}")
        async def edit_seq_request(request: Request, seq_request_id: int, ...):
            form = SeqRequestForm(request, form_type="edit", seq_request_id=seq_request_id)
            return form.make_response(request, ...)

        @router.post("/edit/{seq_request_id}")
        async def edit_seq_request_post(request: Request, seq_request_id: int, ...):
            return await SeqRequestForm.process_request(request, ..., seq_request_id=seq_request_id)
    """

    template_path = "forms/seq_request/seq_request.html"

    # ---- Input fields (aggregated from all sub-forms) ----

    # User select (insider only)
    user_id = _UserSelectFields.user_id
    new_user_email = _UserSelectFields.new_user_email
    new_user_name = _UserSelectFields.new_user_name

    # Basic info
    name = _BasicInfoFields.name
    description = _BasicInfoFields.description

    # Technical info
    read_type = _TechnicalInfoFields.read_type
    read_length = _TechnicalInfoFields.read_length
    num_lanes = _TechnicalInfoFields.num_lanes
    data_delivery_mode = _TechnicalInfoFields.data_delivery_mode
    special_requirements = _TechnicalInfoFields.special_requirements

    # Contact person
    contact_person_name = _ContactFields.contact_person_name
    contact_person_email = _ContactFields.contact_person_email
    contact_person_phone = _ContactFields.contact_person_phone
    contact_person_address = _ContactFields.contact_person_address

    # Bioinformatician
    bioinformatician_name = _BioinformaticianFields.bioinformatician_name
    bioinformatician_email = _BioinformaticianFields.bioinformatician_email
    bioinformatician_phone = _BioinformaticianFields.bioinformatician_phone
    bioinformatician_address = _BioinformaticianFields.bioinformatician_address

    # Organization
    organization_name = _OrganizationFields.organization_name
    organization_email = _OrganizationFields.organization_email
    organization_phone = _OrganizationFields.organization_phone
    organization_address = _OrganizationFields.organization_address

    # Billing
    billing_code = _BillingFields.billing_code
    billing_contact_name = _BillingFields.billing_contact_name
    billing_contact_email = _BillingFields.billing_contact_email
    billing_contact_phone = _BillingFields.billing_contact_phone
    billing_contact_address = _BillingFields.billing_contact_address

    # Submission
    submission_type = _SubmissionFields.submission_type
    # delivery_emails = _SubmissionFields.delivery_emails

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        request: Request,
        form_type: str = "create",
        seq_request_id: int | None = None,
    ) -> None:
        """Initialise the form.

        Args:
            request: The FastAPI Request.
            form_type: "create" or "edit".
            seq_request_id: Required when form_type == "edit".
        """
        super().__init__(request)
        self.form_type = form_type
        self.seq_request_id = seq_request_id
        self._seq_request: SeqRequest | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_create(self) -> bool:
        return self.form_type == "create"

    @property
    def is_edit(self) -> bool:
        return self.form_type == "edit"

    # def _parse_delivery_emails(self) -> list[str]:
    #     """Parse comma/whitespace-separated delivery emails into a list."""
    #     raw = (self.delivery_emails.data or "").strip()
    #     if not raw:
    #         return []
    #     return [e.strip() for e in re.split(r"[,\s]+", raw) if e.strip()]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate(self) -> None:
        """Run field-level and cross-field validation.

        Called by HTMXForm.validate() after populating fields from request.form().
        """
        await super().validate()

        # --- Insider-only: user selection ---
        # (We can't check current_user here — that's done in process_request.
        #  Here we just validate field consistency.)

        if self.new_user_email.data and not self.new_user_name.data:
            self.new_user_name.errors.append("Name is required when creating a new user.")

        if self.new_user_name.data and not self.new_user_email.data:
            self.new_user_email.errors.append("Email is required when creating a new user.")

        # --- Bioinformatician: if name given, email is required ---
        if self.bioinformatician_name.data and not self.bioinformatician_email.data:
            self.bioinformatician_email.errors.append("Email is required when bioinformatician name is provided.")

        # --- Submission type ---
        if self.submission_type.data not in ("new", "reseq"):
            self.submission_type.errors.append("Invalid submission type.")

        # --- Delivery emails format ---
        # emails = self._parse_delivery_emails()
        # for email in emails:
        #     if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        #         self.delivery_emails.errors.append(f"Invalid email: {email}")
        #         break

    # ------------------------------------------------------------------
    # Context for template rendering
    # ------------------------------------------------------------------

    # def get_context(self) -> dict[str, Any]:
    #     ctx = super().get_context()
    #     ctx.update(
    #         {
    #             "form_type": self.form_type,
    #             "seq_request_id": self.seq_request_id,
    #             "seq_request": self._seq_request,
    #         }
    #     )
    #     return ctx

    # ------------------------------------------------------------------
    # Prepare (pre-fill for create mode)
    # ------------------------------------------------------------------

    async def prepare(self, current_user: User) -> None:
        """Pre-fill form fields for create mode."""
        if not self.is_create:
            return

        # Pre-fill contact person from current user
        self.contact_person_name.data = current_user.name or ""
        self.contact_person_email.data = current_user.email or ""

    # ------------------------------------------------------------------
    # Fill from existing SeqRequest (edit mode)
    # ------------------------------------------------------------------

    async def fill_from_seq_request(self, seq_request: SeqRequest) -> None:
        """Pre-fill all fields from an existing SeqRequest."""
        self._seq_request = seq_request

        self.name.data = seq_request.name or ""
        self.description.data = seq_request.description or ""
        self.read_type.data = seq_request.read_type or ""
        self.read_length.data = str(seq_request.read_length) if seq_request.read_length else ""
        self.num_lanes.data = str(seq_request.num_lanes) if seq_request.num_lanes else ""
        self.data_delivery_mode.data = seq_request.data_delivery_mode or ""
        self.special_requirements.data = seq_request.special_requirements or ""
        self.submission_type.data = seq_request.submission_type or ""
        self.billing_code.data = seq_request.billing_code or ""

        # Delivery emails
        # self.delivery_emails.data = ", ".join(
        #     link.email for link in seq_request.delivery_email_links
        # )

        # Contacts
        if seq_request.contact_person:
            self.contact_person_name.data = seq_request.contact_person.name or ""
            self.contact_person_email.data = seq_request.contact_person.email or ""
            self.contact_person_phone.data = seq_request.contact_person.phone or ""
            self.contact_person_address.data = seq_request.contact_person.address or ""

        if seq_request.bioinformatician_contact:
            self.bioinformatician_name.data = seq_request.bioinformatician_contact.name or ""
            self.bioinformatician_email.data = seq_request.bioinformatician_contact.email or ""
            self.bioinformatician_phone.data = seq_request.bioinformatician_contact.phone or ""
            self.bioinformatician_address.data = seq_request.bioinformatician_contact.address or ""

        if seq_request.organization_contact:
            self.organization_name.data = seq_request.organization_contact.name or ""
            self.organization_email.data = seq_request.organization_contact.email or ""
            self.organization_phone.data = seq_request.organization_contact.phone or ""
            self.organization_address.data = seq_request.organization_contact.address or ""

        if seq_request.billing_contact:
            self.billing_contact_name.data = seq_request.billing_contact.name or ""
            self.billing_contact_email.data = seq_request.billing_contact.email or ""
            self.billing_contact_phone.data = seq_request.billing_contact.phone or ""
            self.billing_contact_address.data = seq_request.billing_contact.address or ""

    # ------------------------------------------------------------------
    # Contact helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_contact(
        session,
        name: str | None,
        email: str | None,
        phone: str | None,
        address: str | None,
    ) -> Contact | None:
        """Return a new Contact if any field is non-empty, else None."""
        if not any((name, email, phone, address)):
            return None
        return Contact(
            name=name or "",
            email=email or "",
            phone=phone or "",
            address=address or "",
        )

    @staticmethod
    async def _sync_contact(
        session,
        existing: Contact | None,
        name: str | None,
        email: str | None,
        phone: str | None,
        address: str | None,
    ) -> Contact | None:
        """Update an existing contact or create a new one. Returns None if all fields empty."""
        if not any((name, email, phone, address)):
            return None
        if existing is not None:
            existing.name = name or ""
            existing.email = email or ""
            existing.phone = phone or ""
            existing.address = address or ""
            return existing
        return Contact(
            name=name or "",
            email=email or "",
            phone=phone or "",
            address=address or "",
        )

    # ------------------------------------------------------------------
    # Create new SeqRequest
    # ------------------------------------------------------------------

    async def _create_new_request(
        self,
        session,
        current_user: User,
        is_insider: bool,
    ) -> SeqRequest:
        """Create a new SeqRequest and associated contacts/delivery links."""

        # Determine the requestor user
        if is_insider and self.user_id.data:
            requestor = await session.first(
                select(User).where(User.id == int(self.user_id.data))
            )
            if requestor is None:
                self.user_id.error = "Selected user not found."
                from ...core.exceptions import FormValidationException
                raise FormValidationException(self)
        elif is_insider and self.new_user_email.data:
            requestor = Q.user.create(
                name=self.new_user_name.data or "",
                first_name=self.new_user_name.data,
                email=self.new_user_email.data,
            )
            session.add(requestor)
            await session.flush()
        else:
            requestor = current_user

        # Build contacts
        contact_person = self._get_or_create_contact(
            session,
            self.contact_person_name.data,
            self.contact_person_email.data,
            self.contact_person_phone.data,
            self.contact_person_address.data,
        )
        bioinformatician = self._get_or_create_contact(
            session,
            self.bioinformatician_name.data,
            self.bioinformatician_email.data,
            self.bioinformatician_phone.data,
            self.bioinformatician_address.data,
        )
        organization = self._get_or_create_contact(
            session,
            self.organization_name.data,
            self.organization_email.data,
            self.organization_phone.data,
            self.organization_address.data,
        )
        billing_contact = self._get_or_create_contact(
            session,
            self.billing_contact_name.data,
            self.billing_contact_email.data,
            self.billing_contact_phone.data,
            self.billing_contact_address.data,
        )

        seq_request = SeqRequest(
            name=self.name.data or "",
            description=self.description.data or "",
            requestor=requestor,
            group=None,  # FIXME
            read_type=self.read_type.data or "",
            read_length=int(self.read_length.data) if self.read_length.data else None,
            num_lanes=int(self.num_lanes.data) if self.num_lanes.data else None,
            data_delivery_mode=self.data_delivery_mode.data or "",
            special_requirements=self.special_requirements.data or "",
            submission_type=self.submission_type.data or "",
            billing_code=self.billing_code.data or "",
            contact_person=contact_person,
            bioinformatician_contact=bioinformatician,
            organization_contact=organization,
            billing_contact=billing_contact,
            status=C.SeqRequestStatus.DRAFT,
        )

        session.add(seq_request)
        await session.flush()

        # FIXME
        # for email in self._parse_delivery_emails():
        #     link = SeqRequestDeliveryEmailLink(
        #         seq_request_id=seq_request.id,
        #         email=email,
        #         status=DeliveryStatus.PENDING,
        #     )
        #     session.add(link)

        await session.flush()
        return seq_request

    # ------------------------------------------------------------------
    # Edit existing SeqRequest
    # ------------------------------------------------------------------

    async def _edit_existing_request(
        self,
        session,
        seq_request: SeqRequest,
    ) -> SeqRequest:
        """Update an existing SeqRequest."""

        seq_request.name = self.name.data or ""
        seq_request.description = self.description.data or ""
        seq_request.read_type = self.read_type.data or ""
        seq_request.read_length = int(self.read_length.data) if self.read_length.data else None
        seq_request.num_lanes = int(self.num_lanes.data) if self.num_lanes.data else None
        seq_request.data_delivery_mode = self.data_delivery_mode.data or ""
        seq_request.special_requirements = self.special_requirements.data or ""
        seq_request.submission_type = self.submission_type.data or ""
        seq_request.billing_code = self.billing_code.data or ""

        # Sync contacts
        seq_request.contact_person = await self._sync_contact(
            session,
            seq_request.contact_person,
            self.contact_person_name.data,
            self.contact_person_email.data,
            self.contact_person_phone.data,
            self.contact_person_address.data,
        )
        seq_request.bioinformatician_contact = await self._sync_contact(
            session,
            seq_request.bioinformatician_contact,
            self.bioinformatician_name.data,
            self.bioinformatician_email.data,
            self.bioinformatician_phone.data,
            self.bioinformatician_address.data,
        )
        seq_request.organization_contact = await self._sync_contact(
            session,
            seq_request.organization_contact,
            self.organization_name.data,
            self.organization_email.data,
            self.organization_phone.data,
            self.organization_address.data,
        )
        seq_request.billing_contact = await self._sync_contact(
            session,
            seq_request.billing_contact,
            self.billing_contact_name.data,
            self.billing_contact_email.data,
            self.billing_contact_phone.data,
            self.billing_contact_address.data,
        )

        # Delivery emails — replace existing links
        existing_emails = {link.email for link in seq_request.delivery_email_links}
        new_emails = set(self._parse_delivery_emails())

        # Remove links no longer present
        for link in list(seq_request.delivery_email_links):
            if link.email not in new_emails:
                await session.delete(link)

        # Add new links
        for email in new_emails - existing_emails:
            link = SeqRequestDeliveryEmailLink(
                seq_request_id=seq_request.id,
                email=email,
                status=DeliveryStatus.PENDING,
            )
            session.add(link)

        await session.flush()
        return seq_request

    # ------------------------------------------------------------------
    # Main entry point — process_request
    # ------------------------------------------------------------------

    @staticmethod
    async def process_request(
        request: Request,
        session: SessionDep,
        current_user: User,
        form_type: str = "create",
        seq_request_id: int | None = None,
    ) -> Response:
        """Validate and process the SeqRequest form.

        Args:
            request: FastAPI Request.
            response: FastAPI Response.
            session: Database session (injected).
            bcrypt: Bcrypt compat instance (injected).
            current_user: Authenticated user (injected).
            form_type: "create" or "edit".
            seq_request_id: Required for edit mode.

        Returns:
            HTMX redirect response on success, or re-rendered form on error.
        """
        from ...core.responses import htmx_response

        is_insider = current_user.is_insider

        form = SeqRequestForm(request, form_type=form_type, seq_request_id=seq_request_id)

        # ---- Edit mode: load existing SeqRequest ----
        if form_type == "edit":
            if seq_request_id is None:
                raise ValueError("seq_request_id is required for edit mode.")

            seq_request = await session.first(
                select(SeqRequest).where(SeqRequest.id == seq_request_id)
            )
            if seq_request is None:
                return htmx_response(redirect="/seq-requests")

            # Permission check: only owner or insider can edit
            if not is_insider and seq_request.requestor_id != current_user.id:
                return htmx_response(redirect="/seq-requests")

            if not seq_request.is_editable:
                # Already submitted — redirect
                return htmx_response(redirect=f"/seq-requests/{seq_request_id}")

            await form.fill_from_seq_request(seq_request)

        # ---- Validate ----
        try:
            form.validate()
        except FormValidationException:
            return await form.make_response(status_code=409)

        if not form.is_valid:
            return await form.make_response(status_code=409)

        # ---- Insider-only: bioinformatician email required ----
        if is_insider and form.bioinformatician_name.data and not form.bioinformatician_email.data:
            form.bioinformatician_email.error = "Bioinformatician email is required."
            return await form.make_response(status_code=409)

        # ---- Duplicate name check (create mode) ----
        if form_type == "create":
            existing = await session.first(
                select(SeqRequest).where(SeqRequest.name == form.name.data)
            )
            if existing is not None:
                form.name.error = "A sequencing request with this name already exists."
                return await form.make_response(status_code=409)

        # ---- Process ----
        try:
            if form_type == "create":
                seq_request = await form._create_new_request(session, current_user, is_insider)
            else:
                seq_request = await form._edit_existing_request(session, seq_request)

            await session.commit()

            return htmx_response(
                redirect=f"/seq-requests/{seq_request.id}",
            )

        except FormValidationException:
            await session.rollback()
            return await form.make_response(status_code=409)
        except Exception:
            await session.rollback()
            raise