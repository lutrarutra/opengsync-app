import json

from fastapi import Depends, Response

from opengsync_db import SyncSession, queries as Q, categories as C
from opengsync_db.categories import LibraryStatus, LibraryType, LabChecklistType

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class LibraryPrepAction(HTMXForm):
    template_path = "actions/library-prep.html"

    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "library-prep",
        status_in=[LibraryStatus.ACCEPTED],
        select_all=True,
        required=True,
    )

    def __init__(
        self,
        lab_prep_id: int,
        library_type_filter: list[C.LibraryType] | None = None,
    ) -> None:
        super().__init__()
        self.lab_prep_id = lab_prep_id
        self.library_type_filter = library_type_filter

    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            lab_prep_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ) -> "LibraryPrepAction":
            if (lab_prep := session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
                raise exc.ItemNotFoundException()

            library_type_filter: list[C.LibraryType] | None = None
            if lab_prep.checklist_type == LabChecklistType.CUSTOM:
                library_type_filter = None
            else:
                library_type_filter = LibraryType.get_check_list_library_types(lab_prep.checklist_type) or None

            return cls(lab_prep_id=lab_prep_id, library_type_filter=library_type_filter)
        return dependency

    @htmx_route("GET", "/{lab_prep_id}", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LibraryPrepAction" = Depends(LibraryPrepAction.Init()),
        ) -> Response:
            if form.library_type_filter is not None:
                form.selected_library_ids.query_params["type_in"] = json.dumps(
                    [t.id for t in form.library_type_filter]
                )
            return form.make_response()
        return route

    @htmx_route("POST", "/{lab_prep_id}", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LibraryPrepAction" = Depends(LibraryPrepAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            lab_prep = session.get_one(Q.lab_prep.select(id=form.lab_prep_id))
            if lab_prep is None:
                raise exc.ItemNotFoundException()

            for library in form.selected_library_ids.get_selected_libraries(session=session):
                lab_prep.libraries.append(library)

            session.save(lab_prep)

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep_id),
                flash=responses.flash("Libraries added to prep!", "success"),
            )
        return route