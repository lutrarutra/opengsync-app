import json

import pandas as pd
from fastapi import Depends, Response

from ....core import exceptions as exc
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
            try:
                samples_order = [int(s) for s in json.loads(form.left_order.data)]
                excel_order = [
                    (str(s["name"]), (int(float(s["value"]))) if s.get("value") else None)
                    for s in json.loads(form.right_order.data)
                ]
                if any(i not in form.sample_table.index for i in samples_order):
                    raise ValueError("unknown sample")
            except (ValueError, TypeError, KeyError, AttributeError):
                form.add_general_error("Invalid sample/well assignment. Please assign the wells again.")
                raise exc.FormValidationException(form)

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
                # A size must be positive (molarity divides by it); like the export parser, ≤ 0 means unknown
                data["avg_fragment_size"].append(excel_value if excel_value is not None and excel_value > 0 else None)
                data["well_name"].append(excel_name)

            ba_table = pd.DataFrame(data)
            form.workflow.tables["ba_table"] = ba_table
            form.workflow.add_step(form.__class__.__name__)
            next_step = CompleteBAReport(workflow=form.workflow)
            form.workflow.add_step(next_step.__class__.__name__)
            return next_step.make_response()
        return route