import string
from typing import Literal

from fastapi import Depends, Response
from opengsync_db import SyncSession, models
from opengsync_db import categories as C
from opengsync_db import queries as Q

from ...components import inputs
from ...core import dependencies, responses
from ...core import exceptions as exc
from ..HTMXForm import FormFunc, HTMXForm, RouteFunc, htmx_route


class IndexKitForm(HTMXForm):
    template_path = "forms/index_kit.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.IndexKit.name.type.length,
        required=True,
    )
    identifier = inputs.string.StringInputField(
        "Identifier",
        max_length=models.IndexKit.identifier.type.length,
        required=True,
    )
    index_type_id = inputs.selectable.SelectableInputField(
        "Index Type",
        C.IndexType.as_selectable(),
        required=False,
    )

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        index_kit: models.IndexKit | None,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.index_kit = index_kit

        if form_type == "edit":
            if index_kit is None:
                raise ValueError("Index kit must be provided for edit form.")
            self.post_url = responses.url_for("IndexKitForm.Edit", index_kit_id=index_kit.id)
        elif form_type == "create":
            if index_kit is not None:
                raise ValueError("Index kit must not be provided for create form.")
            self.post_url = responses.url_for("IndexKitForm.Create")
        else:
            raise ValueError("form_type must be either 'create' or 'edit'.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            index_kit_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "IndexKitForm":
            if form_type == "edit" and index_kit_id is None:
                raise exc.OpeNGSyncServerException("Index kit ID must be provided for edit form.")

            index_kit = None
            if index_kit_id is not None:
                index_kit = session.get_one(Q.index_kit.select(id=index_kit_id))
            return IndexKitForm(form_type=form_type, index_kit=index_kit)

        return dependency

    @htmx_route("GET", "/{index_kit_id}/edit-index-kit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "IndexKitForm" = Depends(IndexKitForm.Init(form_type="edit")),
        ):
            if form.index_kit is None:
                raise exc.OpeNGSyncServerException("Index kit ID must be provided for edit form.")

            form.name.data = form.index_kit.name
            form.identifier.data = form.index_kit.identifier
            form.index_type_id.data = form.index_kit.type_id
            return form.make_response()

        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "IndexKitForm" = Depends(IndexKitForm.Init(form_type="create")),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()

        return route

    @htmx_route("POST", "/{index_kit_id}/edit-index-kit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "IndexKitForm" = Depends(IndexKitForm.Validate(form_type="edit")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.index_kit is None:
                raise exc.OpeNGSyncServerException("Index kit ID must be provided for edit form.")

            # Validate identifier
            form.identifier.data = form.identifier.data.strip()
            if form.identifier.data.startswith("#"):
                form.identifier.errors.append("Identifier cannot start with '#'.")
                raise exc.FormValidationException(form)

            for ws in string.whitespace:
                if ws in form.identifier.data:
                    form.identifier.errors.append("Identifier cannot contain whitespace.")
                    raise exc.FormValidationException(form)

            if session.exists(
                Q.index_kit.select(identifier=form.identifier.data).where(models.IndexKit.id != form.index_kit.id)
            ):
                form.identifier.errors.append("An index kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(Q.index_kit.select(name=form.name.data).where(models.IndexKit.id != form.index_kit.id)):
                form.name.errors.append("An index kit with this name already exists.")
                raise exc.FormValidationException(form)

            form.index_kit.name = form.name.data
            form.index_kit.identifier = form.identifier.data

            return responses.htmx_response(
                redirect=responses.url_for("index_kit_page", index_kit_id=form.index_kit.id),
                flash=responses.flash("Index kit updated successfully.", "success"),
            )

        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "IndexKitForm" = Depends(IndexKitForm.Validate(form_type="create")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            # Validate identifier
            form.identifier.data = form.identifier.data.strip()
            if form.identifier.data.startswith("#"):
                form.identifier.errors.append("Identifier cannot start with '#'.")
                raise exc.FormValidationException(form)

            for ws in string.whitespace:
                if ws in form.identifier.data:
                    form.identifier.errors.append("Identifier cannot contain whitespace.")
                    raise exc.FormValidationException(form)

            if session.exists(Q.index_kit.select(identifier=form.identifier.data)):
                form.identifier.errors.append("An index kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(Q.index_kit.select(name=form.name.data)):
                form.name.errors.append("An index kit with this name already exists.")
                raise exc.FormValidationException(form)

            index_kit = session.save(
                Q.index_kit.create(
                    name=form.name.data,
                    identifier=form.identifier.data,
                    type=C.IndexType.get(form.index_type_id.data)
                    if form.index_type_id.data is not None
                    else C.IndexType.DUAL_INDEX,
                    supported_protocol_ids=[],
                ),
                flush=True,
            )

            return responses.htmx_response(
                redirect=responses.url_for("index_kit_page", index_kit_id=index_kit.id),
                flash=responses.flash("Index kit created successfully.", "success"),
            )

        return submit
