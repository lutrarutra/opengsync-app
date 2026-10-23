from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, auth, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..common import UserProfileMixin


class UserForm(UserProfileMixin, HTMXForm):
    """Edit a user. Organization and PI are required from a customer editing their own profile (and once set, a
    customer cannot clear them); insiders may leave them empty for anyone."""
    template_path = "forms/user.html"

    first_name = inputs.string.StringInputField("First Name", max_length=models.User.first_name.type.length)
    last_name = inputs.string.StringInputField("Last Name", max_length=models.User.last_name.type.length)
    email = inputs.string.StringInputField("Email", max_length=models.User.email.type.length)
    role = inputs.selectable.SelectableInputField("Role", C.UserRole.as_selectable())

    def __init__(self, user: models.User, editor: models.User) -> None:
        super().__init__()
        self.user = user
        self.editor = editor
        self.post_url = responses.url_for("UserForm.Edit", user_id=user.id)
        self.init_profile_fields(other_user=editor.id != user.id)
        # Only admins may change the email
        self.email.read_only = not editor.is_admin

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            user_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> "UserForm":
            user = session.get_one(Q.user.select(id=user_id))
            return UserForm(user=user, editor=current_user)
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
            form.init_profile_fields(form.user, other_user=form.editor.id != form.user.id)
            return form.make_response()
        return route

    @htmx_route("POST", "/{user_id}/edit")
    def Edit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
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

            # The DB unique constraint is case-sensitive, emails are compared case-insensitively
            if form.email.data.lower() != form.user.email.lower() and session.exists(Q.user.select(email=form.email.data)):
                form.email.errors.append("User with this email already exists.")
                raise exc.FormValidationException(form)

            customer_editor = not form.editor.is_insider
            profile = form.validate_profile(
                session,
                name=f"{form.first_name.data} {form.last_name.data}",
                email=form.email.data,
                required=customer_editor and form.editor.id == form.user.id,
                keep=form.user if customer_editor else None,
            )

            form.user.first_name = form.first_name.data
            form.user.last_name = form.last_name.data
            form.user.email = form.email.data
            auth.set_role(form.user, C.UserRole.get(form.role.data))
            form.apply_profile(form.user, profile)

            return responses.htmx_response(
                redirect=responses.url_for("user_page", user_id=form.user.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route