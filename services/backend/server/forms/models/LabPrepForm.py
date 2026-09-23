from typing import Literal
from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, config
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class LabPrepForm(HTMXForm):
    template_path = "forms/lab_prep.html"

    checklist_type = inputs.selectable.SelectableInputField(
        "Checklist", options=C.LabChecklistType.as_selectable()
    )
    service_type = inputs.selectable.SelectableInputField(
        "Service", options=C.ServiceType.as_selectable()
    )
    name = inputs.string.StringInputField(
        "Name", max_length=models.LabPrep.name.type.length, required=False
    )

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        lab_prep: models.LabPrep | None = None,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.lab_prep = lab_prep

        if form_type == "create" and lab_prep is not None:
            raise ValueError("lab_prep must be None when form_type is 'create'.")
        if form_type == "edit" and lab_prep is None:
            raise ValueError("lab_prep must be provided when form_type is 'edit'.")

        self._context["lab_prep"] = lab_prep
        self._context["identifiers"] = {
            ct.id: ct.identifier for ct in C.LabChecklistType.as_list()
        }

    def prepare(self) -> None:
        if self.lab_prep is not None:
            self.checklist_type.data = self.lab_prep.checklist_type.id
            self.name.data = self.lab_prep.name
            self.service_type.data = self.lab_prep.service_type.id

    def _validate_types(self) -> tuple[C.LabChecklistType, C.ServiceType]:
        try:
            checklist_type = C.LabChecklistType.get(self.checklist_type.data)
        except ValueError:
            self.checklist_type.errors.append("Invalid protocol")
            raise exc.FormValidationException(self)

        try:
            service_type = C.ServiceType.get(self.service_type.data)
        except ValueError:
            self.service_type.errors.append("Invalid assay type")
            raise exc.FormValidationException(self)

        return checklist_type, service_type

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            lab_prep_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "LabPrepForm":
            lab_prep = None
            if lab_prep_id is not None:
                lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))
            return LabPrepForm(form_type=form_type, lab_prep=lab_prep)
        return dependency

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_insider),
            form: "LabPrepForm" = Depends(LabPrepForm.Init(form_type="create")),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            current_user: models.User = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            form: "LabPrepForm" = Depends(LabPrepForm.Validate(form_type="create")),
        ) -> Response:
            checklist_type, service_type = form._validate_types()

            if not checklist_type.identifier:
                raise ValueError("Checklist type must have an identifier.")

            latest_prep = session.first(
                Q.lab_prep.select(
                    checklist_type=checklist_type
                ).order_by(models.LabPrep.prep_number.desc())
            )
            if latest_prep is not None:
                prep_number = latest_prep.prep_number + 1
            else:
                prep_number = config.settings.app_config.db.lab_protocol_start_number

            if not form.name.data:
                form.name.data = f"{checklist_type.identifier}{prep_number:04d}"

            lab_prep = session.save(
                Q.lab_prep.create(
                    name=form.name.data.strip(),
                    checklist_type=checklist_type,
                    service_type=service_type,
                    number=prep_number,
                    creator=current_user,
                ),
                flush=True,
            )

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=lab_prep.id),
                flash=responses.flash("Prep created!", "success"),
            )
        return submit

    @htmx_route("GET", "/{lab_prep_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            _ = Depends(dependencies.require_insider),
            form: "LabPrepForm" = Depends(LabPrepForm.Init(form_type="edit")),
        ):
            if form.lab_prep is None:
                raise exc.OpeNGSyncServerException("Lab prep must be provided for edit form.")
            return form.make_response()
        return route

    @htmx_route("POST", "/{lab_prep_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            _ = Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
            form: "LabPrepForm" = Depends(LabPrepForm.Validate(form_type="edit")),
        ) -> Response:
            if form.lab_prep is None:
                raise exc.OpeNGSyncServerException("Lab prep must be provided for edit form.")

            checklist_type, service_type = form._validate_types()

            if not form.name.data:
                form.name.errors.append("Name is required")
                raise exc.FormValidationException(form)

            if checklist_type != form.lab_prep.checklist_type:
                form.checklist_type.errors.append("Cannot change checklist type")
                raise exc.FormValidationException(form)

            form.lab_prep.name = form.name.data.strip()
            form.lab_prep.service_type = service_type

            session.save(form.lab_prep)

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep.id),
                flash=responses.flash("Changes saved!", "success"),
            )
        return submit