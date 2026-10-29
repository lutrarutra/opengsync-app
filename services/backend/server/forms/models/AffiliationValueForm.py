from fastapi import Depends, Query, Response

from opengsync_db import SyncSession, models

from ...core import responses, dependencies, affiliation_values as av, exceptions as exc
from ...core.context import ctx
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route

MIN_NAME_LENGTH = {av.Kind.INSTITUTE: 2, av.Kind.DEPARTMENT: 2, av.Kind.PI: 3}


def get_value(
    kind: av.Kind,
    key: str = Query(..., description="Key of the value"),
    institute: str | None = Query(None, description="Institute key of a department"),
    session: SyncSession = Depends(dependencies.db_session),
) -> av.Value:
    if (value := av.get(session, kind, key, institute)) is None:
        raise exc.NotFoundException(f"{kind.label} not found.")
    return value


class AffiliationValueForm(HTMXForm):
    """Rename an institute, department or PI (and change a PI's email) on every user having it (admin)."""
    template_path = "forms/affiliation-value.html"

    name = inputs.string.StringInputField("Name", max_length=models.User.institute.type.length)
    # PIs only, which require it (checked by ``_values``)
    email = inputs.string.EmailInputField(
        "Email", required=False, max_length=models.User.pi_email.type.length, autocomplete="off", placeholder="Required",
    )

    def __init__(self, kind: av.Kind, value: av.Value) -> None:
        super().__init__()
        self.kind = kind
        self.value = value
        self.name.label = f"{kind.label} Name"
        self.post_url = responses.url_for("AffiliationValueForm.Edit", kind=kind.value).include_query_params(**value.params)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(kind: av.Kind, value: av.Value = Depends(get_value)) -> "AffiliationValueForm":
            return AffiliationValueForm(kind=kind, value=value)
        return dependency

    def prepare_context(self) -> None:
        session = ctx.session
        self._context["users"] = av.users(session, self.value, self.kind)
        if self.kind == av.Kind.PI:
            self._context["pi_account"] = av.account_of_pi(session, self.value.email)

    def prepare(self) -> None:
        self.name.data = self.value.name
        self.email.data = self.value.email

    def _values(self, session: SyncSession) -> tuple[str, ...]:
        """The submitted values, cleaned like new values of the pickers; records errors."""
        column = self.kind.source.value_columns[0]
        name = " ".join(str(self.name.data or "").split())
        if len(name) < MIN_NAME_LENGTH[self.kind]:
            self.name.errors.append(f"Name should have at least {MIN_NAME_LENGTH[self.kind]} characters.")
        elif len(name) > column.type.length:
            self.name.errors.append(f"Name should have at most {column.type.length} characters.")
        if self.kind != av.Kind.PI:
            return (name,)

        email = str(self.email.data or "").strip().lower()
        if not email:
            self.email.errors.append("Email is required.")
        elif email != (self.value.email or "").strip().lower() and (account := av.account_of_pi(session, self.value.email)):
            # the PI is the user with this email: they and the users naming them as PI must keep pointing to it
            self.email.errors.append(f"This PI is the user {account.name}; change the email of their account instead.")
        return self.kind.source.clean((name, email))

    @htmx_route("GET", "/affiliations/{kind}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(form: "AffiliationValueForm" = Depends(AffiliationValueForm.Init())):
            return form.make_response()
        return route

    @htmx_route("POST", "/affiliations/{kind}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "AffiliationValueForm" = Depends(AffiliationValueForm.Validate()),
        ) -> Response:
            values = form._values(session)
            if form.name.errors or form.email.errors:
                raise exc.FormValidationException(form)

            new_key = form.kind.source.new_key(values)
            if new_key != form.value.key and (other := av.get(session, form.kind, new_key, form.value.institute_key)):
                field = form.email if form.kind == av.Kind.PI and values[0] == form.value.name else form.name
                field.errors.append(f"'{other.name}' already exists: merge into it instead.")
                raise exc.FormValidationException(form)

            num_users = av.assign(session, form.kind, form.value, values)
            return responses.htmx_response(
                redirect=responses.url_for("admin_affiliations_page").include_query_params(tab=f"affiliations-{form.kind.value}"),
                flash=responses.flash(f"{form.kind.label} updated for {num_users} user{'s' if num_users != 1 else ''}.", "success"),
            )
        return submit
