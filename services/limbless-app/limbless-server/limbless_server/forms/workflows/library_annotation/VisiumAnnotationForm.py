from typing import Optional

import pandas as pd

from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length
from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger # noqa
from ....tools import SpreadSheetColumn
from ...SpreadsheetInput import SpreadsheetInput
from ...MultiStepForm import MultiStepForm
from .FRPAnnotationForm import FRPAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm


class VisiumAnnotationForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-9.html"
    _workflow_name = "library_annotation"
    _step_name = "visium_annotation"

    columns = {
        "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
        "image": SpreadSheetColumn("B", "image", "Image", "text", 170, str),
        "slide": SpreadSheetColumn("C", "slide", "Slide", "text", 170, str),
        "area": SpreadSheetColumn("D", "area", "Area", "text", 170, str),
    }

    instructions = TextAreaField("Instructions where to download images?", validators=[DataRequired(), Length(max=models.Comment.text.type.length)], description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.")  # type: ignore

    def __init__(self, seq_request: models.SeqRequest, uuid: str, previous_form: Optional[MultiStepForm] = None, formdata: dict = {}):
        MultiStepForm.__init__(
            self, workflow=VisiumAnnotationForm._workflow_name, step_name=VisiumAnnotationForm._step_name,
            uuid=uuid, previous_form=previous_form, formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=VisiumAnnotationForm.columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_visium_reference', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def get_template(self) -> pd.DataFrame:
        library_table: pd.DataFrame = self.tables["library_table"]
        df = library_table[library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])][["library_name"]]
        df = df.rename(columns={"library_name": "Library Name"})

        for col in VisiumAnnotationForm.columns.values():
            if col.name not in df.columns:
                df[col.name] = ""

        return df

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
        library_table: pd.DataFrame = self.tables["library_table"]

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["library_name"]):
                self.spreadsheet.add_error(i + 1, "library_name", "'Library Name' is missing.", "missing_value")

            elif row["library_name"] not in library_table["library_name"].values:
                self.spreadsheet.add_error(i + 1, "library_name", "'Library Name' is not found in the library table.", "invalid_value")
            elif (df["library_name"] == row["library_name"]).sum() > 1:
                self.spreadsheet.add_error(i + 1, "library_name", "'Library Name' is a duplicate.", "duplicate_value")
            else:
                if (library_table[library_table["library_name"] == row["library_name"]]["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
                    self.spreadsheet.add_error(i + 1, "library_name", "'Library Name' is not a Spatial Transcriptomic library.", "invalid_value")

            if pd.isna(row["image"]):
                self.spreadsheet.add_error(i + 1, "image", "'Image' is missing.", "missing_value")

            if pd.isna(row["slide"]):
                self.spreadsheet.add_error(i + 1, "slide", "'Slide' is missing.", "missing_value")

            if pd.isna(row["area"]):
                self.spreadsheet.add_error(i + 1, "area", "'Area' is missing.", "missing_value")
            
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.visium_table = df
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
        
        self.add_table("visium_table", self.visium_table)
        self.add_table("comment_table", comment_table)
        self.update_data()

        if LibraryType.TENX_SC_GEX_FLEX.id in library_table["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return frp_annotation_form.make_response()
        
        sample_annotation_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()
 
