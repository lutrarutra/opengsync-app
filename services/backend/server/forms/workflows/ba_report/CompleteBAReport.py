import os

import sqlalchemy as sa
from pydantic import BaseModel
from fastapi import Depends

from opengsync_db import queries as Q, SyncSession, categories as C, models
from opengsync_db.transitions import run_operation, lab as lab_ops

from ....core import dependencies, responses, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .BAReportWorkflow import BAReportWorkflowStep, BAReportWorkflow

def save_report(form: "BAReportWorkflowStep", session: SyncSession, uploader_id: int, sub_form_lists, pdf) -> responses.Response:
    """Save the report PDF and the sizes of the selected objects, as legacy ``CompleteBAForm.save_changes``:
    each object with a size is linked to the report, an empty size clears size and report link, an
    ACCEPTED pool with a size becomes STORED. Completes the workflow and returns the redirect."""
    # The rows are submitted by the client: only objects selected in step 1 may be updated
    sample_table = form.workflow.tables["sample_table"]
    selected = set(zip(sample_table["type"], sample_table["id"].astype(int)))
    entries = [entry for sub_forms in sub_form_lists for entry in sub_forms.entries]
    if any((entry.type.data, entry.id_.data) not in selected for entry in entries):
        raise exc.BadRequestException("The report does not match the selection. Please start again.")

    filename, extension = os.path.splitext(pdf.data.filename)
    media_file = session.save(Q.media_file.create(
        name=filename,
        extension=extension,
        size_bytes=pdf.data.size,
        type=C.MediaFileType.BIOANALYZER_REPORT,
        uploader_id=uploader_id,
        lab_prep_id=form.workflow.lab_prep_id,
    ), flush=True)

    models_by_type = {"sample": models.Sample, "library": models.Library, "pool": models.Pool, "lane": models.Lane}
    with run_operation(session, lab_ops.BA_REPORT):
        for entry in entries:
            obj = session.get_one(sa.select(models_by_type[entry.type.data]).where(models_by_type[entry.type.data].id == entry.id_.data))
            obj.avg_fragment_size = entry.avg_fragment_size.data
            obj.ba_report_id = media_file.id if entry.avg_fragment_size.data is not None else None
            if isinstance(obj, models.Pool) and entry.avg_fragment_size.data is not None and obj.status == C.PoolStatus.ACCEPTED:
                obj.status = C.PoolStatus.STORED
            session.save(obj)

    # written last, so a failing database change leaves no file behind
    session.flush()
    pdf.save(media_file)

    redirect = responses.url_for("dashboard")
    if form.workflow.lab_prep_id is not None:
        redirect = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)
    elif form.workflow.experiment_id is not None:
        redirect = responses.url_for("experiment_page", experiment_id=form.workflow.experiment_id)

    form.workflow.complete()
    return responses.htmx_response(redirect=redirect, flash=responses.flash("Changes Saved!", "success"))


class SubForm(SubHTMXForm):
    id_ = inputs.numeric.IntInputField("ID", required=True, read_only=True)
    name = inputs.string.StringInputField("Name", required=True, read_only=True)
    type = inputs.string.StringInputField("Type", required=True, read_only=True)
    avg_fragment_size = inputs.numeric.IntInputField("Avg. Fragment Size", unit="bp.", required=False, ge=1)

class CompleteBAReport(BAReportWorkflowStep):
    template_path = "workflows/ba_report/bar-3.html"

    sample_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    library_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    lane_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)

    pdf = inputs.file.FileInputField("BA PDF File", required=True, allowed_extensions=["pdf"])

    def __init__(self, workflow: "BAReportWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.ba_table = workflow.tables["ba_table"]

    def prepare(self):
        class SampleRow(BaseModel):
            id: int
            name: str
            type: str
            avg_fragment_size: int | None

        for _, row in parsing.safe_iter(self.ba_table, SampleRow):
            match row.type:
                case "sample":
                    entry = self.sample_forms.append_entry()
                case "library":
                    entry = self.library_forms.append_entry()
                case "pool":
                    entry = self.pool_forms.append_entry()
                case "lane":
                    entry = self.lane_forms.append_entry()
                case _:
                    raise exc.OpeNGSyncServerException(f"Unknown sample type: {row.type}")
                
            entry.id_.data = row.id
            entry.name.data = row.name
            entry.type.data = row.type
            entry.avg_fragment_size.data = row.avg_fragment_size

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "CompleteBAReport" = Depends(CompleteBAReport.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user_id: int = Depends(dependencies.require_user_id),
        ):
            return save_report(
                form, session, current_user_id,
                (form.sample_forms, form.library_forms, form.pool_forms, form.lane_forms), form.pdf,
            )
        return route