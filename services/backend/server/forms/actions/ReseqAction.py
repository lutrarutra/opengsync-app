from fastapi import Depends, Response, Query
from loguru import logger

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class ReseqAction(HTMXForm):
    template_path = "actions/reseq.html"

    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries",
        "reseq",
        select_all=True,
        required=True,
    )
    reprep_type = inputs.selectable.SelectableInputField(
        "Re-Sequencing Type",
        options=[
            (0, "Indexed"),
            (1, "Raw"),
        ],
        default=0,
        description="Indexed: selected libraries are prepared (and indexed) but not pooled. Raw: selected libraries need to be prepared from raw samples.",
    )

    def __init__(
        self,
        seq_request_id: int | None = None,
        lab_prep_id: int | None = None,
    ) -> None:
        super().__init__()
        self.seq_request_id = seq_request_id
        self.lab_prep_id = lab_prep_id

    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            seq_request_id: int | None = Query(None),
            lab_prep_id: int | None = Query(None),
            user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "ReseqAction":
            if not user.is_insider:
                raise exc.NoPermissionsException()

            # Validate context and permissions
            if seq_request_id is not None:
                seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
                if session.get_access_level(Q.seq_request.permissions(seq_request.id, user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException()
            elif lab_prep_id is not None:
                lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))
                if not lab_prep:
                    raise exc.ItemNotFoundException()
            else:
                raise exc.OpeNGSyncServerException("Either seq_request_id or lab_prep_id must be provided.")

            return cls(seq_request_id=seq_request_id, lab_prep_id=lab_prep_id)
        return dependency

    @htmx_route("GET", name="Begin")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "ReseqAction" = Depends(ReseqAction.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ReseqAction" = Depends(ReseqAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            indexed = form.reprep_type.data == 0

            for library in form.selected_library_ids.get_selected_libraries(session=session):
                seq_request_id = library.seq_request_id
                if form.seq_request_id is not None:
                    seq_request_id = form.seq_request_id

                status = C.LibraryStatus.STORED if indexed else C.LibraryStatus.ACCEPTED

                actions.clone_library(
                    session=session,
                    library_id=library.id,
                    seq_request_id=seq_request_id,
                    indexed=indexed,
                    status=status,
                )

            flash = responses.flash("Libraries Cloned!", "success")

            if form.seq_request_id is not None:
                return responses.htmx_response(
                    redirect=responses.url_for("seq_request_page", seq_request_id=form.seq_request_id),
                    flash=flash,
                )

            if form.lab_prep_id is not None:
                return responses.htmx_response(
                    redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep_id),
                    flash=flash,
                )

            return responses.htmx_response(redirect=responses.url_for("dashboard"), flash=flash)
        return route