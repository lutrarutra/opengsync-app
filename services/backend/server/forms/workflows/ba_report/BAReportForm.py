import io
import re
import os
from typing import Literal

import pandas as pd
from pydantic import BaseModel
from fastapi import Depends, Response, Query
from loguru import logger

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ....core import dependencies, responses, exceptions as exc
from ....components import inputs
from ....utils import parsing
from ...HTMXForm import RouteFunc, htmx_route
from ...SubHTMXForm import SubHTMXForm
from .BAReportWorkflow import BAReportWorkflowStep, BAReportWorkflow
from .ParseBAExcelFileForm import ParseBAExcelFileForm


class SubForm(SubHTMXForm):
    id_ = inputs.numeric.IntInputField("ID", required=True, read_only=True)
    name = inputs.string.StringInputField("Name", required=True, read_only=True)
    type = inputs.string.StringInputField("Type", required=True, read_only=True)
    avg_fragment_size = inputs.numeric.IntInputField("Avg. Fragment Size", unit="bp.", required=False, ge=0)

class BAReportForm(BAReportWorkflowStep):
    template_path = "workflows/ba_report/bar-1.html"

    sample_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    library_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    pool_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)
    lane_forms = inputs.dynamic.SubFormList[SubForm](min_elements=0)

    ba_excel = inputs.file.FileInputField("BA Excel File", required=False, allowed_extensions=["csv"])
    pdf = inputs.file.FileInputField("BA PDF File", required=False, allowed_extensions=["pdf"])

    def __init__(self, workflow: "BAReportWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.active_tab = "excel"

    def prepare(self):
        class SampleRow(BaseModel):
            id: int
            name: str
            type: str
            avg_fragment_size: int | None

        sample_table = self.workflow.tables["sample_table"]
        for _, row in parsing.safe_iter(sample_table, SampleRow):
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
            form: "BAReportForm" = Depends(BAReportForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            method: Literal["excel", "manual"] = Query(..., description="The method used to submit the form. Can be 'excel' or 'manual'."),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> Response:
            form.active_tab = method
            if method == "manual":
                if not form.pdf.data:
                    form.pdf.errors.append("Please upload a PDF file.")
                    raise exc.FormValidationException(form)
                
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

                return responses.htmx_response(
                    redirect=redirect,
                    flash=responses.flash("Changes Saved!", "success"),
                )
            elif method == "excel":
                if not form.ba_excel.data:
                    form.ba_excel.errors.append("Please upload an Excel file.")
                    raise exc.FormValidationException(form)
                
                data = {
                    "sample_name": [],
                    "avg_fragment_size": [],
                }
                
                excel_content = form.ba_excel.data.content.decode("latin-1")

                pattern = r"Sample Name,([^\r\n]+).*?Region Table\s+([\s\S]+?)(?=\n\s*\n\s*Sample Name|\Z)"

                for it in re.finditer(pattern, excel_content, re.MULTILINE | re.DOTALL):
                    sample_name = it.group(1).strip()
                    region_table_raw = it.group(2).strip()
                    
                    data["sample_name"].append(sample_name)
                    
                    try:
                        temp_df = pd.read_csv(io.StringIO(region_table_raw))
                        
                        if not temp_df.empty and "Average Size [bp]" in temp_df.columns:
                            val = temp_df["Average Size [bp]"].values[0]
                            # Convert to float first in case there are decimals, then int
                            data["avg_fragment_size"].append(int(float(val)))
                        else:
                            data["avg_fragment_size"].append(None)
                    except Exception as e:
                        logger.warning(f"Error parsing region for {sample_name}: {e}")
                        data["avg_fragment_size"].append(None)

                df = pd.DataFrame(data)
                if df.empty:
                    form.ba_excel.errors.append("No valid data was parsed in the Excel file.")
                    raise exc.BadRequestException("No valid data was parsed in the Excel file.")

                form.workflow.tables["excel_table"] = df
                form.workflow.add_step(form.__class__.__name__)
                next_form = ParseBAExcelFileForm(workflow=form.workflow)
                return next_form.make_response()
            else:
                raise exc.BadRequestException(f"Invalid method: {method}")
        return route






