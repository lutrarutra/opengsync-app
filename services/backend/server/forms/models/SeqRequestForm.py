from typing import Literal

from fastapi import Cookie, Depends, Request
from fastapi.responses import Response

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...core import responses, dependencies, exceptions as exc, secrets
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..SubHTMXForm import SubHTMXForm


class DisclaimerSubForm(SubHTMXForm):
    """Disclaimer that must be accepted."""
    title = "Disclaimer"
    icon = "bi-exclamation-triangle"

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
    title = "Request Info"
    icon = "bi-info-circle"

    name = inputs.string.StringInputField("Request Name", required=True)
    description = inputs.string.TextAreaInputField("Description", required=False)
    group_id = inputs.searchable.SearchableInputField("Group", route="search_groups", required=False)


class UserSelectionSubForm(SubHTMXForm):
    """Existing or manually-created requestor (insider only)."""
    title = "Requestor"
    icon = "bi-person-plus"

    user_id = inputs.searchable.SearchableInputField("User", route="search_users", required=False)
    email = inputs.string.EmailInputField("New User Email", required=False)
    first_name = inputs.string.StringInputField("New User First Name", required=False)
    last_name = inputs.string.StringInputField("New User Last Name", required=False)


class TechnicalInfoSubForm(SubHTMXForm):
    """Technical requirements for sequencing."""
    title = "Technical Requirements"
    icon = "bi-cpu"

    submission_type = inputs.selectable.SelectableInputField("Submission Type", options=C.SubmissionType.as_selectable(include_unpooled_libraries=False))
    read_type = inputs.selectable.SelectableInputField(
        "Read Type",
        options=C.ReadType.as_selectable(),
        default=C.ReadType.PAIRED_END.id,
    )
    read_length = inputs.numeric.IntInputField("Read Length", required=False, ge=1)
    num_lanes = inputs.numeric.IntInputField("Number of Lanes", required=False, ge=1, le=8)
    data_delivery_mode = inputs.selectable.SelectableInputField("Data Delivery Mode", options=C.DataDeliveryMode.as_selectable(), default=C.DataDeliveryMode.CUSTOM.id)
    special_requirements = inputs.string.TextAreaInputField("Special Requirements", required=False)


class ContactSubForm(SubHTMXForm):
    """Contact person for the request."""
    title = "Contact Person"
    icon = "bi-person"

    current_user_is_contact = inputs.boolean.SwitchInputField("Requestor is the contact person")
    name = inputs.string.StringInputField("Contact Person Name", required=True)
    email = inputs.string.EmailInputField("Contact Person Email", required=True)
    phone = inputs.string.StringInputField("Contact Person Phone", required=True)
    pi_name = inputs.string.StringInputField("Principal Investigator Name", required=True)
    pi_email = inputs.string.EmailInputField("Principal Investigator Email", required=True)


class BioinformaticianSubForm(SubHTMXForm):
    """Bioinformatician contact (optional)."""
    title = "Bioinformatician Contact"
    icon = "bi-robot"

    name = inputs.string.StringInputField("Bioinformatician Name", required=False)
    email = inputs.string.EmailInputField("Bioinformatician Email", required=False)
    phone = inputs.string.StringInputField("Bioinformatician Phone", required=False)


class OrganizationSubForm(SubHTMXForm):
    """Organization name and address."""
    title = "Organization"
    icon = "bi-building"

    name = inputs.string.StringInputField("Organization Name", required=True)
    address = inputs.string.TextAreaInputField("Organization Address", required=True)


class BillingSubForm(SubHTMXForm):
    """Billing information."""
    title = "Billing"
    icon = "bi-credit-card"

    # UI-only: copies the organization name/address into the billing fields.
    use_organization = inputs.boolean.SwitchInputField("Use organization for billing")
    code = inputs.string.StringInputField("Billing Code", required=False)
    name = inputs.string.StringInputField("Billing Contact Name", required=True)
    email = inputs.string.EmailInputField("Billing Contact Email", required=True)
    phone = inputs.string.StringInputField("Billing Contact Phone", required=False)
    address = inputs.string.TextAreaInputField("Billing Address", required=True)


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

    # Order of the steps in the multi-step form.
    STEPS = ("disclaimer", "user_selection", "basic_info", "contact", "technical_info", "bioinformatician", "organization", "billing")

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        seq_request: models.SeqRequest | None = None,
        is_insider: bool = False,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.seq_request = seq_request
        self.is_insider = is_insider

        if form_type == "create":
            if seq_request is not None:
                raise exc.OpeNGSyncServerException("SeqRequest must be None when form_type is 'create'.")
        elif form_type == "edit":
            if seq_request is None:
                raise exc.OpeNGSyncServerException("SeqRequest must be provided when form_type is 'edit'.")
        else:
            raise exc.OpeNGSyncServerException("Invalid form_type. Must be 'create' or 'edit'.")

    @property
    def post_url(self):
        if self.form_type == "create":
            return responses.url_for("SeqRequestForm.Create")
        assert self.seq_request is not None
        return responses.url_for("SeqRequestForm.Edit", seq_request_id=self.seq_request.id)

    @property
    def step_url(self):
        if self.form_type == "create":
            return responses.url_for("SeqRequestForm.CreateStep")
        assert self.seq_request is not None
        return responses.url_for("SeqRequestForm.EditStep", seq_request_id=self.seq_request.id)

    @property
    def step_names(self) -> list[str]:
        return [name for name in self.STEPS if name != "user_selection" or self.is_insider]

    @property
    def steps(self) -> list[tuple[str, SubHTMXForm]]:
        return [(name, self.sub_form_dict[name]) for name in self.step_names]

    @property
    def active_step(self) -> str:
        """First step with errors, else the first step not validated yet, else the last step."""
        for name, sub_form in self.steps:
            if sub_form.has_errors:
                return name
        for name, sub_form in self.steps:
            if not sub_form.validated:
                return name
        return self.step_names[-1]

    def validate_rules(self, session: SyncSession, step_names: list[str]) -> None:
        """Cross-field and database checks for the given steps, run once their fields are valid."""
        def ready(name: str) -> bool:
            return name in step_names and self.sub_form_dict[name].is_valid

        if ready("basic_info") and self.form_type == "create":
            if session.exists(Q.seq_request.select(name=self.basic_info.name.data)):
                self.basic_info.name.errors.append("A sequencing request with this name already exists.")

        if ready("user_selection") and self.form_type == "create":
            user_id = self.user_selection.user_id.data
            new_user = (self.user_selection.email.data, self.user_selection.first_name.data, self.user_selection.last_name.data)
            if user_id and any(new_user):
                self.user_selection.user_id.errors.append("Select a user or enter new user details, not both.")
            elif user_id:
                if session.first(Q.user.select(id=int(user_id))) is None:
                    self.user_selection.user_id.errors.append("Selected user not found.")
            elif any(new_user):
                if not all(new_user):
                    self.user_selection.email.errors.append("Email, first name, and last name are required for a new user.")
                elif session.exists(Q.user.select(email=self.user_selection.email.data)):
                    self.user_selection.email.errors.append("Email already registered.")

        if ready("contact"):
            if bool(self.contact.pi_name.data) != bool(self.contact.pi_email.data):
                self.contact.pi_email.errors.append("PI name and email must be provided together.")

        if ready("bioinformatician"):
            if self.bioinformatician.name.data and not self.bioinformatician.email.data:
                self.bioinformatician.email.errors.append("Email is required when bioinformatician name is provided.")

    def validate_step(self, formdata: dict, csrf_token: str | None, session: SyncSession) -> Response:
        """Validate every step up to the submitted one and re-render the form at the next step.

        On errors, the form is re-rendered at the first step with errors instead.
        """
        step = formdata.get("step")
        if step not in self.step_names:
            raise exc.BadRequestException(f"Unknown step '{step}'.")

        completed = self.step_names[: self.step_names.index(step) + 1]
        self.validate_sub_forms(formdata, completed, csrf_token=csrf_token)
        self.validate_rules(session, completed)
        self.assert_valid()
        return self.make_response()

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            seq_request_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> "SeqRequestForm":
            if form_type == "edit" and seq_request_id is None:
                raise exc.OpeNGSyncServerException("SeqRequest ID must be provided for edit form.")

            seq_request = None
            if seq_request_id is not None:
                seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
            return SeqRequestForm(form_type=form_type, seq_request=seq_request, is_insider=current_user.is_insider)

        return dependency

    @htmx_route("POST", "/create/step", name="CreateStep")
    def CreateStep(cls) -> RouteFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            session: SyncSession = Depends(dependencies.db_session),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Init(form_type="create")),
        ) -> Response:
            return form.validate_step(request.state.form_data, csrf_token, session)
        return route

    @htmx_route("POST", "/{seq_request_id}/edit/step", name="EditStep")
    def EditStep(cls) -> RouteFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Init(form_type="edit")),
        ) -> Response:
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this request.")
            return form.validate_step(request.state.form_data, csrf_token, session)
        return route

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
            _ = Depends(dependencies.require_user),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Init(form_type="edit"))
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this request.")
            if form.seq_request is None:
                raise exc.OpeNGSyncServerException("SeqRequest ID must be provided for edit form.")

            form.disclaimer.validated = True
            form.disclaimer.accepted.data = True
            
            form.basic_info.name.data = form.seq_request.name or ""
            form.basic_info.description.data = form.seq_request.description or ""

            # Technical info
            form.technical_info.read_type.data = form.seq_request.read_type
            form.technical_info.read_length.data = form.seq_request.read_length
            form.technical_info.num_lanes.data = form.seq_request.num_lanes
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
            if form.seq_request.pi_contact:
                form.contact.pi_name.data = form.seq_request.pi_contact.name or ""
                form.contact.pi_email.data = form.seq_request.pi_contact.email or ""

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
                form.organization.address.data = (
                    form.seq_request.organization_contact.address or ""
                )

            # Billing
            if form.seq_request.billing_contact:
                form.billing.name.data = form.seq_request.billing_contact.name or ""
                form.billing.email.data = form.seq_request.billing_contact.email or ""
                form.billing.phone.data = form.seq_request.billing_contact.phone or ""
                form.billing.address.data = form.seq_request.billing_contact.address or ""
                form.billing.code.data = form.seq_request.billing_code or ""

            return form.make_response()
        return route

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def route(
            request: Request,
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            form: "SeqRequestForm" = Depends(SeqRequestForm.Validate(form_type="create"))
        ) -> Response:
            form.validate_rules(session, form.step_names)
            form.assert_valid()

            requestor = current_user
            if form.is_insider:
                user_id = form.user_selection.user_id.data
                email = form.user_selection.email.data
                first_name = form.user_selection.first_name.data
                last_name = form.user_selection.last_name.data

                if user_id:
                    requestor = session.get_one(Q.user.select(id=int(user_id)))
                elif email and first_name and last_name:
                    requestor = session.save(Q.user.create(
                        email=email,
                        first_name=first_name.strip(),
                        last_name=last_name.strip(),
                        hashed_password=bcrypt.generate_password_hash(secrets.url_safe_token()),
                        role=C.UserRole.DEACTIVATED,
                    ), flush=True)

            contact_person = Q.contact.create(
                form.contact.name.data,
                form.contact.email.data,
                form.contact.phone.data,
            )
            pi_contact = None
            if form.contact.pi_name.data and form.contact.pi_email.data:
                pi_contact = Q.contact.create(
                    form.contact.pi_name.data,
                    form.contact.pi_email.data,
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
                None,
                None,
                form.organization.address.data,
            )

            billing_contact = Q.contact.create(
                form.billing.name.data,
                form.billing.email.data,
                form.billing.phone.data,
                form.billing.address.data,
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
                    pi_contact=pi_contact,
                    bioinformatician_contact=bioinformatician,
                    organization_contact=organization,
                    billing_contact=billing_contact,
                    requestor=requestor,
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
            _ = Depends(dependencies.require_user),
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
                seq_request.status != C.SeqRequestStatus.DRAFT
                and access_level < C.AccessLevel.INSIDER
            ):
                raise exc.NoPermissionsException(
                    "Submitted requests can only be edited by insiders."
                )

            form.validate_rules(session, form.step_names)
            form.assert_valid()

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
            if form.contact.pi_name.data and form.contact.pi_email.data:
                if seq_request.pi_contact is None:
                    seq_request.pi_contact = Q.contact.create(
                        form.contact.pi_name.data,
                        form.contact.pi_email.data,
                    )
                else:
                    seq_request.pi_contact.name = form.contact.pi_name.data
                    seq_request.pi_contact.email = form.contact.pi_email.data
            else:
                seq_request.pi_contact = None
            seq_request.billing_contact.name = form.billing.name.data
            seq_request.billing_contact.email = form.billing.email.data
            seq_request.billing_contact.phone = form.billing.phone.data
            seq_request.billing_contact.address = form.billing.address.data

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
            seq_request.organization_contact.email = None
            seq_request.organization_contact.phone = None
            seq_request.organization_contact.address = (
                form.organization.address.data
            )

            session.save(seq_request)

            return responses.htmx_response(
                redirect=request.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route
