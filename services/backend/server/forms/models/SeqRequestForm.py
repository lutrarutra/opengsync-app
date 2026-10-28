from typing import Literal

from fastapi import Cookie, Depends, Request
from fastapi.responses import Response

from opengsync_db import SyncSession, models, queries as Q, categories as C
from opengsync_db.transitions import run_operation, create as create_ops, manual as manual_ops

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


class SubmissionSubForm(SubHTMXForm):
    """What is submitted, which decides the workflow of the request."""
    title = "Submission Type"
    icon = "bi-diagram-3"

    # Un-pooled libraries are not offered (yet); add them here to enable that submission type.
    TYPES = C.SubmissionType.as_list(include_unpooled_libraries=False)

    # Stages of each submission type's workflow, shown when it is selected: (icon, label, done by the customer).
    WORKFLOWS: dict[C.SubmissionType, list[tuple[str, str, bool]]] = {
        C.SubmissionType.RAW_SAMPLES: [
            ("bi-droplet", "Your Samples", True),
            ("bi-eyedropper", "Library Prep", False),
            ("bi-collection", "Pooling", False),
            ("bi-cpu", "Sequencing", False),
            ("bi-cloud-download", "Data Delivery", False),
        ],
        C.SubmissionType.POOLED_LIBRARIES: [
            ("bi-collection", "Your Pooled Libraries", True),
            ("bi-cpu", "Sequencing", False),
            ("bi-cloud-download", "Data Delivery", False),
        ],
        C.SubmissionType.UNPOOLED_LIBRARIES: [
            ("bi-eyedropper", "Your Libraries", True),
            ("bi-collection", "Pooling", False),
            ("bi-cpu", "Sequencing", False),
            ("bi-cloud-download", "Data Delivery", False),
        ],
        C.SubmissionType.QC_ONLY: [
            ("bi-droplet", "Your Samples or Libraries", True),
            ("bi-clipboard-check", "Quality Control", False),
            ("bi-file-earmark-text", "QC Report", False),
        ],
    }

    ICONS: dict[C.SubmissionType, str] = {
        C.SubmissionType.RAW_SAMPLES: "bi-droplet",
        C.SubmissionType.POOLED_LIBRARIES: "bi-collection",
        C.SubmissionType.UNPOOLED_LIBRARIES: "bi-eyedropper",
        C.SubmissionType.QC_ONLY: "bi-clipboard-check",
    }

    submission_type = inputs.selectable.SelectableInputField("Submission Type", options=[(t.id, t.label) for t in TYPES])


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
    submission = SubmissionSubForm()
    basic_info = BasicInfoSubForm()
    user_selection = UserSelectionSubForm()
    technical_info = TechnicalInfoSubForm()
    contact = ContactSubForm()
    bioinformatician = BioinformaticianSubForm()
    organization = OrganizationSubForm()
    billing = BillingSubForm()

    # Order of the steps in the multi-step form.
    STEPS = ("disclaimer", "submission", "user_selection", "basic_info", "contact", "technical_info", "bioinformatician", "organization", "billing")

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
        self.submitted_step: str | None = None  # step whose Next was pressed, if any

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
        # Requestor selection only exists to create a request on behalf of a customer.
        return [
            name for name in self.STEPS
            if name != "user_selection" or (self.is_insider and self.form_type == "create")
        ]

    @property
    def steps(self) -> list[tuple[str, SubHTMXForm]]:
        return [(name, self.sub_form_dict[name]) for name in self.step_names]

    @property
    def active_step(self) -> str:
        """Step the form opens at.

        After Next: the first step up to the submitted one with errors, else the step after it
        (later steps of an edit form are validated too, but only flagged in the timeline).
        Otherwise: the first step with errors, else the first step not validated yet; an edit
        form, whose steps are all pre-filled, opens at the first step after the disclaimer.
        """
        if self.submitted_step is not None:
            index = self.step_names.index(self.submitted_step)
            for name in self.step_names[: index + 1]:
                if self.sub_form_dict[name].has_errors:
                    return name
            return self.step_names[min(index + 1, len(self.step_names) - 1)]

        for name, sub_form in self.steps:
            if sub_form.has_errors:
                return name
        for name, sub_form in self.steps:
            if not sub_form.validated:
                return name
        if self.form_type == "edit":
            return self.step_names[1]
        return self.step_names[-1]

    def lock_submission_type(self, access_level: C.AccessLevel) -> None:
        """The submission type of an existing request decides its workflow; only admins may change it."""
        self.submission.submission_type.read_only = access_level < C.AccessLevel.ADMIN

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

    def prefill_pi_from_requestor(self, session: SyncSession) -> None:
        """Fill the empty PI of the contact step with the PI of the selected requestor, if a customer who has one.

        Before the contact step is completed (all steps are re-rendered from the submitted data). Typed values are
        kept; a new requestor has no PI yet.
        """
        if self.user_selection.has_errors or not (user_id := self.user_selection.user_id.data):
            return
        pi_name, pi_email = self.contact.pi_name.name, self.contact.pi_email.name
        if (self.raw_data.get(pi_name) or "").strip() or (self.raw_data.get(pi_email) or "").strip():
            return
        requestor = session.first(Q.user.select(id=int(user_id)))
        if requestor is None or requestor.is_insider or not (requestor.pi_name and requestor.pi_email):
            return
        self.raw_data = {**self.raw_data, pi_name: requestor.pi_name, pi_email: requestor.pi_email}

    def selected_group(self, session: SyncSession, requestor: models.User) -> models.Group | None:
        """Group selected in the form; a non-insider requestor must be affiliated with it."""
        if not self.basic_info.group_id.data:
            return None
        group = session.get_one(Q.group.select(id=self.basic_info.group_id.data))
        if not requestor.is_insider and session.first(
            Q.affiliation.select(user_id=requestor.id, group_id=group.id)
        ) is None:
            self.basic_info.group_id.errors.append("Requestor must be part of the selected group.")
            raise exc.FormValidationException(self)
        return group

    def validate_step(self, formdata: dict, csrf_token: str | None, session: SyncSession) -> Response:
        """Validate every step up to the submitted one and re-render the form at the next step.

        On errors, the form is re-rendered at the first step with errors instead. An edit form
        validates all steps, since they are all pre-filled, so the timeline shows their state.
        """
        step = formdata.get("step")
        if step not in self.step_names:
            raise exc.BadRequestException(f"Unknown step '{step}'.")

        self.submitted_step = step
        completed = self.step_names[: self.step_names.index(step) + 1]
        checked = self.step_names if self.form_type == "edit" else completed
        self.validate_sub_forms(formdata, checked, csrf_token=csrf_token)
        self.validate_rules(session, checked)
        if self.form_type == "create" and "user_selection" in completed and "contact" not in completed:
            self.prefill_pi_from_requestor(session)
        # Errors in later steps of an edit form are only flagged; they don't block Next.
        if any(self.sub_form_dict[name].has_errors for name in completed):
            raise exc.FormValidationException(self)
        return self.make_response()

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            seq_request_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> "SeqRequestForm":
            if form_type == "edit" and seq_request_id is None:
                raise exc.BadRequestException("SeqRequest ID must be provided for edit form.")

            seq_request = None
            if form_type != "create" and seq_request_id is not None:  # a create form ignores a stray id
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
            form.lock_submission_type(access_level)
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
            # A customer's own PI by default; an insider's requestor's PI is filled once selected (validate_step)
            if not current_user.is_insider and current_user.pi_name and current_user.pi_email:
                form.contact.pi_name.data = current_user.pi_name
                form.contact.pi_email.data = current_user.pi_email
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
                raise exc.BadRequestException("SeqRequest ID must be provided for edit form.")
            form.lock_submission_type(access_level)

            # Every step is pre-filled from the request, so the timeline starts out all valid.
            for _, sub_form in form.steps:
                sub_form.validated = True
            form.disclaimer.accepted.data = True

            form.submission.submission_type.data = form.seq_request.submission_type.id

            form.basic_info.name.data = form.seq_request.name or ""
            form.basic_info.description.data = form.seq_request.description or ""
            form.basic_info.group_id.data = form.seq_request.group_id

            # Technical info
            form.technical_info.read_type.data = form.seq_request.read_type
            form.technical_info.read_length.data = form.seq_request.read_length
            form.technical_info.num_lanes.data = form.seq_request.num_lanes
            form.technical_info.data_delivery_mode.data = form.seq_request.data_delivery_mode
            form.technical_info.special_requirements.data = (
                form.seq_request.special_requirements or ""
            )

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

            group = form.selected_group(session, requestor)

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

            with run_operation(session, create_ops.REQUEST_CREATE):
                seq_request = session.save(
                    Q.seq_request.create(
                        name=form.basic_info.name.data,
                        description=form.basic_info.description.data,
                        read_type=C.ReadType.get(form.technical_info.read_type.data),
                        read_length=int(form.technical_info.read_length.data) if form.technical_info.read_length.data else None,
                        num_lanes=int(form.technical_info.num_lanes.data) if form.technical_info.num_lanes.data else None,
                        data_delivery_mode=C.DataDeliveryMode.get(form.technical_info.data_delivery_mode.data),
                        special_requirements=form.technical_info.special_requirements.data,
                        submission_type=C.SubmissionType.get(form.submission.submission_type.data),
                        billing_code=form.billing.code.data or None,
                        contact_person=contact_person,
                        pi_contact=pi_contact,
                        bioinformatician_contact=bioinformatician,
                        organization_contact=organization,
                        billing_contact=billing_contact,
                        requestor=requestor,
                        group=group,
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

            form.lock_submission_type(access_level)
            if form.submission.submission_type.read_only and form.submission.submission_type.data != seq_request.submission_type.id:
                form.submission.submission_type.errors.append("Only admins can change the submission type.")
                raise exc.FormValidationException(form)

            form.validate_rules(session, form.step_names)
            form.assert_valid()

            # Update basic info
            seq_request.name = form.basic_info.name.data
            seq_request.description = form.basic_info.description.data
            seq_request.group = form.selected_group(session, seq_request.requestor)

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
            seq_request.submission_type = C.SubmissionType.get(form.submission.submission_type.data)
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
