from typing import Literal

from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class ProtocolForm(HTMXForm):
    template_path = "forms/protocol.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.Protocol.name.type.length,
        min_length=6,
    )
    service_type = inputs.selectable.SelectableInputField(
        "Service Type",
        C.ServiceType.as_selectable(),
    )
    read_structure = inputs.string.StringInputField(
        "Read Structure",
        max_length=models.Protocol.read_structure.type.length,
        required=False,
        description="Read structure defining the layout of reads, UMIs and indexes.",
    )

    def __init__(self, form_type: Literal["create", "edit"], protocol: models.Protocol | None) -> None:
        super().__init__()
        self.form_type = form_type
        self.protocol = protocol
        if protocol is None and form_type == "edit":
            raise ValueError("Protocol must be provided for edit form.")
        elif protocol is not None and form_type == "create":
            raise ValueError("Protocol must not be provided for create form.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            protocol_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "ProtocolForm":
            if form_type == "edit" and protocol_id is None:
                raise exc.OpeNGSyncServerException("Protocol ID must be provided for edit form.")

            protocol = None
            if protocol_id is not None:
                protocol = session.get_one(Q.protocol.select(id=protocol_id))
            return ProtocolForm(form_type=form_type, protocol=protocol)

        return dependency

    @htmx_route("GET", "/{protocol_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "ProtocolForm" = Depends(ProtocolForm.Init(form_type="edit"))
        ):
            if form.protocol is None:
                raise exc.OpeNGSyncServerException("Protocol ID must be provided for edit form.")

            form.name.data = form.protocol.name
            form.service_type.data = form.protocol.service_type.id
            form.read_structure.data = form.protocol.read_structure
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "ProtocolForm" = Depends(ProtocolForm.Init(form_type="create"))
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{protocol_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "ProtocolForm" = Depends(ProtocolForm.Validate(form_type="edit")),
        ) -> Response:
            if form.protocol is None:
                raise exc.OpeNGSyncServerException("Protocol ID must be provided for edit form.")

            if session.exists(
                Q.protocol.select(name=form.name.data).where(models.Protocol.id != form.protocol.id)
            ):
                form.name.errors.append("A protocol with this name already exists.")
                raise exc.FormValidationException(form)

            form.protocol.name = form.name.data.strip()
            form.protocol.service_type = C.ServiceType.get(form.service_type.data)
            form.protocol.read_structure = form.read_structure.data.strip() if form.read_structure.data else None

            session.save(form.protocol)

            return responses.htmx_response(
                redirect=responses.url_for("protocol_page", protocol_id=form.protocol.id),
                flash=responses.flash("Protocol Updated!", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "ProtocolForm" = Depends(ProtocolForm.Validate(form_type="create")),
        ) -> Response:
            if session.exists(Q.protocol.select(name=form.name.data)):
                form.name.errors.append("A protocol with this name already exists.")
                raise exc.FormValidationException(form)

            protocol = session.save(Q.protocol.create(
                name=form.name.data.strip(),
                service_type=C.ServiceType.get(form.service_type.data),
                read_structure=form.read_structure.data.strip() if form.read_structure.data else None,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("protocol_page", protocol_id=protocol.id),
                flash=responses.flash("Protocol Created!", "success"),
            )
        return submit