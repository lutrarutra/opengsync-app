from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, config
from ...components import inputs
from ..HTMXForm import HTMXForm


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
        request: Request,
        form_type: Literal["create", "edit"],
        lab_prep: models.LabPrep | None = None,
    ) -> None:
        super().__init__(request)
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

    async def prepare(self) -> None:
        if self.lab_prep is not None:
            self.checklist_type.data = self.lab_prep.checklist_type_id
            self.name.data = self.lab_prep.name
            self.service_type.data = self.lab_prep.service_type_id

    async def _validate_types(self) -> tuple[C.LabChecklistType, C.ServiceType]:
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

    @staticmethod
    async def create(
        request: Request,
        current_user: models.User = Depends(dependencies.require_insider),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        form = LabPrepForm(request, form_type="create")
        await form.validate()

        checklist_type, service_type = await form._validate_types()

        if not checklist_type.identifier:
            raise ValueError("Checklist type must have an identifier.")

        latest_prep = await session.first(
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

        lab_prep = await session.save(
            Q.lab_prep.create(
                name=form.name.data.strip(),
                checklist_type=checklist_type,
                service_type=service_type,
                number=prep_number,
                creator=current_user,
            ),
            flush=True,
        )

        return await responses.htmx_response(
            redirect=request.url_for("lab_prep", lab_prep_id=lab_prep.id),
            flash=responses.flash("Prep created!", "success"),
        )

    @staticmethod
    async def edit(
        request: Request,
        lab_prep_id: int,
        current_user: models.User = Depends(dependencies.require_insider),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        lab_prep = await session.get_one(Q.lab_prep.select(id=lab_prep_id))

        form = LabPrepForm(request, form_type="edit", lab_prep=lab_prep)
        await form.validate()

        checklist_type, service_type = await form._validate_types()

        if not form.name.data:
            form.name.errors.append("Name is required")
            raise exc.FormValidationException(form)

        if checklist_type != lab_prep.checklist_type:
            form.checklist_type.errors.append("Cannot change checklist type")
            raise exc.FormValidationException(form)

        lab_prep.name = form.name.data.strip()
        lab_prep.service_type = service_type

        return await responses.htmx_response(
            redirect=request.url_for("lab_prep", lab_prep_id=lab_prep.id),
            flash=responses.flash("Changes saved!", "success"),
        )