from fastapi import Depends

from opengsync_db import models, queries as Q, SyncSession, actions

from ...core import dependencies, exceptions as exc, responses, redis as rds
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class MergeUsersAction(HTMXForm):
    template_path = "workflows/merge_users.html"

    user_dst = inputs.searchable.SearchableInputField(
        "Destination User (kept)", route="search_users", required=True,
    )
    user_src = inputs.searchable.SearchableInputField(
        "Source User (deleted)", route="search_users", required=True,
    )

    def __init__(self) -> None:
        super().__init__()
        self.preview_url = responses.url_for(f"{self.__class__.__name__}.Preview")
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency() -> "MergeUsersAction":
            return MergeUsersAction()
        return dependency

    def _get_users(self, session: SyncSession, current_user: models.User) -> tuple[models.User, models.User]:
        if self.user_dst.data is None:
            self.user_dst.errors.append("Please select a destination user to merge into.")
            raise exc.FormValidationException(self)

        if self.user_src.data is None:
            self.user_src.errors.append("Please select a source user to merge from.")
            raise exc.FormValidationException(self)

        if self.user_dst.data == self.user_src.data:
            self.user_src.errors.append("Source and destination users cannot be the same.")
            self.user_dst.errors.append("Source and destination users cannot be the same.")
            raise exc.FormValidationException(self)

        if int(self.user_src.data) == current_user.id:
            self.user_src.errors.append("You cannot merge away your own account.")
            raise exc.FormValidationException(self)

        if (user_dst := session.first(Q.user.select(id=int(self.user_dst.data)))) is None:
            self.user_dst.errors.append("Selected user not found.")
            raise exc.FormValidationException(self)

        if (user_src := session.first(Q.user.select(id=int(self.user_src.data)))) is None:
            self.user_src.errors.append("Selected user not found.")
            raise exc.FormValidationException(self)

        return user_dst, user_src

    @htmx_route("GET", "/merge-users")
    def Begin(cls) -> RouteFunc:
        def route(
            _=Depends(dependencies.require_admin),
            form: "MergeUsersAction" = Depends(MergeUsersAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/merge-users/preview")
    def Preview(cls) -> RouteFunc:
        def route(
            # first: dependencies resolve in order, and a non-admin must not see the form validated
            current_user: models.User = Depends(dependencies.require_admin),
            form: "MergeUsersAction" = Depends(MergeUsersAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> responses.Response:
            user_dst, user_src = form._get_users(session, current_user)
            preview = actions.merge_users_preview(session, user_dst=user_dst, user_src=user_src)
            return form.make_response(preview=preview, dst_user=user_dst, src_user=user_src)
        return route

    @htmx_route("POST", "/merge-users")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_admin),
            form: "MergeUsersAction" = Depends(MergeUsersAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            r: rds.RedisClient = Depends(dependencies.redis),
        ) -> responses.Response:
            user_dst, user_src = form._get_users(session, current_user)
            src_id, dst_id = user_src.id, user_dst.id
            src_token_hashes = [token.token_hash for token in session.scalars(Q.api_token.select(owner_id=src_id))]

            try:
                user = actions.merge_users(session, user_dst=user_dst, user_src=user_src)
            except ValueError as e:
                form.user_src.errors.append(str(e))
                raise exc.FormValidationException(form)

            # Cached users, access levels, route caches and API tokens still name the old owner.
            for user_id in (src_id, dst_id):
                r.delete(f"user:{user_id}")
                r.delete_pattern(f"*:user:{user_id}")
            r.delete_pattern(f"chat:{src_id}:*")
            for token_hash in src_token_hashes:
                r.delete(f"api_token:{token_hash}")

            return responses.htmx_response(
                redirect=responses.url_for("user_page", user_id=user.id),
                flash=responses.flash("Users merged successfully!", "success"),
            )
        return route
