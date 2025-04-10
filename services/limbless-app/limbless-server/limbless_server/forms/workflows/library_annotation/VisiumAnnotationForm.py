from typing import Optional

import pandas as pd

from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length
from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger # noqa
from ....tools import SpreadSheetColumn, StaticSpreadSheet
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class VisiumAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-visium_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "visium_annotation"

    columns = [
        SpreadSheetColumn("sample_name", "Sample Name", "text", 170, str),
        SpreadSheetColumn("image", "Image", "text", 170, str),
        SpreadSheetColumn("slide", "Slide", "text", 170, str),
        SpreadSheetColumn("area", "Area", "text", 170, str),
    ]

    instructions = TextAreaField("Instructions where to download images?", validators=[DataRequired(), Length(max=models.Comment.text.type.length)], description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.")  # type: ignore

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=VisiumAnnotationForm._workflow_name, step_name=VisiumAnnotationForm._step_name,
            uuid=uuid, previous_form=previous_form, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.library_table = self.tables["library_table"]
        self.visium_libraries = self.library_table[self.library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])]

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=VisiumAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_visium_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=False, df=self.get_template()
        )

        self._context["available_samples"] = StaticSpreadSheet(
            df=self.visium_libraries,
            columns=[SpreadSheetColumn("sample_name", "Sample Name", "text", 500, str)],
        )

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

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(idx, "sample_name", "'Sample Name' is missing.", "missing_value")

            elif row["sample_name"] not in self.library_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "sample_name", "'Sample Name' is not found in the library table.", "invalid_value")
            elif (df["sample_name"] == row["sample_name"]).sum() > 1:
                self.spreadsheet.add_error(idx, "sample_name", "'Sample Name' is a duplicate.", "duplicate_value")
            else:
                if (row["sample_name"] not in self.visium_libraries["sample_name"].values):
                    self.spreadsheet.add_error(idx, "sample_name", f"Sample, '{row['sample_name']}', is not a Spatial Transcriptomic library.", "invalid_value")

            if pd.isna(row["image"]):
                self.spreadsheet.add_error(idx, "image", "'Image' is missing.", "missing_value")

            if pd.isna(row["slide"]):
                self.spreadsheet.add_error(idx, "slide", "'Slide' is missing.", "missing_value")

            if pd.isna(row["area"]):
                self.spreadsheet.add_error(idx, "area", "'Area' is missing.", "missing_value")
            
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        library_sample_map = self.visium_libraries.set_index("sample_name").to_dict()["library_name"]
        self.df["library_name"] = self.df["sample_name"].map(library_sample_map)
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        library_table = self.tables["library_table"]

        if (comment_table := self.tables.get("comment_table")) is None:  # type: ignore
            comment_table = pd.DataFrame({
                "context": ["visium_instructions"],
                "text": [self.instructions.data]
            })
        else:
            comment_table = pd.concat([
                comment_table,
                pd.DataFrame({
                    "context": ["visium_instructions"],
                    "text": [self.instructions.data]
                })
            ])
        
        self.add_table("visium_table", self.df)
        self.add_table("comment_table", comment_table)
        self.update_data()

        if LibraryType.TENX_SC_GEX_FLEX.id in library_table["library_type_id"].values:
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()
 
