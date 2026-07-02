from typing import Literal
from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, secrets
from ...components import inputs
from ..HTMXForm import HTMXForm


class ChangePasswordForm(HTMXForm):
    template_path = "forms/auth/change_password.html"

    current_password = inputs.string.PasswordInputField("Current Password")
    new_password = inputs.string.PasswordInputField("New Password", min_length=8)
    confirm_new_password = inputs.string.PasswordInputField("Confirm New Password")

    def __init__(
        self,
        request: Request,
        user: models.User,
    ):
        super().__init__(request)
        self.user = user

    @staticmethod
    def change_password(
        user_id: int,
        request: Request,
        session: SyncSession = Depends(dependencies.db_session),
        bcrypt: secrets.BcryptCompat = Depends(dependencies.get_bcrypt),
        current_user: models.User = Depends(dependencies.require_user),
        access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    ) -> Response:
        if current_user.id != user_id and access_level < C.AccessLevel.ADMIN:
            raise exc.NoPermissionsException("You do not have permission to change this user's password.")
        
        user = session.get_one(Q.user.select(id=user_id))
        form = ChangePasswordForm(request, user=user)
        form.validate()

        if not bcrypt.check_password_hash(user.password, form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
            raise exc.FormValidationException(form)

        if form.new_password.data != form.confirm_new_password.data:
            form.confirm_new_password.errors.append("New passwords do not match.")
            raise exc.FormValidationException(form)

        user.password = bcrypt.generate_password_hash(form.new_password.data)

        return responses.html_response(
            redirect=request.url_for("user_page", user_id=user.id),
            flash=responses.flash("Password Changed!", "success"),
        )