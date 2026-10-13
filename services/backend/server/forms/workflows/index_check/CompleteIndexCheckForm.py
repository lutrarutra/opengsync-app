from types import SimpleNamespace

from fastapi import Depends, Response
import sqlalchemy as sa
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import context, dependencies, responses
from ...HTMXForm import RouteFunc, htmx_route
from .IndexCheckWorkflow import IndexCheckWorkflowStep, IndexCheckWorkflow


class CompleteIndexCheckForm(IndexCheckWorkflowStep):
    template_path = "workflows/index_check/complete.html"

    def __init__(self, workflow: IndexCheckWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.orientation_results = workflow.metadata.get("orientation_results", [])

        indices = {
            index.id: index for index in context.ctx.session.execute(
                sa.select(models.LibraryIndex)
                .where(models.LibraryIndex.id.in_([r["library_index_id"] for r in self.orientation_results]))
                .options(orm.selectinload(models.LibraryIndex.library))
            ).scalars()
        }

        # Build summary for display, showing each index as it will be saved
        summary = []
        for result in self.orientation_results:
            if (index := indices.get(result["library_index_id"])) is None:
                continue
            # Transient copy for library_index_cell: no relationships are set, so it is never added to the session
            preview = models.LibraryIndex(
                library_id=index.library_id,
                index_kit_i7_id=index.index_kit_i7_id,
                index_kit_i5_id=index.index_kit_i5_id,
                name_i7=index.name_i7,
                name_i5=index.name_i5,
                sequence_i7=result.get("sequence_i7"),
                sequence_i5=result.get("sequence_i5"),
                orientation=C.BarcodeOrientation.FORWARD,
            )
            summary.append({
                "library_name": result["library_name"],
                "library": SimpleNamespace(index_type=index.library.index_type, indices=[preview]),
                "orientation": preview.orientation,
                "was_reverse_complemented_i7": result.get("was_reverse_complemented_i7", False),
                "was_reverse_complemented_i5": result.get("was_reverse_complemented_i5", False),
            })
        self._context["summary"] = summary

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "CompleteIndexCheckForm" = Depends(CompleteIndexCheckForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "CompleteIndexCheckForm" = Depends(CompleteIndexCheckForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            orientation_results = form.orientation_results

            for result in orientation_results:
                library_index_id = result.get("library_index_id")
                if library_index_id is None:
                    continue

                index = session.get_one(Q.library_index.select(id=library_index_id))
                if index is None:
                    continue

                # Set orientation to FORWARD
                index.orientation = C.BarcodeOrientation.FORWARD

                # Update the sequence of each reverse-complemented barcode
                if result.get("was_reverse_complemented_i7") and (new_seq_i7 := result.get("sequence_i7")) is not None:
                    index.sequence_i7 = new_seq_i7
                if result.get("was_reverse_complemented_i5") and (new_seq_i5 := result.get("sequence_i5")) is not None:
                    index.sequence_i5 = new_seq_i5

            session.flush()

            flash = responses.flash("Index orientations validated!", "success")

            # The review checklist step is derived from the indices, so only warn if some are still unvalidated
            if form.workflow.seq_request_id is not None:
                seq_request = session.get_one(Q.seq_request.select(id=form.workflow.seq_request_id))
                if not seq_request.all_indices_validated():
                    flash = responses.flash("Some libraries in this request still have unvalidated index orientations.", "warning")

            form.workflow.complete()

            # Redirect back to originating context
            if form.workflow.seq_request_id is not None:
                redirect = responses.url_for("seq_request_page", seq_request_id=form.workflow.seq_request_id)
            elif form.workflow.lab_prep_id is not None:
                redirect = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)
            elif form.workflow.pool_id is not None:
                redirect = responses.url_for("pool_page", pool_id=form.workflow.pool_id)
            else:
                redirect = responses.url_for("dashboard")

            return responses.htmx_response(redirect=redirect, flash=flash)
        return route