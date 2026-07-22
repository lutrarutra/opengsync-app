import json

import pandas as pd
from fastapi import Depends, Response

from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .CompleteBAReport import CompleteBAReport
from .BAReportWorkflow import BAReportWorkflowStep, BAReportWorkflow

class ParseBAExcelFileForm(BAReportWorkflowStep):
    template_path = "workflows/ba_report/bar-2.html"

    left_order = inputs.string.StringInputField("Left Order", required=True)
    right_order = inputs.string.StringInputField("Right Order", required=True)

    def __init__(self, workflow: "BAReportWorkflow") -> None:
        super().__init__(workflow=workflow)
        self.excel_table = workflow.tables["excel_table"]
        self.sample_table = workflow.tables["sample_table"]

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ParseBAExcelFileForm" = Depends(ParseBAExcelFileForm.Validate()),
        ) -> Response:
            samples_order = [int(s) for s in json.loads(form.left_order.data)]
            excel_order = [
                (str(s["name"]), (int(s["value"])) if s.get("value") else None)
                for s in json.loads(form.right_order.data)
            ]

            data = {
                "id": [],
                "name": [],
                "type": [],
                "avg_fragment_size": [],
                "well_name": [],
            }

            for i in range(min(len(samples_order), len(excel_order))):
                sample_idx = samples_order[i]
                excel_name, excel_value = excel_order[i]

                data["id"].append(form.sample_table.at[sample_idx, "id"])
                data["name"].append(form.sample_table.at[sample_idx, "name"])
                data["type"].append(form.sample_table.at[sample_idx, "type"])
                data["avg_fragment_size"].append(excel_value)
                data["well_name"].append(excel_name)

            ba_table = pd.DataFrame(data)
            form.workflow.tables["ba_table"] = ba_table
            form.workflow.add_step(form.__class__.__name__)
            next_step = CompleteBAReport(workflow=form.workflow)
            return next_step.make_response()
        return route