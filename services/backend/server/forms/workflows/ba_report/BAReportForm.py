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
from .CompleteBAReport import save_report


class SubForm(SubHTMXForm):
    id_ = inputs.numeric.IntInputField("ID", required=True, read_only=True)
    name = inputs.string.StringInputField("Name", required=True, read_only=True)
    type = inputs.string.StringInputField("Type", required=True, read_only=True)
    avg_fragment_size = inputs.numeric.IntInputField("Avg. Fragment Size", unit="bp.", required=False, ge=1)

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

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "BAReportForm" = Depends(BAReportForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BAReportForm" = Depends(BAReportForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            method: Literal["excel", "manual"] = Query(..., description="The method used to submit the form. Can be 'excel' or 'manual'."),
            current_user_id: int = Depends(dependencies.require_user_id),
        ) -> Response:
            form.active_tab = method
            if method == "manual":
                if not form.pdf.data:
                    form.pdf.errors.append("Please upload a PDF file.")
                    raise exc.FormValidationException(form)
                
                return save_report(
                    form, session, current_user_id,
                    (form.sample_forms, form.library_forms, form.pool_forms, form.lane_forms), form.pdf,
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
                            size = int(float(val))
                            data["avg_fragment_size"].append(size if size > 0 else None)
                        else:
                            data["avg_fragment_size"].append(None)
                    except Exception as e:
                        logger.warning(f"Error parsing region for {sample_name}: {e}")
                        data["avg_fragment_size"].append(None)

                df = pd.DataFrame(data)
                if df.empty:
                    form.ba_excel.errors.append("No valid data was parsed in the Excel file.")
                    raise exc.FormValidationException(form)

                form.workflow.tables["excel_table"] = df
                return form.workflow.get_next_step(form, ParseBAExcelFileForm).make_response()
            else:
                raise exc.BadRequestException(f"Invalid method: {method}")
        return route






