from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class SelectPoolLibrariesAction(HTMXForm):
    template_path = "actions/select-pool-libraries.html"

    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "select-pool-libraries",
        status_in=[
            C.LibraryStatus.DRAFT,
            C.LibraryStatus.SUBMITTED,
            C.LibraryStatus.ACCEPTED,
            C.LibraryStatus.PREPARING,
            C.LibraryStatus.STORED,
        ],
        select_all=True,
        required=False,
        pooled=False
    )

    def __init__(
        self,
        pool_id: int,
    ) -> None:
        super().__init__()
        self.pool_id = pool_id

    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            pool_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ) -> "SelectPoolLibrariesAction":
            if session.first(Q.pool.select(id=pool_id)) is None:
                raise exc.ItemNotFoundException()
            return cls(pool_id=pool_id)
        return dependency

    @htmx_route("GET", "/{pool_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SelectPoolLibrariesAction" = Depends(SelectPoolLibrariesAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{pool_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectPoolLibrariesAction" = Depends(SelectPoolLibrariesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            pool = session.get_one(Q.pool.select(id=form.pool_id))
            if pool is None:
                raise exc.ItemNotFoundException()

            for library in form.selected_library_ids.get_selected_libraries(session=session):
                library.pool_id = pool.id
                session.save(library)

            session.flush()

            return responses.htmx_response(
                redirect=responses.url_for("pool_page", pool_id=pool.id),
                flash=responses.flash("Libraries added to pool!", "success"),
            )
        return route