from typing import Optional, Union
from flask import Response
import pandas as pd
from pathlib import Path
from uuid import uuid4

from wtforms import SelectField, FileField

from flask_wtf.file import FileAllowed
from werkzeug.utils import secure_filename

from ... import logger
from ..TableDataForm import TableDataForm

from ..HTMXFlaskForm import HTMXFlaskForm
from .FeatureKitMappingForm import FeatureKitMappingForm


class CMOReferenceInputForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/seq_request/sas-6.html"
    
    _required_columns: list[Union[str, list[str]]] = [
        "Demux Name", "Sample Name",
    ]
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    _mapping: dict[str, str] = {
        "Demux Name": "demux_name",
        "Sample Name": "sample_pool",
        "Kit": "kit",
        "Feature": "feature_name",
        "Sequence": "sequence",
        "Pattern": "pattern",
        "Read": "read",
    }

    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()

        # self.update_data(data)
        return {}

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.file.data is None:
            self.file.errors = ("Upload a file.",)
            return False
        
        filename = f"{Path(self.file.data.filename).stem}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
        filename = secure_filename(filename)
        self.file.data.save("uploads/seq_request/" + filename)
        logger.debug(f"Saved file to uploads/seq_request/{filename}")

        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        try:
            self.cmo_ref = pd.read_csv("uploads/seq_request/" + filename, sep=sep, index_col=False, header=0)
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return False
        
        missing = []
        for col in CMOReferenceInputForm._required_columns:
            if col not in self.cmo_ref.columns:
                missing.append(col)
        
            if len(missing) > 0:
                self.file.errors = (f"Missing column(s): [{', '.join(missing)}]",)
                return False
        
        specified_with_name = (~self.cmo_ref["Kit"].isna() & ~self.cmo_ref["Feature"].isna())
        specified_manually = (~self.cmo_ref["Sequence"].isna() & ~self.cmo_ref["Pattern"].isna() & ~self.cmo_ref["Read"].isna())
        if (~(specified_with_name | specified_manually)).any():
            self.file.errors = ("Columns 'Kit + Feature' or 'Sequence + Pattern Read'  must be specified for all rows.",)
            return False
        
        if self.cmo_ref["Sample Name"].isna().any():
            self.file.errors = ("Column 'Sample Name' must be specified for all rows.",)
            return False
        
        if self.cmo_ref["Demux Name"].isna().any():
            self.file.errors = ("Column 'Demux Name' must be specified for all rows.",)
            return False
        
        data = self.get_data()

        libraries_not_mapped = ~self.cmo_ref["Sample Name"].isin(data["library_table"]["sample_name"])
        if libraries_not_mapped.any():
            self.file.errors = (
                "Values in 'Sample Name'-column in feature reference must be found in 'Sample Name'-column of sample annotation sheet.",
                "Missing values: " + ", ".join(self.cmo_ref["Sample Name"][libraries_not_mapped].unique().tolist())
            )
            return False
        
        return True
    
    def __parse(self) -> dict[str, pd.DataFrame]:
        data = self.get_data()

        self.cmo_ref = self.cmo_ref.rename(columns=CMOReferenceInputForm._mapping)

        data["cmo_table"] = self.cmo_ref

        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)

        try:
            data = self.__parse()
        except pd.errors.ParserError as e:
            self.file.errors = (str(e),)
            return self.make_response(**context)
        
        feature_kit_mapping_form = FeatureKitMappingForm(uuid=self.uuid)
        context = feature_kit_mapping_form.prepare(data) | context
        return feature_kit_mapping_form.make_response(**context)