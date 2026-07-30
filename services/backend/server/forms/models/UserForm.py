from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class UserForm(HTMXForm):
    template_path = "forms/user.html"

    first_name = inputs.string.StringInputField("First Name", max_length=models.User.first_name.type.length)
    last_name = inputs.string.StringInputField("Last Name", max_length=models.User.last_name.type.length)
    email = inputs.string.StringInputField("Email", max_length=models.User.email.type.length)
    role = inputs.selectable.SelectableInputField("Role", C.UserRole.as_selectable())

    def __init__(self, user: models.User) -> None:
        super().__init__()
        self.user = user
        self.post_url = responses.url_for("UserForm.Edit", user_id=user.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            user_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "UserForm":
            user = session.get_one(Q.user.select(id=user_id))
            return UserForm(user=user)
        return dependency

    @htmx_route("GET", "/{user_id}/edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "UserForm" = Depends(UserForm.Init()),
            access_level: C.AccessLevel = Depends(dependencies.user_permissions),
        ):
            if access_level < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to edit this user.")
            form.first_name.data = form.user.first_name
            form.last_name.data = form.user.last_name
            form.email.data = form.user.email
            form.role.data = form.user.role.id
            return form.make_response()
        return route

    @htmx_route("POST", "/{user_id}/edit")
    def Edit(cls) -> RouteFunc:
        def route(
            form: "UserForm" = Depends(UserForm.Validate()),
            access_level: C.AccessLevel = Depends(dependencies.user_permissions),
        ) -> Response:
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this user.")

            if access_level < C.AccessLevel.ADMIN and form.role.data != form.user.role.id:
                form.role.errors.append("You do not have permission to change this user's role.")
                raise exc.FormValidationException(form)

            if access_level < C.AccessLevel.ADMIN and form.email.data != form.user.email:
                form.email.errors.append("You do not have permission to change this user's email.")
                raise exc.FormValidationException(form)

            form.user.first_name = form.first_name.data
            form.user.last_name = form.last_name.data
            form.user.email = form.email.data
            form.user.role_id = form.role.data

            return responses.htmx_response(
                redirect=responses.url_for("user_page", user_id=form.user.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route