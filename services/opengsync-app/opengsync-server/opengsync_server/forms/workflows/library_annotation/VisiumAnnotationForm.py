from typing import Optional

import pandas as pd

from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length
from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType
from opengsync_server.forms.MultiStepForm import StepFile

from .... import logger # noqa
from ....tools.spread_sheet_components import TextColumn, DropdownColumn, DuplicateCellValue
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class VisiumAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-visium_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "visium_annotation"

    columns = [
        DropdownColumn("sample_name", "Sample Name", 250, choices=[], required=True),
        TextColumn("image", "Image", 170, max_length=512, required=True),
        TextColumn("slide", "Slide", 170, max_length=32, required=True),
        TextColumn("area", "Area", 170, max_length=32, required=True),
    ]

    instructions = TextAreaField("Instructions where to download images?", validators=[DataRequired(), Length(max=models.Comment.text.type.length)], description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.")  # type: ignore

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.tables["library_table"]["library_type_id"].isin([t.id for t in LibraryType.get_visium_library_types()]).any()

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=VisiumAnnotationForm._workflow_name, step_name=VisiumAnnotationForm._step_name,
            uuid=uuid, previous_form=previous_form, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library_table = self.tables["library_table"]
        self.visium_libraries = self.library_table[self.library_table["library_type_id"].isin([t.id for t in LibraryType.get_visium_library_types()])]
        self.visium_samples = self.visium_libraries["sample_name"].unique().tolist()

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=VisiumAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_visium_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=False, df=self.get_template()
        )

        self.spreadsheet.columns["sample_name"].source = self.visium_samples

    def get_template(self) -> pd.DataFrame:
        data = {
            "sample_name": [],
            "image": [],
            "slide": [],
            "area": [],
        }

        for _, row in self.visium_libraries.iterrows():
            data["sample_name"].append(row["sample_name"])
            data["image"].append(None)
            data["slide"].append(None)
            data["area"].append(None)

        return pd.DataFrame(data)
    
    def fill_previous_form(self, previous_form: StepFile):
        library_properties_table = previous_form.tables["library_properties_table"]
        self.spreadsheet.set_data(library_properties_table)
        self.instructions.data = previous_form.metadata["visium_annotation_instructions"]

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        for i, (idx, row) in enumerate(df.iterrows()):
            if (df["sample_name"] == row["sample_name"]).sum() > 1:
                self.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("'Sample Name' is a duplicate."))
            
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        library_sample_map = self.visium_libraries.set_index("sample_name").to_dict()["library_name"]
        self.df["library_name"] = self.df["sample_name"].map(library_sample_map)
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.add_comment(
            context="visium_annotation",
            text=f"Images: {self.instructions.data}",
            update_data=False
        )
        self.metadata["visium_annotation_instructions"] = self.instructions.data

        if (library_properties_table := self.tables.get("library_properties")) is None:
            library_properties_table = self.df[["library_name", "sample_name"]].copy()

        library_properties_table["image"] = None
        library_properties_table["slide"] = None
        library_properties_table["area"] = None

        for _, row in self.df.iterrows():
            library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "image"] = row["image"]
            library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "slide"] = row["slide"]
            library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "area"] = row["area"]
        
        self.add_table("library_properties_table", library_properties_table)
        self.update_data()

        if FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()
 
