import string
from typing import Literal

from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class KitForm(HTMXForm):
    template_path = "forms/kit.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.Kit.name.type.length,
        required=True,
    )
    identifier = inputs.string.StringInputField(
        "Identifier",
        max_length=models.Kit.identifier.type.length,
        required=True,
    )

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        kit: models.Kit | None,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.kit = kit

        if form_type == "edit":
            if kit is None:
                raise ValueError("Kit must be provided for edit form.")
            self.post_url = responses.url_for("KitForm.Edit", kit_id=kit.id)
        elif form_type == "create":
            if kit is not None:
                raise ValueError("Kit must not be provided for create form.")
            self.post_url = responses.url_for("KitForm.Create")
        else:
            raise ValueError("form_type must be either 'create' or 'edit'.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            kit_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "KitForm":
            if form_type == "edit" and kit_id is None:
                raise exc.OpeNGSyncServerException("Kit ID must be provided for edit form.")

            kit = None
            if kit_id is not None:
                kit = session.get_one(Q.kit.select(id=kit_id))
            return KitForm(form_type=form_type, kit=kit)

        return dependency

    @htmx_route("GET", "/{kit_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "KitForm" = Depends(KitForm.Init(form_type="edit")),
        ):
            if form.kit is None:
                raise exc.OpeNGSyncServerException("Kit ID must be provided for edit form.")

            form.name.data = form.kit.name
            form.identifier.data = form.kit.identifier
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "KitForm" = Depends(KitForm.Init(form_type="create")),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{kit_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "KitForm" = Depends(KitForm.Validate(form_type="edit")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.kit is None:
                raise exc.OpeNGSyncServerException("Kit ID must be provided for edit form.")

            # Validate identifier
            form.identifier.data = form.identifier.data.strip()
            if form.identifier.data.startswith("#"):
                form.identifier.errors.append("Identifier cannot start with '#'.")
                raise exc.FormValidationException(form)

            if "," in form.identifier.data:
                form.identifier.errors.append("Identifier cannot contain ',' (commas).")
                raise exc.FormValidationException(form)

            for ws in string.whitespace:
                if ws in form.identifier.data:
                    form.identifier.errors.append("Identifier cannot contain whitespace.")
                    raise exc.FormValidationException(form)

            if session.exists(
                Q.kit.select(identifier=form.identifier.data).where(
                    models.Kit.id != form.kit.id
                )
            ):
                form.identifier.errors.append("A kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(
                Q.kit.select(name=form.name.data).where(
                    models.Kit.id != form.kit.id
                )
            ):
                form.name.errors.append("A kit with this name already exists.")
                raise exc.FormValidationException(form)

            form.kit.name = form.name.data
            form.kit.identifier = form.identifier.data

            return responses.htmx_response(
                redirect=responses.url_for("kit_page", kit_id=form.kit.id),
                flash=responses.flash("Kit updated successfully.", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "KitForm" = Depends(KitForm.Validate(form_type="create")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            # Validate identifier
            form.identifier.data = form.identifier.data.strip()
            if form.identifier.data.startswith("#"):
                form.identifier.errors.append("Identifier cannot start with '#'.")
                raise exc.FormValidationException(form)

            if "," in form.identifier.data:
                form.identifier.errors.append("Identifier cannot contain ',' (commas).")
                raise exc.FormValidationException(form)

            for ws in string.whitespace:
                if ws in form.identifier.data:
                    form.identifier.errors.append("Identifier cannot contain whitespace.")
                    raise exc.FormValidationException(form)

            if session.exists(Q.kit.select(identifier=form.identifier.data)):
                form.identifier.errors.append("A kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(Q.kit.select(name=form.name.data)):
                form.name.errors.append("A kit with this name already exists.")
                raise exc.FormValidationException(form)

            kit = session.save(Q.kit.create(
                name=form.name.data,
                identifier=form.identifier.data,
                kit_type=C.KitType.LIBRARY_KIT,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("kit_page", kit_id=kit.id),
                flash=responses.flash("Kit created successfully.", "success"),
            )
        return submit