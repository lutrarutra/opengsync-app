import pandas as pd
import os
import openpyxl
from openpyxl.utils import get_column_letter

from flask import Response, url_for, flash
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, FieldList, FormField

from opengsync_db import models

from .... import db, logger  # noqa
from ....tools import utils
from ....core import runtime
from ...MultiStepForm import MultiStepForm
from .LibraryProtocolSelectForm import LibraryProtocolSelectForm

class SubForm(FlaskForm):
    kit_combination = StringField("Kit Combination")
    protocol = SelectField("Protocol", coerce=int)

class ProtocolMappingForm(MultiStepForm):
    _template_path = "workflows/select_library_protocols/map_protocols.html"
    _workflow_name = "select_library_protocols"
    _step_name = "protocol_mapping_form"

    subforms = FieldList(FormField(SubForm))

    def __init__(self, lab_prep: models.LabPrep, uuid: str | None, formdata: dict | None = None):
        super().__init__(formdata=formdata, workflow=ProtocolMappingForm._workflow_name, step_name=ProtocolMappingForm._step_name, uuid=uuid, step_args={})
        self.lab_prep = lab_prep
        self._context["lab_prep"] = lab_prep

        self.post_url = url_for("select_library_protocols_workflow.map_protocols", uuid=self.uuid, lab_prep_id=lab_prep.id)
        
        protocols = db.pd.get_protocol_kits()
        self.protocols = (
            protocols.groupby(['protocol_id', 'combination_num'])
            .agg(identifiers=('kit_identifier', lambda x: ';'.join(sorted(x))))
            .reset_index()
        )

        if self.lab_prep.prep_file is None:
            raise ValueError("Lab prep has no prep file associated with it.")
        
        df = pd.read_excel(os.path.join(runtime.app.media_folder, self.lab_prep.prep_file.path), sheet_name="prep_table")
        if "library_kits" not in df.columns:
            df["library_kits"] = None
        self.library_table = df[["library_id", "library_name", "library_kits"]].copy()
        self.library_table = self.library_table[self.library_table["library_id"].notna()]
        self.library_table["library_id"] = self.library_table["library_id"].astype(pd.Int64Dtype())
        
        self.kit_combinations = set()
        self.library_table["combination"] = None
        self.library_table["protocol_id"] = None
        for library in self.lab_prep.libraries:
            self.library_table.loc[self.library_table["library_id"] == library.id, "protocol_id"] = library.protocol_id
        
        for idx, row in self.library_table.iterrows():
            if pd.isna(row["library_kits"]):
                continue
            
            combination = ";".join(sorted([kit.strip().removeprefix("#") for kit in str(row["library_kits"]).strip().split(";")]))
            self.library_table.at[idx, "combination"] = combination  # type: ignore
            self.kit_combinations.add(combination)

        self.kit_combinations = sorted(list(self.kit_combinations))
        protocols = [(p.id, p.name) for p in db.protocols.find(limit=None, sort_by="name")[0]]
        protocol_mapping = dict(protocols)
    
        for i, combination in enumerate(self.kit_combinations):
            if i > len(self.subforms) - 1:
                self.subforms.append_entry()

            sub_form: SubForm = self.subforms[i]  # type: ignore
            sub_form.kit_combination.data = combination
            choices = [(-1, "Unknown")]

            for _, row in self.protocols[self.protocols["identifiers"] == combination].iterrows():
                protocol = db.protocols[int(row["protocol_id"])]
                protocol_id = row["protocol_id"]
                choices.append((protocol_id, f"{protocol.name}"))

            if len(choices) > 1:
                sub_form.protocol.choices = choices  # type: ignore
            else:
                sub_form.protocol.choices = [(-1, "Unknown")] + protocols  # type: ignore

            if len(combination_protocol_ids := self.library_table[self.library_table["combination"] == combination]["protocol_id"].unique().tolist()) == 1:
                if pd.notna(protocol_id := combination_protocol_ids[0]):
                    if protocol_id not in dict(choices):
                        choices.append((protocol_id, protocol_mapping[protocol_id]))

            if not formdata:
                sub_form.protocol.data = choices[-1][0]  # type: ignore
            if len(choices) > 2:
                sub_form.protocol.errors = ("Multiple protocols found for this kit combination. Please select the correct one.",)
            if len(choices) == 0:
                sub_form.protocol.errors = ("No protocols found for this kit combination.",)

    def validate(self) -> bool:
        if not super().validate():
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        for sub_form in self.subforms:
            if sub_form.protocol.data == -1:
                continue
            self.library_table.loc[
                self.library_table["combination"] == sub_form.kit_combination.data, "protocol_id"
            ] = sub_form.protocol.data

        self.add_table("library_table", self.library_table)
        self.update_data()

        logger.debug(self.library_table)

        next_form = LibraryProtocolSelectForm(lab_prep=self.lab_prep, uuid=self.uuid, formdata=None)
        return next_form.make_response()
        
