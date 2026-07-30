from fastapi import Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class APITokenForm(HTMXForm):
    template_path = "forms/auth/api_token.html"

    time_valid_min = inputs.selectable.SelectableInputField("Time Valid", options=[
        (60 * 24 * 30, "30 Days"),
        (60 * 24 * 90, "90 Days"),
        (60 * 24 * 180, "180 Days"),
        (60 * 24 * 365, "1 Year"),
    ], default=60 * 24 * 365)

    def __init__(self, user: models.User) -> None:
        super().__init__()
        self.user = user
        self.post_url = responses.url_for("APITokenForm.Create", user_id=user.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            user_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "APITokenForm":
            user = session.get_one(Q.user.select(id=user_id))
            return APITokenForm(user=user)
        return dependency

    @htmx_route("GET", "/{user_id}/create-api-token")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "APITokenForm" = Depends(APITokenForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/{user_id}/create-api-token")
    def Create(cls) -> RouteFunc:
        def route(
            user_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            form: "APITokenForm" = Depends(APITokenForm.Validate()),
            access_level: C.AccessLevel = Depends(dependencies.user_permissions),
        ) -> Response:
            if current_user.id != user_id and access_level < C.AccessLevel.ADMIN:
                raise exc.NoPermissionsException("You do not have permission to create API tokens for this user.")

            token = session.save(Q.api_token.create(
                owner=form.user,
                time_valid_min=form.time_valid_min.data,
            ))

            return responses.htmx_response(
                template="forms/auth/api_token_complete.html",
                token=token,
                flash=responses.flash("API Token Created!", "success"),
            )
        return route