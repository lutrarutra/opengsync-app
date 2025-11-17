import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from .... import db, logger
from ....tools.spread_sheet_components import CategoricalDropDown, IntegerColumn, MissingCellValue, DuplicateCellValue
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SpreadsheetInput import SpreadsheetInput

class AddKitCombinationsFrom(HTMXFlaskForm):
    _template_path = "workflows/add_kits_to_protocol/add-kit-combinations.html"
    _step_name = "add_kit_combinations"
    _workflow_name = "add_kits_to_protocol"

    def __init__(
        self,
        protocol: models.Protocol,
        formdata: dict | None = None
    ):
        HTMXFlaskForm.__init__(
            self, formdata=formdata,
        )
        self.protocol = protocol
        self._context["protocol"] = protocol
        self._context["workflow"] = AddKitCombinationsFrom._workflow_name
        self.post_url = url_for("add_kits_to_protocol_workflow.add_kit_combinations", protocol_id=protocol.id)

        self.kit_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in db.kits.find(limit=None, sort_by="name")[0]}
        columns: list = [
            CategoricalDropDown("kit_identifier", "Kit", 600, categories=self.kit_mapping, required=True),
            IntegerColumn("combination_num", "Combination", 200, required=False),
        ]

        self.kit_table = db.pd.get_protocol_kits(protocol_id=protocol.id)
        self.spreadsheet = SpreadsheetInput(
            columns=columns,
            csrf_token=self._csrf_token,
            post_url=self.post_url,
            formdata=formdata, df=self.kit_table,
            allow_new_rows=True
        )
        

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        self.df = self.spreadsheet.df

        if self.df["combination_num"].isna().all():
            self.df["combination_num"] = 1

        duplicate = self.df.duplicated(subset=["kit_identifier", "combination_num"], keep=False)

        for idx, row in self.df.iterrows():
            if duplicate.at[idx]:
                self.spreadsheet.add_error(idx, "kit_identifier", DuplicateCellValue("Duplicate kit and combination number."))
            if pd.isna(row["combination_num"]):
                self.spreadsheet.add_error(idx, "combination_num", MissingCellValue("Combination number is required."))
            
        if self.spreadsheet._errors:
            return False
        return True


    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.protocol.kit_links = []
        
        for _, row in self.df.iterrows():
            kit = db.kits[row["kit_identifier"]]
            
            self.protocol.kit_links.append(
                models.links.ProtocolKitLink(
                    protocol_id=self.protocol.id,
                    kit_id=kit.id,
                    combination_num=int(row["combination_num"]),
                )
            )

        db.protocols.update(self.protocol)
        
        flash("Successfully added kits to protocol.", "success")
        return make_response(redirect=url_for("protocols_page.protocol", protocol_id=self.protocol.id))
