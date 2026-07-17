from typing import Literal

from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class GroupForm(HTMXForm):
    template_path = "forms/group.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.Group.name.type.length,
        min_length=6,
    )
    group_type = inputs.selectable.SelectableInputField("Type", C.GroupType.as_selectable())

    def __init__(self, form_type: Literal["create", "edit"], group: models.Group | None) -> None:
        super().__init__()
        self.form_type = form_type
        self.group = group
        if form_type == "create":
            if group is not None:
                raise ValueError("Group must not be provided for create form.")
            self.post_url = responses.url_for("GroupForm.Create")
        elif form_type == "edit":
            if group is None:
                raise ValueError("Group must be provided for edit form.")
            self.post_url = responses.url_for("GroupForm.Edit", group_id=group.id)

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            group_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "GroupForm":
            if form_type == "edit" and group_id is None:
                raise exc.OpeNGSyncServerException("Group ID must be provided for edit form.")

            group = None
            if group_id is not None:
                group = session.get_one(Q.group.select(id=group_id))
            return GroupForm(form_type=form_type, group=group)

        return dependency

    @htmx_route("GET", "/{group_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "GroupForm" = Depends(GroupForm.Init(form_type="edit"))
        ):
            if form.group is None:
                raise exc.OpeNGSyncServerException("Group ID must be provided for edit form.")

            form.name.data = form.group.name
            form.group_type.data = form.group.type_id
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "GroupForm" = Depends(GroupForm.Init(form_type="create"))
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{group_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            access_level: C.AccessLevel = Depends(dependencies.group_permissions),
            session: SyncSession = Depends(dependencies.db_session),
            form: "GroupForm" = Depends(GroupForm.Validate(form_type="edit")),
        ) -> Response:
            if form.group is None:
                raise exc.OpeNGSyncServerException("Group ID must be provided for edit form.")

            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this group.")

            if session.exists(
                Q.group.select(name=form.name.data).where(
                    models.Group.id != form.group.id
                )
            ):
                form.name.errors.append("A group with this name already exists.")
                raise exc.FormValidationException(form)

            form.group.name = form.name.data
            form.group.type_id = form.group_type.data

            return responses.htmx_response(
                redirect=responses.url_for("group_page", group_id=form.group.id),
                flash=responses.flash("Group Updated!", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            form: "GroupForm" = Depends(GroupForm.Validate(form_type="create")),
        ) -> Response:
            if session.exists(Q.group.select(name=form.name.data)):
                form.name.errors.append("A group with this name already exists.")
                raise exc.FormValidationException(form)

            group = Q.group.create(
                name=form.name.data,
                type=C.GroupType.get(form.group_type.data),
            )
            group.user_links.append(Q.affiliation.create(
                user=current_user, group=group, type=C.AffiliationType.OWNER
            ))
            session.save(group, flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("group_page", group_id=group.id),
                flash=responses.flash("Group Created!", "success"),
            )
        return submit