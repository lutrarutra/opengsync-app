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


class FeatureKitForm(HTMXForm):
    template_path = "forms/feature_kit.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.FeatureKit.name.type.length,
        required=True,
    )
    identifier = inputs.string.StringInputField(
        "Identifier",
        max_length=models.FeatureKit.identifier.type.length,
        required=True,
    )
    feature_type_id = inputs.selectable.SelectableInputField(
        "Feature Type",
        C.FeatureType.as_selectable(),
        required=False,
    )

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        feature_kit: models.FeatureKit | None,
    ) -> None:
        super().__init__()
        self.form_type = form_type
        self.feature_kit = feature_kit

        if form_type == "edit":
            if feature_kit is None:
                raise ValueError("Feature kit must be provided for edit form.")
            self.post_url = responses.url_for("FeatureKitForm.Edit", feature_kit_id=feature_kit.id)
        elif form_type == "create":
            if feature_kit is not None:
                raise ValueError("Feature kit must not be provided for create form.")
            self.post_url = responses.url_for("FeatureKitForm.Create")
        else:
            raise ValueError("form_type must be either 'create' or 'edit'.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            feature_kit_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "FeatureKitForm":
            if form_type == "edit" and feature_kit_id is None:
                raise exc.OpeNGSyncServerException("Feature kit ID must be provided for edit form.")

            feature_kit = None
            if feature_kit_id is not None:
                feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))
            return FeatureKitForm(form_type=form_type, feature_kit=feature_kit)

        return dependency

    @htmx_route("GET", "/{feature_kit_id}/edit-feature-kit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "FeatureKitForm" = Depends(FeatureKitForm.Init(form_type="edit")),
        ):
            if form.feature_kit is None:
                raise exc.OpeNGSyncServerException("Feature kit ID must be provided for edit form.")

            form.name.data = form.feature_kit.name
            form.identifier.data = form.feature_kit.identifier
            form.feature_type_id.data = form.feature_kit.type_id
            return form.make_response()

        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "FeatureKitForm" = Depends(FeatureKitForm.Init(form_type="create")),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()

        return route

    @htmx_route("POST", "/{feature_kit_id}/edit-feature-kit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "FeatureKitForm" = Depends(FeatureKitForm.Validate(form_type="edit")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.feature_kit is None:
                raise exc.OpeNGSyncServerException("Feature kit ID must be provided for edit form.")

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
                Q.feature_kit.select(identifier=form.identifier.data).where(models.FeatureKit.id != form.feature_kit.id)
            ):
                form.identifier.errors.append("A feature kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(
                Q.feature_kit.select(name=form.name.data).where(models.FeatureKit.id != form.feature_kit.id)
            ):
                form.name.errors.append("A feature kit with this name already exists.")
                raise exc.FormValidationException(form)

            if form.feature_kit.type != C.FeatureType.get(form.feature_type_id.data):
                form.feature_type_id.errors.append("Feature type cannot be changed.")
                raise exc.FormValidationException(form)

            form.feature_kit.name = form.name.data
            form.feature_kit.identifier = form.identifier.data

            return responses.htmx_response(
                redirect=responses.url_for("feature_kit_page", feature_kit_id=form.feature_kit.id),
                flash=responses.flash("Feature kit updated successfully.", "success"),
            )

        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "FeatureKitForm" = Depends(FeatureKitForm.Validate(form_type="create")),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            form.identifier.data = form.identifier.data.strip()
            if form.identifier.data.startswith("#"):
                form.identifier.errors.append("Identifier cannot start with '#'.")
                raise exc.FormValidationException(form)

            for ws in string.whitespace:
                if ws in form.identifier.data:
                    form.identifier.errors.append("Identifier cannot contain whitespace.")
                    raise exc.FormValidationException(form)

            if session.exists(Q.feature_kit.select(identifier=form.identifier.data)):
                form.identifier.errors.append("A feature kit with this identifier already exists.")
                raise exc.FormValidationException(form)

            if session.exists(Q.feature_kit.select(name=form.name.data)):
                form.name.errors.append("A feature kit with this name already exists.")
                raise exc.FormValidationException(form)

            feature_kit = session.save(
                Q.feature_kit.create(
                    name=form.name.data,
                    identifier=form.identifier.data,
                    type=C.FeatureType.get(form.feature_type_id.data)
                    if form.feature_type_id.data is not None
                    else C.FeatureType.CUSTOM,
                ),
                flush=True,
            )

            return responses.htmx_response(
                redirect=responses.url_for("feature_kit_page", feature_kit_id=feature_kit.id),
                flash=responses.flash("Feature kit created successfully.", "success"),
            )

        return submit
