import os
from typing import Optional, Literal
from uuid import uuid4
from pathlib import Path

import pandas as pd
import numpy as np

from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, TextAreaField, StringField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator
from flask import Response
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import logger, tools
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from .FRPAnnotationForm import FRPAnnotationForm
from .SampleAnnotationForm import SampleAnnotationForm


class VisiumAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-9.html"
    _form_label = "visium_annotation_form"

    columns = {
        "library_name": SpreadSheetColumn("A", "library_name", "Library Name", "text", 170, str),
        "image": SpreadSheetColumn("B", "image", "Image", "text", 170, str),
        "slide": SpreadSheetColumn("C", "slide", "Slide", "text", 170, str),
        "area": SpreadSheetColumn("D", "area", "Area", "text", 170, str),
    }
    _mapping: dict[str, str] = dict([(col.name, col.label) for col in columns.values()])
    _required_columns: list[str] = [col.name for col in columns.values()]

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    instructions = TextAreaField("Instructions where to download images?", validators=[DataRequired(), Length(max=models.Comment.text.type.length)], description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.")  # type: ignore
    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, seq_request: models.SeqRequest, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None, input_type: Optional[Literal["spreadsheet", "file"]] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.input_type = input_type
        self.seq_request = seq_request
        self._context["columns"] = VisiumAnnotationForm.columns.values()
        self._context["seq_request"] = seq_request
        self._context["active_tab"] = "help"
        self._context["colors"] = VisiumAnnotationForm.colors
        self.spreadsheet_style = dict()

    def get_template(self) -> pd.DataFrame:
        library_table: pd.DataFrame = self.tables["library_table"]
        df = library_table[library_table["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])][["library_name"]]
        df = df.rename(columns={"library_name": "Library Name"})

        for col in VisiumAnnotationForm.columns.values():
            if col.name not in df.columns:
                df[col.name] = ""

        return df

    def prepare(self):
        self._context["spreadsheet_data"] = self.get_template().replace(np.nan, "").values.tolist()

    def validate(self) -> bool:
        validated = super().validate()
        self.visium_table = None

        if self.input_type is None:
            logger.error("Input type not specified in constructor.")
            raise Exception("Input type not specified in constructor.")
        
        self._context["active_tab"] = self.input_type
        
        if self.input_type == "file":
            if self.file.data is None:
                self.file.errors = ("Upload a file.",)
                return False
            
        if self.input_type == "file":
            filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            filepath = os.path.join("uploads", "seq_request", filename)
            self.file.data.save(filepath)

            sep = "\t" if self.separator.data == "tsv" else ","

            try:
                self.visium_table = pd.read_csv(filepath, sep=sep, index_col=False, header=0)
                validated = True
            except pd.errors.ParserError as e:
                self.file.errors = (str(e),)
                validated = False
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

            if not validated or self.visium_table is None:
                return False
            
            missing = []
            for col in VisiumAnnotationForm._required_columns:
                if col not in self.visium_table.columns:
                    missing.append(col)
            
                if len(missing) > 0:
                    self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                    return False
                
            self.visium_table = self.visium_table.rename(columns=VisiumAnnotationForm._mapping)
            self.visium_table = self.visium_table.replace(r'^\s*$', None, regex=True)
            self.visium_table = self.visium_table.dropna(how="all")

            if len(self.visium_table) == 0:
                self.file.errors = ("File is empty.",)
                return False
            
            if os.path.exists(filepath):
                os.remove(filepath)

        elif self.input_type == "spreadsheet":
            import json
            data = json.loads(self.formdata["spreadsheet"])  # type: ignore
            try:
                self.visium_table = pd.DataFrame(data)
            except ValueError as e:
                self.spreadsheet_dummy.errors = (str(e),)
                return False
            
            columns = list(VisiumAnnotationForm.columns.keys())
            if len(self.visium_table.columns) != len(columns):
                self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(columns)}). Do not insert new columns or rearrange existing columns.",)
                return False
            
            self.visium_table.columns = columns
            self.visium_table = self.visium_table.replace(r'^\s*$', None, regex=True)
            self.visium_table = self.visium_table.dropna(how="all")

            if len(self.visium_table) == 0:
                self.spreadsheet_dummy.errors = ("Please fill-out spreadsheet or upload a file.",)
                return False
            
        if self.visium_table is None:
            return False
        
        library_table: pd.DataFrame = self.tables["library_table"]

        self.file.errors = []
        self.spreadsheet_dummy.errors = []

        self.visium_table["library_name"] = self.visium_table["library_name"].apply(lambda x: tools.make_alpha_numeric(x))

        for i, (idx, row) in enumerate(self.visium_table.iterrows()):
            if pd.isna(row["library_name"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Library Name' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Library Name' is missing.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['missing_value']};"
            elif row["library_name"] not in library_table["library_name"].values:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Library Name' is not found in the library table.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Library Name' is not found in the library table.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['invalid_value']};"
            elif (self.visium_table["library_name"] == row["library_name"]).sum() > 1:
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Library Name' is a duplicate.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Library Name' is a duplicate.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['duplicate_value']};"
            else:
                if (library_table[library_table["library_name"] == row["library_name"]]["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
                    if self.input_type == "file":
                        self.file.errors.append(f"Row {i + 1}: 'Library Name' is not a Spatial Transcriptomic library.")
                    else:
                        self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Library Name' is not a Spatial Transcriptomic library.")
                        self.spreadsheet_style[f"{VisiumAnnotationForm.columns['library_name'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['invalid_value']};"

            if pd.isna(row["image"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Image' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Image' is missing.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['image'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['missing_value']};"
            if pd.isna(row["slide"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Slide' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Slide' is missing.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['slide'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['missing_value']};"
            if pd.isna(row["area"]):
                if self.input_type == "file":
                    self.file.errors.append(f"Row {i + 1}: 'Area' is missing.")
                else:
                    self.spreadsheet_dummy.errors.append(f"Row {i + 1}: 'Area' is missing.")
                    self.spreadsheet_style[f"{VisiumAnnotationForm.columns['area'].column}{i + 1}"] = f"background-color: {VisiumAnnotationForm.colors['missing_value']};"
            
        if self.input_type == "file":
            validated = validated and len(self.file.errors) == 0
        elif self.input_type == "spreadsheet":
            validated = validated and (len(self.spreadsheet_dummy.errors) == 0 and len(self.spreadsheet_style) == 0)
        return validated
    
    def process_request(self) -> Response:
        if not self.validate():
            if self.input_type == "spreadsheet":
                self._context["spreadsheet_style"] = self.spreadsheet_style
                if self.visium_table is not None:
                    self._context["spreadsheet_data"] = self.visium_table.replace(np.nan, "").values.tolist()
                    if self._context["spreadsheet_data"] == []:
                        self.prepare()
            return self.make_response()
        
        if self.visium_table is None:
            logger.error(f"{self.uuid}: Visium table is None.")
            raise Exception("Visium table is None.")
        
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
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()
        
        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()
 
