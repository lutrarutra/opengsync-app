from typing import Literal

from fastapi import Depends, Request
from fastapi.responses import Response

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..SubHTMXForm import SubHTMXForm


class DisclaimerSubForm(SubHTMXForm):
    """Disclaimer that must be accepted."""

    accepted = inputs.boolean.CheckboxInputField("I have read and understood the disclaimer")

    def validate(self, raw_data: dict) -> bool:
        super().validate(raw_data)
        for field in self.input_fields:
            field.errors = []

        disclaimer_checked = self.accepted.validate_value(raw_data.get(self.accepted.name))
        self.accepted.data = disclaimer_checked
        if not disclaimer_checked:
            self.accepted.errors.append("You must accept the disclaimer")
            self.validated = True
            return False

        self.accepted.data = True
        self.validated = True
        return True


class BasicInfoSubForm(SubHTMXForm):
    """Basic information about the sequencing request."""

    name = inputs.string.StringInputField("Request Name", required=True)
    description = inputs.string.TextAreaInputField("Description", required=False)
    group_id = inputs.searchable.SearchableInputField("Group", route="search_groups", required=False)


class UserSelectionSubForm(SubHTMXForm):
    """User selection (insider only)."""

    user_id = inputs.searchable.SearchableInputField("User", route="search_users", required=False)


class TechnicalInfoSubForm(SubHTMXForm):
    """Technical requirements for sequencing."""

    submission_type = inputs.selectable.SelectableInputField("Submission Type", options=C.SubmissionType.as_selectable(include_unpooled_libraries=False))
    read_type = inputs.selectable.SelectableInputField("Read Type", options=C.ReadType.as_selectable())
    read_length = inputs.string.StringInputField("Read Length", required=False)
    num_lanes = inputs.string.StringInputField("Number of Lanes", required=False)
    data_delivery_mode = inputs.selectable.SelectableInputField("Data Delivery Mode", options=C.DataDeliveryMode.as_selectable())
    special_requirements = inputs.string.TextAreaInputField("Special Requirements", required=False)


class ContactSubForm(SubHTMXForm):
    """Contact person for the request."""

    current_user_is_contact = inputs.boolean.SwitchInputField("Requestor is the contact person")
    name = inputs.string.StringInputField("Contact Person Name", required=True)
    email = inputs.string.StringInputField("Contact Person Email", required=True)
    phone = inputs.string.StringInputField("Contact Person Phone", required=False)


class BioinformaticianSubForm(SubHTMXForm):
    """Bioinformatician contact (optional)."""

    name = inputs.string.StringInputField("Bioinformatician Name", required=False)
    email = inputs.string.StringInputField("Bioinformatician Email", required=False)
    phone = inputs.string.StringInputField("Bioinformatician Phone", required=False)


class OrganizationSubForm(SubHTMXForm):
    """Organization information."""

    name = inputs.string.StringInputField("Organization Name", required=True)
    email = inputs.string.StringInputField("Organization Email", required=False)
    phone = inputs.string.StringInputField("Organization Phone", required=False)
    address = inputs.string.TextAreaInputField("Organization Address", required=True)


class BillingSubForm(SubHTMXForm):
    """Billing information."""

    code = inputs.string.StringInputField("Billing Code", required=False)
    name = inputs.string.StringInputField("Billing Contact Name", required=True)
    email = inputs.string.StringInputField("Billing Contact Email", required=True)
    phone = inputs.string.StringInputField("Billing Contact Phone", required=False)


class SeqRequestForm(HTMXForm):
    template_path = "forms/seq_request/seq_request.html"

    disclaimer = DisclaimerSubForm()
    basic_info = BasicInfoSubForm()
    user_selection = UserSelectionSubForm()
    technical_info = TechnicalInfoSubForm()
    contact = ContactSubForm()
    bioinformatician = BioinformaticianSubForm()
    organization = OrganizationSubForm()
    billing = BillingSubForm()

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        seq_request: models.SeqRequest | None = None,
    ) -> None:
        super().__init__()
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

    @staticmethod
    def _validate_bioinformatician(form: "SeqRequestForm"):
        """If bioinformatician name is given, email is required."""
        if (
            form.bioinformatician.name.data
            and not form.bioinformatician.email.data
        ):
            form.bioinformatician.email.errors.append(
                "Email is required when bioinformatician name is provided."
            )

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            seq_request_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "SeqRequestForm":
            if form_type == "edit" and seq_request_id is None:
                raise exc.OpeNGSyncServerException("SeqRequest ID must be provided for edit form.")
            
            seq_request = None
            if seq_request_id is not None:
                seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
            return SeqRequestForm(form_type=form_type, seq_request=seq_request)
        
        return dependency

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Init(form_type="create"))
        ):  
            if current_user.is_insider:
                form.disclaimer.validated = True
                form.disclaimer.accepted.data = True
            form.contact.name.data = current_user.name or ""
            form.contact.email.data = current_user.email or ""
            return form.make_response()
        return route

    @htmx_route("GET", "/{seq_request_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Init(form_type="edit"))
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this request.")
            if form.seq_request is None:
                raise exc.OpeNGSyncServerException("SeqRequest ID must be provided for edit form.")
            
            form.basic_info.name.data = form.seq_request.name or ""
            form.basic_info.description.data = form.seq_request.description or ""

            # Technical info
            form.technical_info.read_type.data = form.seq_request.read_type
            form.technical_info.read_length.data = (
                str(form.seq_request.read_length) if form.seq_request.read_length else ""
            )
            form.technical_info.num_lanes.data = (
                str(form.seq_request.num_lanes) if form.seq_request.num_lanes else ""
            )
            form.technical_info.data_delivery_mode.data = form.seq_request.data_delivery_mode
            form.technical_info.special_requirements.data = (
                form.seq_request.special_requirements or ""
            )
            form.technical_info.submission_type.data = form.seq_request.submission_type.id

            # Contact
            if form.seq_request.contact_person:
                form.contact.name.data = form.seq_request.contact_person.name or ""
                form.contact.email.data = form.seq_request.contact_person.email or ""
                form.contact.phone.data = form.seq_request.contact_person.phone or ""

            # Bioinformatician
            if form.seq_request.bioinformatician_contact:
                form.bioinformatician.name.data = (
                    form.seq_request.bioinformatician_contact.name or ""
                )
                form.bioinformatician.email.data = (
                    form.seq_request.bioinformatician_contact.email or ""
                )
                form.bioinformatician.phone.data = (
                    form.seq_request.bioinformatician_contact.phone or ""
                )

            # Organization
            if form.seq_request.organization_contact:
                form.organization.name.data = (
                    form.seq_request.organization_contact.name or ""
                )
                form.organization.email.data = (
                    form.seq_request.organization_contact.email or ""
                )
                form.organization.phone.data = (
                    form.seq_request.organization_contact.phone or ""
                )
                form.organization.address.data = (
                    form.seq_request.organization_contact.address or ""
                )

            # Billing
            if form.seq_request.billing_contact:
                form.billing.name.data = form.seq_request.billing_contact.name or ""
                form.billing.email.data = form.seq_request.billing_contact.email or ""
                form.billing.phone.data = form.seq_request.billing_contact.phone or ""
                form.billing.code.data = form.seq_request.billing_code or ""

            return form.make_response()
        return route

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def route(
            request: Request,
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Validate(form_type="create"))
        ) -> Response:
            SeqRequestForm._validate_bioinformatician(form)

            if session.exists(Q.seq_request.select(name=form.basic_info.name.data)):
                form.basic_info.name.errors.append("A sequencing request with this name already exists.")
                raise exc.FormValidationException(form)

            if (
                form.bioinformatician.name.data
                and not form.bioinformatician.email.data
            ):
                raise exc.FormValidationException(form)

            current_user = request.state.current_user

            if form.user_selection.user_id.data:
                selected_user = session.first(Q.user.select(id=int(form.user_selection.user_id.data)))
                if selected_user is None:
                    form.user_selection.user_id.errors.append("Selected user not found.")
                    raise exc.FormValidationException(form)

            contact_person = Q.contact.create(
                form.contact.name.data,
                form.contact.email.data,
                form.contact.phone.data,
            )
            if (
                form.bioinformatician.name.data
                and form.bioinformatician.email.data
            ):
                bioinformatician = Q.contact.create(
                    form.bioinformatician.name.data,
                    form.bioinformatician.email.data,
                    form.bioinformatician.phone.data,
                )
            else:
                bioinformatician = None

            organization = Q.contact.create(
                form.organization.name.data,
                form.organization.email.data,
                form.organization.phone.data,
                form.organization.address.data,
            )

            billing_contact = Q.contact.create(
                form.billing.name.data,
                form.billing.email.data,
                form.billing.phone.data,
            )

            seq_request = session.save(
                Q.seq_request.create(
                    name=form.basic_info.name.data,
                    description=form.basic_info.description.data,
                    read_type=C.ReadType.get(form.technical_info.read_type.data),
                    read_length=int(form.technical_info.read_length.data) if form.technical_info.read_length.data else None,
                    num_lanes=int(form.technical_info.num_lanes.data) if form.technical_info.num_lanes.data else None,
                    data_delivery_mode=C.DataDeliveryMode.get(form.technical_info.data_delivery_mode.data),
                    special_requirements=form.technical_info.special_requirements.data,
                    submission_type=C.SubmissionType.get(form.technical_info.submission_type.data),
                    billing_code=form.billing.code.data or None,
                    contact_person=contact_person,
                    bioinformatician_contact=bioinformatician,
                    organization_contact=organization,
                    billing_contact=billing_contact,
                    requestor=current_user,
                    group=session.get_one(Q.group.select(id=form.basic_info.group_id.data)) if form.basic_info.group_id.data else None,
                ),
                flush=True,
            )

            return responses.htmx_response(
                redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=responses.flash("Sequencing Request Created!", "success"),
            )
        return route

    @htmx_route("POST", "/{seq_request_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def route(
            seq_request_id: int,
            request: Request,
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Validate(form_type="edit")),
        ) -> Response:
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException(
                    "You do not have permission to edit this request."
                )

            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))

            # If not draft, only insiders can edit
            if (
                seq_request.status_id != C.SeqRequestStatus.DRAFT.id
                and access_level < C.AccessLevel.INSIDER
            ):
                raise exc.NoPermissionsException(
                    "Submitted requests can only be edited by insiders."
                )

            SeqRequestForm._validate_bioinformatician(form)

            if (
                form.bioinformatician.name.data
                and not form.bioinformatician.email.data
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
            seq_request.billing_code = form.billing.code.data or None

            # Sync contacts
            seq_request.contact_person.name = form.contact.name.data
            seq_request.contact_person.email = form.contact.email.data
            seq_request.contact_person.phone = form.contact.phone.data

            if (
                form.bioinformatician.name.data
                and form.bioinformatician.email.data
            ):
                if seq_request.bioinformatician_contact is None:
                    seq_request.bioinformatician_contact = Q.contact.create(
                        form.bioinformatician.name.data,
                        form.bioinformatician.email.data,
                        form.bioinformatician.phone.data,
                    )
                else:
                    seq_request.bioinformatician_contact.name = (
                        form.bioinformatician.name.data
                    )
                    seq_request.bioinformatician_contact.email = (
                        form.bioinformatician.email.data
                    )
                    seq_request.bioinformatician_contact.phone = (
                        form.bioinformatician.phone.data
                    )
            else:
                seq_request.bioinformatician_contact = None

            seq_request.organization_contact.name = form.organization.name.data
            seq_request.organization_contact.email = (
                form.organization.email.data
            )
            seq_request.organization_contact.phone = (
                form.organization.phone.data
            )
            seq_request.organization_contact.address = (
                form.organization.address.data
            )

            session.save(seq_request)

            return responses.htmx_response(
                redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route
