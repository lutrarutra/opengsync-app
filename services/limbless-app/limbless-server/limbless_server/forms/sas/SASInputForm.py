import os
from typing import Optional, Literal

import pandas as pd

from flask import Response

from limbless_db.core.categories import LibraryType, Organism

from ..HTMXFlaskForm import HTMXFlaskForm
from .ProjectMappingForm import ProjectMappingForm


class SASInputForm(HTMXFlaskForm):
    _template_path = "components/popups/seq_request/sas-1.html"
    _form_label = "sas_input_form"

    # _allowed_extensions: list[tuple[str, str]] = [
    #     ("tsv", "Tab-separated"),
    #     ("csv", "Comma-separated")
    # ]
    # separator = SelectField(choices=_allowed_extensions, default="tsv", coerce=str)
    # file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

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

    def __init__(self, type: Literal["raw", "pooled"], formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("uploads", "seq_request")
        self.type = type
        if not os.path.exists(self.upload_path):
            os.makedirs(self.upload_path)

    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False

        return True
    
    def get_columns(self):
        if self.type == "raw":
            return [
                {"type": "text", "title": "Sample Name", "width": 120},
                {"type": "text", "title": "Library Name", "width": 120},
                {"type": "dropdown", "title": "Organism", "width": 100, "source": Organism.names()},
                {"type": "text", "title": "Project", "width": 100},
                {"type": "dropdown", "title": "Library Type", "width": 100, "source": LibraryType.descriptions()},
            ]
        elif self.type == "pooled":
            return [
                {"type": "text", "title": "Sample Name", "width": 120},
                {"type": "text", "title": "Library Name", "width": 120},
                {"type": "dropdown", "title": "Organism", "width": 100, "source": Organism.names()},
                {"type": "text", "title": "Project", "width": 100},
                {"type": "dropdown", "title": "Library Type", "width": 100, "source": LibraryType.descriptions()},
                {"type": "text", "title": "Pool", "width": 100},
                {"type": "text", "title": "Index Kit", "width": 100},
                {"type": "text", "title": "Adapter", "width": 100},
                {"type": "text", "title": "Index 1 (i7)", "width": 100},
                {"type": "text", "title": "Index 2 (i5)", "width": 100},
                {"type": "text", "title": "Index 3", "width": 80},
                {"type": "text", "title": "Index 4", "width": 80},
                {"type": "numeric", "title": "Library Volume [uL]", "width": 120},
                {"type": "numeric", "title": "Library DNA Concentration [nM]", "width": 120},
                {"type": "numeric", "title": "Library Total Size [bp]", "width": 120},
            ]
        
        raise ValueError("Invalid type")
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        user_id: int = context["user_id"]

        project_mapping_form = ProjectMappingForm()
        context = project_mapping_form.prepare(user_id, data) | context
                
        return project_mapping_form.make_response(**context)
        
