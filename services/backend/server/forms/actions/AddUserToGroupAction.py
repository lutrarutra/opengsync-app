from fastapi import Depends

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class AddUserToGroupAction(HTMXForm):
    template_path = "actions/add-user-to-group.html"

    email = inputs.string.EmailInputField("Email", required=True, max_length=255)
    affiliation_type = inputs.selectable.SelectableInputField(
        "Affiliation Type",
        C.AffiliationType.as_selectable_no_owner(),
        default=C.AffiliationType.MEMBER.id,
    )

    def __init__(self, group: models.Group):
        super().__init__()
        self.group = group
        self._context["group"] = group
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", group_id=group.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            group_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ):
            group = session.get_one(Q.group.select(id=group_id))
            return AddUserToGroupAction(group=group)
        return form

    @htmx_route("GET", "/{group_id}/add-user")
    def Begin(cls) -> RouteFunc:
        def route(
            form: AddUserToGroupAction = Depends(AddUserToGroupAction.Init()),
            access_level: C.AccessLevel = Depends(dependencies.group_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            return form.make_response()
        return route

    @htmx_route("POST", "/{group_id}/add-user")
    def Submit(cls) -> RouteFunc:
        def route(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AddUserToGroupAction" = Depends(AddUserToGroupAction.Validate()),
            access_level: C.AccessLevel = Depends(dependencies.group_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()

            user = session.first(Q.user.select(email=form.email.data.strip()))
            if user is None:
                form.email.errors.append("User with this email does not exist.")
                raise exc.FormValidationException(form)

            if C.AffiliationType.get(form.affiliation_type.data) == C.AffiliationType.OWNER:
                form.affiliation_type.errors.append("Owner affiliation type is not allowed.")
                raise exc.FormValidationException(form)

            if session.first(Q.affiliation.select(user_id=user.id, group_id=form.group.id)) is not None:
                form.email.errors.append("User is already in this group.")
                raise exc.FormValidationException(form)

            session.save(Q.affiliation.create(
                user=user,
                group=form.group,
                type=C.AffiliationType.get(form.affiliation_type.data),
            ))

            return responses.htmx_response(
                redirect=responses.url_for("group_page", group_id=form.group.id),
                flash=responses.flash("User added to group.", "success"),
            )
        return route