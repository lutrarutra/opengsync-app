from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response
from loguru import logger

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, config
from ...components import inputs
from ..HTMXForm import HTMXForm

class LabPrepForm(HTMXForm):
    """Lab prep form handler — validation, rendering, and response logic."""

    template_path = "forms/lab_prep.html"

    name = inputs.string.StringInputField("Name", max_length=models.LabPrep.name.type.length, required=False)
    service_type = inputs.selectable.SelectableInputField("Service", C.AccessType.as_selectable())
    checklist_type = inputs.selectable.SelectableInputField("Checklist", C.LabChecklistType.as_selectable())
    

    @staticmethod
    async def create_lab_prep(
        request: Request,
        method: Literal["create", "edit"],
        current_user: models.User = Depends(dependencies.require_insider),
        lab_prep: models.LabPrep | None = None,
        session: AsyncSession = Depends(dependencies.db_session), 
    ) -> Response:
        form = LabPrepForm(request)
        await form.validate()
        try:
            checklist_type = C.LabChecklistType.get(form.checklist_type.data)
        except ValueError:
            form.checklist_type.errors.append("Invalid protocol")
            raise exc.FormValidationException(form)
        
        try:
            service_type = C.ServiceType.get(form.service_type.data)
        except ValueError:
            form.service_type.errors.append("Invalid assay type")
            raise exc.FormValidationException(form)

        if method == "edit":
            if lab_prep is None:
                logger.error("lab_prep must be provided if form_type is 'edit'.")
                raise ValueError("lab_prep must be provided if form_type is 'edit'.")
            
            if not form.name.data:
                form.name.errors.append("Name is required",)
                raise exc.FormValidationException(form)
            if checklist_type != lab_prep.checklist_type:
                form.checklist_type.errors.append("Cannot change checklist type")
                raise exc.FormValidationException(form)
            
        if not checklist_type.identifier:
            raise ValueError("Checklist type must have an identifier.")
        
        if (latest_prep := await session.first(
            Q.lab_prep.select(
                checklist_type=checklist_type
            ).order_by(models.LabPrep.prep_number.desc())
        )) is not None:
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
                creator=current_user
            ), flush=True
        )

        return await responses.htmx_response(redirect="lab_prep_page", lab_prep_id=lab_prep.id)
            
