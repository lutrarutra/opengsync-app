from typing import Literal

from fastapi import Depends, Request
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import AsyncSession, models, queries as Q, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ...components.inputs.switch import SwitchInputField
from ..HTMXForm import HTMXForm
from ..SubHTMXForm import SubHTMXForm


class BasicInfoSubForm(SubHTMXForm):
    """Basic information about the sequencing request."""

    title = "Request Info"
    order = 1
    collapsed = False
    icon = "bi-info-circle"

    name = inputs.string.StringInputField("Request Name", required=True)
    description = inputs.string.TextAreaInputField("Description", required=False)


class TechnicalInfoSubForm(SubHTMXForm):
    """Technical requirements for sequencing."""

    title = "Technical Requirements"
    order = 2
    collapsed = False
    icon = "bi-cpu"

    submission_type = inputs.selectable.SelectableInputField(
        "Submission Type",
        options=C.SubmissionType.as_selectable(),
        required=True,
    )
    read_type = inputs.selectable.SelectableInputField(
        "Read Type",
        options=C.ReadType.as_selectable(),
    )
    read_length = inputs.string.StringInputField("Read Length", required=False)
    num_lanes = inputs.string.StringInputField("Number of Lanes", required=False)
    data_delivery_mode = inputs.selectable.SelectableInputField(
        "Data Delivery Mode",
        options=C.DataDeliveryMode.as_selectable(),
    )
    special_requirements = inputs.string.TextAreaInputField(
        "Special Requirements", required=False
    )


class ContactSubForm(SubHTMXForm):
    """Contact person for the request."""

    title = "Contact Person"
    order = 3
    collapsed = False
    icon = "bi-person"

    current_user_is_contact = SwitchInputField("Requestor is the contact person")
    contact_person_name = inputs.string.StringInputField(
        "Contact Person Name", required=True
    )
    contact_person_email = inputs.string.StringInputField(
        "Contact Person Email", required=True
    )
    contact_person_phone = inputs.string.StringInputField(
        "Contact Person Phone", required=False
    )


class BioinformaticianSubForm(SubHTMXForm):
    """Bioinformatician contact (optional)."""

    title = "Bioinformatician Contact"
    order = 4
    collapsed = True
    icon = "bi-robot"

    bioinformatician_name = inputs.string.StringInputField(
        "Bioinformatician Name", required=False
    )
    bioinformatician_email = inputs.string.StringInputField(
        "Bioinformatician Email", required=False
    )
    bioinformatician_phone = inputs.string.StringInputField(
        "Bioinformatician Phone", required=False
    )


class OrganizationSubForm(SubHTMXForm):
    """Organization information."""

    title = "Organization"
    order = 5
    collapsed = False
    icon = "bi-building"

    organization_name = inputs.string.StringInputField(
        "Organization Name", required=True
    )
    organization_email = inputs.string.StringInputField(
        "Organization Email", required=False
    )
    organization_phone = inputs.string.StringInputField(
        "Organization Phone", required=False
    )
    organization_address = inputs.string.StringInputField(
        "Organization Address", required=True
    )


class BillingSubForm(SubHTMXForm):
    """Billing information."""

    title = "Billing"
    order = 6
    collapsed = False
    icon = "bi-credit-card"

    billing_code = inputs.string.StringInputField("Billing Code", required=False)
    billing_contact_name = inputs.string.StringInputField(
        "Billing Contact Name", required=True
    )
    billing_contact_email = inputs.string.StringInputField(
        "Billing Contact Email", required=True
    )
    billing_contact_phone = inputs.string.StringInputField(
        "Billing Contact Phone", required=False
    )


class SeqRequestForm(HTMXForm):
    template_path = "forms/seq_request/seq_request.html"

    # Sub-forms (accordion sections)
    basic_info = BasicInfoSubForm()
    technical_info = TechnicalInfoSubForm()
    contact = ContactSubForm()
    bioinformatician = BioinformaticianSubForm()
    organization = OrganizationSubForm()
    billing = BillingSubForm()

    # Direct fields (not in accordion)
    user_id = inputs.searchable.SearchableInputField(
        "User", route="search_users", required=False
    )
    group_id = inputs.searchable.SearchableInputField(
        "Group", route="search_groups", required=False
    )

    def __init__(
        self,
        request: Request,
        form_type: Literal["create", "edit"],
        seq_request: models.SeqRequest | None = None,
    ) -> None:
        super().__init__(request)
        self.form_type = form_type
        self.seq_request = seq_request

        if form_type == "create" and seq_request is not None:
            raise exc.OpeNGSyncServerException(
                "SeqRequest must be None when form_type is 'create'."
            )
        if form_type == "edit" and seq_request is None:
            raise exc.OpeNGSyncServerException(
                "SeqRequest must be provided when form_type is 'edit'."
            )

    async def prepare(self) -> None:
        if self.form_type == "create":
            self.contact.contact_person_name.data = (
                self.request.state.current_user.name or ""
            )
            self.contact.contact_person_email.data = (
                self.request.state.current_user.email or ""
            )
        elif self.form_type == "edit" and self.seq_request is not None:
            sr = self.seq_request

            # Basic info
            self.basic_info.name.data = sr.name or ""
            self.basic_info.description.data = sr.description or ""

            # Technical info
            self.technical_info.read_type.data = sr.read_type
            self.technical_info.read_length.data = (
                str(sr.read_length) if sr.read_length else ""
            )
            self.technical_info.num_lanes.data = (
                str(sr.num_lanes) if sr.num_lanes else ""
            )
            self.technical_info.data_delivery_mode.data = sr.data_delivery_mode
            self.technical_info.special_requirements.data = (
                sr.special_requirements or ""
            )
            self.technical_info.submission_type.data = sr.submission_type.id

            # Contact
            if sr.contact_person:
                self.contact.contact_person_name.data = sr.contact_person.name or ""
                self.contact.contact_person_email.data = sr.contact_person.email or ""
                self.contact.contact_person_phone.data = sr.contact_person.phone or ""

            # Bioinformatician
            if sr.bioinformatician_contact:
                self.bioinformatician.bioinformatician_name.data = (
                    sr.bioinformatician_contact.name or ""
                )
                self.bioinformatician.bioinformatician_email.data = (
                    sr.bioinformatician_contact.email or ""
                )
                self.bioinformatician.bioinformatician_phone.data = (
                    sr.bioinformatician_contact.phone or ""
                )

            # Organization
            if sr.organization_contact:
                self.organization.organization_name.data = (
                    sr.organization_contact.name or ""
                )
                self.organization.organization_email.data = (
                    sr.organization_contact.email or ""
                )
                self.organization.organization_phone.data = (
                    sr.organization_contact.phone or ""
                )
                self.organization.organization_address.data = (
                    sr.organization_contact.address or ""
                )

            # Billing
            if sr.billing_contact:
                self.billing.billing_contact_name.data = sr.billing_contact.name or ""
                self.billing.billing_contact_email.data = sr.billing_contact.email or ""
                self.billing.billing_contact_phone.data = sr.billing_contact.phone or ""
                self.billing.billing_code.data = sr.billing_code or ""

    @staticmethod
    def _validate_bioinformatician(form: "SeqRequestForm"):
        """If bioinformatician name is given, email is required."""
        if (
            form.bioinformatician.bioinformatician_name.data
            and not form.bioinformatician.bioinformatician_email.data
        ):
            form.bioinformatician.bioinformatician_email.errors.append(
                "Email is required when bioinformatician name is provided."
            )

    @staticmethod
    async def create(
        request: Request,
        current_user: models.User = Depends(dependencies.require_user),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        form = SeqRequestForm(request, form_type="create")
        await form.validate()

        SeqRequestForm._validate_bioinformatician(form)

        # Check for duplicate name
        if await session.exists(
            Q.seq_request.select(search_name=form.basic_info.name.data)
        ):
            form.basic_info.name.errors.append(
                "A sequencing request with this name already exists."
            )
            raise exc.FormValidationException(form)

        if (
            form.bioinformatician.bioinformatician_name.data
            and not form.bioinformatician.bioinformatician_email.data
        ):
            raise exc.FormValidationException(form)

        current_user = request.state.current_user

        # Determine requestor
        requestor_id = current_user.id
        if form.user_id.data:
            selected_user = await session.first(
                Q.user.select(id=int(form.user_id.data))
            )
            if selected_user is None:
                form.user_id.errors.append("Selected user not found.")
                raise exc.FormValidationException(form)
            requestor_id = selected_user.id

        # Build contacts
        contact_person = Q.contact.create(
            form.contact.contact_person_name.data,
            form.contact.contact_person_email.data,
            form.contact.contact_person_phone.data,
        )
        if (
            form.bioinformatician.bioinformatician_name.data
            and form.bioinformatician.bioinformatician_email.data
        ):
            bioinformatician = Q.contact.create(
                form.bioinformatician.bioinformatician_name.data,
                form.bioinformatician.bioinformatician_email.data,
                form.bioinformatician.bioinformatician_phone.data,
            )
        else:
            bioinformatician = None

        organization = Q.contact.create(
            form.organization.organization_name.data,
            form.organization.organization_email.data,
            form.organization.organization_phone.data,
            form.organization.organization_address.data,
        )

        billing_contact = Q.contact.create(
            form.billing.billing_contact_name.data,
            form.billing.billing_contact_email.data,
            form.billing.billing_contact_phone.data,
        )

        seq_request = await session.save(
            Q.seq_request.create(
                name=form.basic_info.name.data,
                description=form.basic_info.description.data,
                read_type=C.ReadType.get(form.technical_info.read_type.data),
                read_length=int(form.technical_info.read_length.data)
                if form.technical_info.read_length.data
                else None,
                num_lanes=int(form.technical_info.num_lanes.data)
                if form.technical_info.num_lanes.data
                else None,
                data_delivery_mode=C.DataDeliveryMode.get(
                    form.technical_info.data_delivery_mode.data
                ),
                special_requirements=form.technical_info.special_requirements.data,
                submission_type=C.SubmissionType.get(
                    form.technical_info.submission_type.data
                ),
                billing_code=form.billing.billing_code.data or None,
                contact_person=contact_person,
                bioinformatician_contact=bioinformatician,
                organization_contact=organization,
                billing_contact=billing_contact,
                requestor=current_user,
                group=await session.get_one(Q.group.select(id=form.group_id.data))
                if form.group_id.data
                else None,
            ),
            flush=True,
        )

        return await responses.htmx_response(
            redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
            flash=responses.flash("Sequencing Request Created!", "success"),
        )

    @staticmethod
    async def edit(
        seq_request_id: int,
        request: Request,
        session: AsyncSession = Depends(dependencies.db_session),
        access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException(
                "You do not have permission to edit this request."
            )

        seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id))

        # If not draft, only insiders can edit
        if (
            seq_request.status_id != C.SeqRequestStatus.DRAFT.id
            and access_level < C.AccessLevel.INSIDER
        ):
            raise exc.NoPermissionsException(
                "Submitted requests can only be edited by insiders."
            )

        form = SeqRequestForm(request, form_type="edit", seq_request=seq_request)
        await form.validate()

        SeqRequestForm._validate_bioinformatician(form)

        if (
            form.bioinformatician.bioinformatician_name.data
            and not form.bioinformatician.bioinformatician_email.data
        ):
            raise exc.FormValidationException(form)

        # Update basic info
        seq_request.name = form.basic_info.name.data
        seq_request.description = form.basic_info.description.data

        # Update technical info
        seq_request.read_type = C.ReadType.get(form.technical_info.read_type.data)
        seq_request.read_length = (
            int(form.technical_info.read_length.data)
            if form.technical_info.read_length.data
            else None
        )
        seq_request.num_lanes = (
            int(form.technical_info.num_lanes.data)
            if form.technical_info.num_lanes.data
            else None
        )
        seq_request.data_delivery_mode = C.DataDeliveryMode.get(
            form.technical_info.data_delivery_mode.data
        )
        seq_request.special_requirements = form.technical_info.special_requirements.data
        seq_request.billing_code = form.billing.billing_code.data or None

        # Sync contacts
        seq_request.contact_person.name = form.contact.contact_person_name.data
        seq_request.contact_person.email = form.contact.contact_person_email.data
        seq_request.contact_person.phone = form.contact.contact_person_phone.data

        if (
            form.bioinformatician.bioinformatician_name.data
            and form.bioinformatician.bioinformatician_email.data
        ):
            if seq_request.bioinformatician_contact is None:
                seq_request.bioinformatician_contact = Q.contact.create(
                    form.bioinformatician.bioinformatician_name.data,
                    form.bioinformatician.bioinformatician_email.data,
                    form.bioinformatician.bioinformatician_phone.data,
                )
            else:
                seq_request.bioinformatician_contact.name = (
                    form.bioinformatician.bioinformatician_name.data
                )
                seq_request.bioinformatician_contact.email = (
                    form.bioinformatician.bioinformatician_email.data
                )
                seq_request.bioinformatician_contact.phone = (
                    form.bioinformatician.bioinformatician_phone.data
                )
        else:
            seq_request.bioinformatician_contact = None

        seq_request.organization_contact.name = form.organization.organization_name.data
        seq_request.organization_contact.email = (
            form.organization.organization_email.data
        )
        seq_request.organization_contact.phone = (
            form.organization.organization_phone.data
        )
        seq_request.organization_contact.address = (
            form.organization.organization_address.data
        )

        await session.save(seq_request)

        return await responses.htmx_response(
            redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
            flash=responses.flash("Changes Saved!", "success"),
        )
