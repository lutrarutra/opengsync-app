from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm


class APITokenForm(HTMXForm):
    template_path = "forms/auth/api_token.html"

    time_valid_min = inputs.selectable.SelectableInputField("Time Valid", options=[
        (60 * 24 * 30, "30 Days"),
        (60 * 24 * 90, "90 Days"),
        (60 * 24 * 180, "180 Days"),
        (60 * 24 * 365, "1 Year"),
    ], default=60 * 24 * 365)

    def __init__(
        self,
        request: Request,
        user: models.User,
    ):
        super().__init__(request)
        self.user = user


    @staticmethod
    def create_api_token(
        user_id: int,
        request: Request,
        session: SyncSession = Depends(dependencies.db_session),
        current_user: models.User = Depends(dependencies.require_user),
        access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException("You do not have permission to edit this user.")
        
        user = session.get_one(Q.user.select(id=user_id))
        form = APITokenForm(request, user=user)
        form.validate()

        if not form.validate():
            raise exc.FormValidationException(form)

        token = session.save(Q.api_token.create(
            owner=user, time_valid_min=form.time_valid_min.data
        ))

        return responses.html_response(
            template="forms/auth/api_token_complete.html",
            token=token,
            flash=responses.flash("API Token Created!", "success"),
        )