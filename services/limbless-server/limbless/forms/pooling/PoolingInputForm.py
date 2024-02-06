import os
from uuid import uuid4
from typing import Optional
from pathlib import Path

import pandas as pd

from flask import Response
from wtforms import SelectField
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename

from ... import logger
from ..TableDataForm import TableDataForm
from ..HTMXFlaskForm import HTMXFlaskForm
from .IndexKitMappingForm import IndexKitMappingForm


class PoolingInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/pooling/pooling-1.html"
    _form_label = "pooling_input_form"

    _required_columns: list[str] = [
        "id", "library_name", "library_type", "index_1", "adapter", "pool", "index_kit"
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]

    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def __init__(self, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("uploads", "pooling")
        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.file.data is None:
            self.file.errors = ("Please upload a file.",)
            return False
        
        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save("uploads/" + filename)

        sep = "\t" if self.separator.data == "tsv" else ","
        
        try:
            self.df = pd.read_csv("uploads/" + filename, sep=sep, index_col=False, header=0)
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False

        missing = []
        for col in PoolingInputForm._required_columns:
            if col not in self.df.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False

        return True
    
    def process_request(self, **context) -> Response:
        if self.validate() is False:
            return self.make_response(**context)
        
        data = {"pooling_table": self.df}
        index_kit_mapping_form = IndexKitMappingForm(uuid=None)
        context = index_kit_mapping_form.prepare(data) | context

        return index_kit_mapping_form.make_response(**context)