from fastapi import Request, Depends, Query
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, secrets
from ...components import inputs
from ..HTMXForm import HTMXForm, FormFunc, htmx_route, RouteFunc


class ChangePasswordForm(HTMXForm):
    template_path = "forms/auth/change_password.html"

    current_password = inputs.string.PasswordInputField("Current Password")
    new_password = inputs.string.PasswordInputField("New Password", min_length=8)
    confirm_new_password = inputs.string.PasswordInputField("Confirm New Password")

    def __init__(self, user: models.User):
        super().__init__()
        self.user = user
        self.post_url = responses.url_for("ChangePasswordForm.Submit", user_id=user.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            user_id: int | None = Query(None, description="The ID of the user whose password is being changed."),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "ChangePasswordForm":
            user = current_user
            if user_id is not None and user.id != user_id:
                if session.get_access_level(Q.user.permissions(user_id=user_id, viewer_id=current_user.id)) < C.AccessLevel.ADMIN:
                    raise exc.NoPermissionsException("You do not have permission to change this user's password.")
                user = session.get_one(Q.user.select(id=user_id))
            
            return ChangePasswordForm(user=user)
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "ChangePasswordForm" = Depends(ChangePasswordForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ChangePasswordForm" = Depends(ChangePasswordForm.Validate()),
            bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
            current_user: models.User = Depends(dependencies.require_user),
            access_level: C.AccessLevel = Depends(dependencies.user_permissions),
        ) -> Response:
            if current_user.id != form.user.id and access_level < C.AccessLevel.ADMIN:
                raise exc.NoPermissionsException("You do not have permission to change this user's password.")

            if not bcrypt.check_password_hash(form.user.password, form.current_password.data):
                form.current_password.errors.append("Current password is incorrect.")
                raise exc.FormValidationException(form)

            if form.new_password.data != form.confirm_new_password.data:
                form.confirm_new_password.errors.append("New passwords do not match.")
                raise exc.FormValidationException(form)

            form.user.password = bcrypt.generate_password_hash(form.new_password.data)

            if current_user.id == form.user.id:
                resp = responses.htmx_response(
                    redirect=responses.url_for("login_page"),
                    flash=responses.flash("Password Changed, please log-in!", "success"),
                )
                resp.delete_cookie(key="access_token", path="/", samesite="lax")
                resp.delete_cookie(key="csrf_token", path="/", samesite="lax")
                return resp

            return responses.html_response(
                redirect=responses.url_for("user_page", user_id=form.user.id),
                flash=responses.flash("Password Changed!", "success"),
            )
        return route