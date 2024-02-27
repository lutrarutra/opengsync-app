import os
from typing import Optional
from uuid import uuid4
import pandas as pd
from pathlib import Path

from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField, TextAreaField
from wtforms.validators import DataRequired, Length
from flask import Response
from werkzeug.utils import secure_filename

from limbless_db import models
from limbless_db.core.categories import LibraryType
from ..HTMXFlaskForm import HTMXFlaskForm
from ..TableDataForm import TableDataForm
from .PoolMappingForm import PoolMappingForm
from .BarcodeCheckForm import BarcodeCheckForm


class VisiumAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/seq_request/sas-8.html"
    _form_label = "visium_annotation_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    instructions = TextAreaField("Instructions where to download images?", validators=[DataRequired(), Length(max=models.Comment.text.type.length)], description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.")  # type: ignore

    _visium_annotation_mapping = {
        "Library Name": "library_name",
        "Image": "image",
        "Slide": "slide",
        "Area": "area",
    }

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if self.file.data is None:
            self.file.errors = ("Please upload a file.",)
            return False

        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        filepath = os.path.join("uploads", "seq_request", filename)
        self.file.data.save(filepath)

        sep = "\t" if self.separator.data == "tsv" else ","

        try:
            self.visium_ref = pd.read_csv(filepath, sep=sep)
            validated = True
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            validated = False
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
            if not validated:
                return False
            
        missing_columns = ~self.visium_ref.columns.isin(self._visium_annotation_mapping.keys())
        if missing_columns.any():
            self.file.errors = (f"Missing required columns: {', '.join(self.visium_ref.columns[missing_columns])}.",)
            return False
        
        self.visium_ref = self.visium_ref.rename(columns=self._visium_annotation_mapping)
        self.visium_ref = self.visium_ref[list(self._visium_annotation_mapping.values())]

        duplicate_entries = self.visium_ref.duplicated(subset=["library_name"])
        if duplicate_entries.any():
            self.file.errors = (f"Duplicate library entries: {', '.join(self.visium_ref[duplicate_entries]['library_name'])}",)
            return False

        if self.visium_ref.isna().any().any():
            self.file.errors = ("Missing values in annotation table.",)
            return False
        
        library_table = self.get_data()["library_table"]
        _df = library_table[library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id]
        is_annotated = _df["library_name"].isin(self.visium_ref["library_name"])
        if not is_annotated.all():
            self.file.errors = (f"Spatial Transcriptomic annotations missing from following libraries: {', '.join(_df.loc[~is_annotated, 'library_name'])}",)
            return False
        
        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        data = self.get_data()
        data["visium_ref"] = self.visium_ref
        if "comments" not in data:
            data["comments"] = pd.DataFrame(columns=["context", "text"])

        data["comments"] = pd.concat([
            data["comments"],
            pd.DataFrame({
                "context": ["visium_instructions"],
                "text": [self.instructions.data]
            })
        ])

        self.update_data(data)

        if "pool" in data["library_table"].columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)
        
        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data)
        return barcode_check_form.make_response(**context)



        

        
