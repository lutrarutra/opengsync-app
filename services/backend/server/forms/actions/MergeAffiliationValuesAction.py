from fastapi import Depends, Response

from opengsync_db import SyncSession

from ...core import responses, dependencies, affiliation_values as av, column_values, exceptions as exc
from ...core.context import ctx
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..models.AffiliationValueForm import get_value


class MergeAffiliationValuesAction(HTMXForm):
    """Give the users of an institute, department or PI those of another one (admin). Departments are merged within
    their institute."""
    template_path = "actions/merge-affiliation-values.html"

    target = inputs.column_value.ColumnValueInputField(
        "Merge Into", source="user_institute", allow_new=False, placeholder="Search…",
    )

    def __init__(self, kind: av.Kind, value: av.Value) -> None:
        super().__init__()
        self.kind = kind
        self.value = value
        self.target.source = kind.source_name
        self.target.label = f"Merge Into {kind.label}"
        self.target.placeholder = f"Search {kind.plural.lower()}…"
        if kind == av.Kind.DEPARTMENT and value.institute_key:
            self.target.query_params = {"institute": value.institute_key}
        self.post_url = responses.url_for("MergeAffiliationValuesAction.Submit", kind=kind.value).include_query_params(**value.params)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(kind: av.Kind, value: av.Value = Depends(get_value)) -> "MergeAffiliationValuesAction":
            return MergeAffiliationValuesAction(kind=kind, value=value)
        return dependency

    def prepare_context(self) -> None:
        self._context["users"] = av.users(ctx.session, self.value, self.kind)

    def _target(self, session: SyncSession) -> tuple[str, ...]:
        """Values of the selected target; records errors."""
        if not self.target.data:  # reported by the form (required)
            return ()
        key = str(self.target.data)
        if key == self.value.key:
            self.target.errors.append(f"Select another {self.kind.label.lower()}.")
            return ()
        filters = {"institute": self.value.institute_key} if self.kind == av.Kind.DEPARTMENT and self.value.institute_key else None
        if (values := column_values.lookup(session, self.kind.source, key, filters)) is None:
            self.target.errors.append(f"Invalid {self.kind.label.lower()} selected.")
            return ()
        self.target.text = values[0]
        if self.kind == av.Kind.PI and (account := av.account_of_pi(session, self.value.email)):
            # its users would no longer point to the PI's account (the users naming themselves PI included)
            self.target.errors.append(f"{self.value.name} is the user {account.name}: merge the other PI into this one instead.")
        return values

    @htmx_route("GET", "/affiliations/{kind}/merge", name="Submit")
    def Render(cls) -> RouteFunc:
        def route(form: "MergeAffiliationValuesAction" = Depends(MergeAffiliationValuesAction.Init())):
            return form.make_response()
        return route

    @htmx_route("POST", "/affiliations/{kind}/merge", name="Submit")
    def Submit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "MergeAffiliationValuesAction" = Depends(MergeAffiliationValuesAction.Validate()),
        ) -> Response:
            values = form._target(session)
            if form.target.errors:
                raise exc.FormValidationException(form)

            num_users = av.assign(session, form.kind, form.value, values)
            return responses.htmx_response(
                redirect=responses.url_for("admin_affiliations_page").include_query_params(tab=f"affiliations-{form.kind.value}"),
                flash=responses.flash(
                    f"Merged '{form.value.name}' into '{values[0]}' ({num_users} user{'s' if num_users != 1 else ''}).", "success",
                ),
            )
        return submit
