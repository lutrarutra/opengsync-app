import os

from pydantic import BaseModel
from fastapi import Depends

from opengsync_db import queries as Q, SyncSession, categories as C, models

from ....core import dependencies, responses, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .BAReportWorkflow import BAReportWorkflowStep, BAReportWorkflow

class SubForm(SubHTMXForm):
    id_ = inputs.numeric.IntInputField("ID", required=True, read_only=True)
    name = inputs.string.StringInputField("Name", required=True, read_only=True)
    type = inputs.string.StringInputField("Type", required=True, read_only=True)
    avg_fragment_size = inputs.numeric.IntInputField("Avg. Fragment Size", unit="bp.", required=False, ge=0)

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
            current_user: models.User = Depends(dependencies.require_user),
        ):
            for entry in form.sample_forms:
                sample = session.get_one(Q.sample.select(id=entry.id_.data))
                sample.avg_fragment_size = entry.avg_fragment_size.data

            for entry in form.library_forms.entries:
                library = session.get_one(Q.library.select(id=entry.id_.data))
                library.avg_fragment_size = entry.avg_fragment_size.data

            for entry in form.pool_forms.entries:
                pool = session.get_one(Q.pool.select(id=entry.id_.data))
                pool.avg_fragment_size = entry.avg_fragment_size.data

            for entry in form.lane_forms.entries:
                lane = session.get_one(Q.lane.select(id=entry.id_.data))
                lane.avg_fragment_size = entry.avg_fragment_size.data

            filename, extension = os.path.splitext(form.pdf.data.filename)
            media_file = session.save(Q.media_file.create(
                name=filename,
                extension=extension,
                size_bytes=form.pdf.data.size,
                type=C.MediaFileType.BIOANALYZER_REPORT,
                uploader_id=current_user.id,
            ))
            form.pdf.save(media_file)
            
            redirect = responses.url_for("dashboard")
            if form.workflow.lab_prep_id is not None:
                redirect = responses.url_for("lab_prep_page", lab_prep_id=form.workflow.lab_prep_id)
            elif form.workflow.experiment_id is not None:
                redirect = responses.url_for("experiment_page", experiment_id=form.workflow.experiment_id)

            return responses.htmx_response(redirect=redirect, flash=responses.flash("Changes Saved!", "success"))
        return route