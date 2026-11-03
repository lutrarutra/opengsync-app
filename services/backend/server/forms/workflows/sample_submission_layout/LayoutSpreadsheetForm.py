from collections import defaultdict
from typing import cast

import pandas as pd
from fastapi import Depends, Response
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, queries as Q, categories as C, SyncSession

from ....core import responses
from ....utils import parsing
from ....components import inputs
from ....components.tables import DBObjectColumn, TextColumn, StaticSpreadsheet, InvalidCellValue, DuplicateCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .SampleSubmissionLayoutWorkflow import SampleSubmissionLayoutWorkflow, SampleSubmissionLayoutWorkflowStep, KIND_LABELS

Layout = models.SampleSubmissionLayout


class LayoutSpreadsheetForm(SampleSubmissionLayoutWorkflowStep):
    template_path = "workflows/sample_submission_layout/layout_spreadsheet.html"
    # Titles are set per container type and kind in __init__
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            # Categories are the request's samples/libraries/pools, set in __init__
            DBObjectColumn(("item_id", "name"), "Item", 300, categories={}, required=True, unique=True, read_only=True),
            TextColumn("set_name", "Set", 200, max_length=Layout.MAX_SET_NAME_LENGTH),
            TextColumn("position", "Position", 150, required=True, max_length=Layout.MAX_POSITION_LENGTH),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: SampleSubmissionLayoutWorkflow, session: SyncSession) -> None:
        super().__init__(workflow)
        self.session = session
        self.layout_type = workflow.layout_type
        self.kind = workflow.kind
        self.kind_label = KIND_LABELS[self.kind]
        self.is_plate = self.layout_type == C.SubmissionLayoutType.PLATE
        layout_table = self.workflow.tables["layout_table"]
        item_column = cast(DBObjectColumn, self.spreadsheet.columns["Item"])
        item_column.name = self.kind_label
        item_column.set_categories({
            int(item_id): f"{name} [{item_id}]" for item_id, name in zip(layout_table["item_id"], layout_table["name"])
        })
        self.spreadsheet.columns["set_name"].name = "Plate" if self.is_plate else "Tube Set"
        self.spreadsheet.columns["position"].name = "Well" if self.is_plate else "Tube Label"
        self.spreadsheet.configure(
            csrf_token=self.csrf_token_value,
            post_url=self.post_url,
            df=layout_table,
        )

    def prepare_context(self) -> None:
        if self.is_plate:
            example = pd.DataFrame({
                "name": [f"{self.kind_label.lower()}_{i}" for i in range(1, 6)],
                "set_name": ["", "", "", "plate_2", "plate_2"],
                "position": ["A1", "B1", "C1", "A1", "B1"],
            })
        else:
            example = pd.DataFrame({
                "name": [f"{self.kind_label.lower()}_{i}" for i in range(1, 6)],
                "set_name": ["", "", "", "box_2", "box_2"],
                "position": ["1", "2", "3", "1", "2"],
            })
        self._context["example_spreadsheet"] = StaticSpreadsheet(
            example,
            columns=[
                TextColumn("name", self.kind_label, 300),
                TextColumn("set_name", self.spreadsheet.columns["set_name"].name, 200),
                TextColumn("position", self.spreadsheet.columns["position"].name, 150),
            ],
            id="sample-submission-layout-example",
        )

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "LayoutSpreadsheetForm" = Depends(LayoutSpreadsheetForm.Init()),
        ) -> Response:
            form.spreadsheet.set_data(form.workflow.tables["layout_table"])
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LayoutSpreadsheetForm" = Depends(LayoutSpreadsheetForm.Validate()),
        ) -> Response:
            class RowSchema(BaseModel):
                item_id: int
                set_name: str | None = None
                position: str

            df = form.spreadsheet.data
            expected_ids = set(form.workflow.tables["layout_table"]["item_id"].tolist())
            if (submitted_ids := set(df["item_id"].tolist())) != expected_ids:
                form.spreadsheet.add_general_error(
                    f"The sheet must list every {form.kind_label.lower()} of the request once. Please start again."
                    if submitted_ids - expected_ids else
                    f"Every {form.kind_label.lower()} of the request needs a {form.spreadsheet.columns['position'].name.lower()}."
                )
                form.assert_valid()

            rows_by_idx: dict[int, tuple[int, str, str]] = {}
            # Positions compare case-insensitively: 'a1'/'A1' or 'Tube1'/'tube1' are the same tube or well
            occupied: dict[tuple[str, str], list[int]] = defaultdict(list)
            for idx, row in parsing.safe_iter(df, RowSchema, index_type=int):
                set_name = (row.set_name or "").strip()
                position = row.position.strip()
                if form.is_plate:
                    try:
                        position = Layout.normalize_well(position)
                    except ValueError:
                        form.spreadsheet.add_error(idx, "position", InvalidCellValue(
                            f"Invalid well '{row.position}', must be A1-H12."
                        ))
                        continue
                occupied[(set_name.lower(), position.lower())].append(idx)
                rows_by_idx[idx] = (row.item_id, set_name, position)

            container = "plate" if form.is_plate else "tube set"
            for indices in occupied.values():
                if len(indices) < 2:
                    continue
                set_name = rows_by_idx[indices[0]][1]
                where = f"{container} '{set_name}'" if set_name else f"the default {container}"
                for idx in indices:
                    form.spreadsheet.add_error(idx, ["set_name", "position"], DuplicateCellValue(
                        f"'{df.at[idx, 'position']}' is used for {len(indices)} {form.kind_label.lower()}s in {where} (rows {', '.join(str(i + 1) for i in indices)})."
                    ))
            form.assert_valid()

            seq_request = form.session.get_one(
                Q.seq_request.select(id=form.workflow.seq_request_id).options(orm.selectinload(models.SeqRequest.submission_layout))
            )
            # Delete the old positions first: the new ones may reuse them (unique per request)
            seq_request.submission_layout.clear()
            form.session.flush()
            seq_request.submission_layout_type = form.layout_type
            for item_id, set_name, position in rows_by_idx.values():
                seq_request.submission_layout.append(Layout(**{f"{form.kind}_id": item_id}, set_name=set_name, position=position))

            form.workflow.complete()
            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=form.workflow.seq_request_id),
                flash=responses.flash("Submission layout saved!", "success"),
            )
        return route
