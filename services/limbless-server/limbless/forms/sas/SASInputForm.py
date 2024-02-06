import os
from uuid import uuid4
from pathlib import Path
from typing import Optional

import pandas as pd

from flask_wtf.file import FileField, FileAllowed
from wtforms import SelectField
from flask import Response
from werkzeug.utils import secure_filename

from ..HTMXFlaskForm import HTMXFlaskForm
from .ProjectMappingForm import ProjectMappingForm


class SASInputForm(HTMXFlaskForm):
    _template_path = "components/popups/seq_request/sas-1.html"
    _form_label = "sas_input_form"

    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    separator = SelectField(choices=_allowed_extensions, default="tsv")
    submission_type = SelectField(choices=[("", ""), ("pooled", "Pooled Libraries"), ("raw", "Raw Samples")], description="Select 'Pooled Libraries' if you are planning to submit pooled libraries, or 'Raw Samples' if you are planning to submit samples for library preparation.")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    _feature_mapping_premade = {
        "Sample Name": "sample_name",
        "Library Name": "library_name",
        "Organism": "organism",
        "Project": "project",
        "Library Type": "library_type",
        "Pool": "pool",
        "Index Kit": "index_kit",
        "Adapter": "adapter",
        "Index 1 (i7)": "index_1",
        "Index 2 (i5)": "index_2",
        "Index 3": "index_3",
        "Index 4": "index_4",
        "Library Volume [uL]": "library_volume",
        "Library DNA Concentration [nM]": "library_concentration",
        "Library Total Size [bp]": "library_total_size",
    }

    _feature_mapping_raw = {
        "Sample Name": "sample_name",
        "Library Name": "library_name",
        "Organism": "organism",
        "Project": "project",
        "Library Type": "library_type",
    }

    def __init__(self, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("uploads", "seq_request")
        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self) -> bool:
        validated = super().validate()

        if self.file.data is None:
            self.file.errors = ("Please upload a file.",)
            validated = False
        
        if self.submission_type.data == "pooled":
            feature_mapping = SASInputForm._feature_mapping_premade
        elif self.submission_type.data == "raw":
            feature_mapping = SASInputForm._feature_mapping_raw
        else:
            self.submission_type.errors = ("Please select a submission type.",)
            return False

        if validated is False:
            return False
        
        try:
            self.df = self.__parse()

        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False

        missing_cols = [col for col in feature_mapping.keys() if col not in self.df.columns]
        if len(missing_cols) > 0:
            self.file.errors = (str(f"Uploaded table is missing column(s): [{', '.join(missing_cols)}]"),)
            return False

        self.df = self.df.rename(columns=feature_mapping)
        self.df = self.df[feature_mapping.values()]

        return True
    
    def __parse(self) -> pd.DataFrame:
        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save(os.path.join(self.upload_path, filename))

        df = pd.read_csv(os.path.join(self.upload_path, filename), sep=sep, index_col=False, header=0)
        
        return df
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user_id: int = context["user_id"]
        
        data = {"library_table": self.df}

        project_mapping_form = ProjectMappingForm()
        context = project_mapping_form.prepare(user_id, data) | context
                
        return project_mapping_form.make_response(**context)
        
