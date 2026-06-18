from fastapi import Request, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm


class UserForm(HTMXForm):
    template_path = "forms/user.html"

    first_name = inputs.string.StringInputField("First Name", max_length=models.User.first_name.type.length)
    last_name = inputs.string.StringInputField("Last Name", max_length=models.User.last_name.type.length)
    email = inputs.string.StringInputField("Email", max_length=models.User.email.type.length)
    role = inputs.selectable.SelectableInputField("Role", C.UserRole.as_selectable())


    def __init__(
        self,
        request: Request,
        user: models.User,
    ):
        super().__init__(request)
        self.user = user

    async def prepare(self):
        self.first_name.data = self.user.first_name
        self.last_name.data = self.user.last_name
        self.email.data = self.user.email
        self.role.data = self.user.role.id

    @staticmethod
    async def edit_user(
        user_id: int,
        request: Request,
        session: AsyncSession = Depends(dependencies.db_session),
        access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    ) -> Response:
        if access_level < C.AccessLevel.WRITE:
            raise exc.NoPermissionsException("You do not have permission to edit this user.")
        
        user = await session.get_one(Q.user.select(id=user_id))
        form = UserForm(request, user=user)
        await form.validate()

        if not form.validate():
            raise exc.FormValidationException(form)
        
        if access_level < C.AccessLevel.ADMIN and form.role.data != form.user.role.id:
            raise exc.NoPermissionsException("You do not have permission to change this user's role.")
        
        if access_level < C.AccessLevel.ADMIN and form.email.data != form.user.email:
            raise exc.NoPermissionsException("You do not have permission to change this user's email.")

        user = await session.get_one(Q.user.select(id=user_id))
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data
        user.role = C.UserRole(form.role.data)

        return await responses.html_response(
            redirect=request.url_for("user_page", user_id=user.id),
            flash=responses.flash("Changes Saved!", "success"),
        )