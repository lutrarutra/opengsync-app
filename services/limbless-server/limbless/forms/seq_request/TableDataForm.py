import os
from typing import Optional
from uuid import uuid4

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

import pandas as pd

from ...tools import io as iot


class TableDataForm(FlaskForm):
    file_uuid = StringField()

    def __init__(self):
        super().__init__()
        if self.file_uuid.data is None:
            self.file_uuid.data = str(uuid4())
        self._data = None

    @property
    def path(self) -> str:
        if self.file_uuid.data is None:
            self.uuid = str(uuid4())
            self.file_uuid.data = self.uuid

        return os.path.join("uploads", "seq_request", self.file_uuid.data + ".tsv")
    
    @property
    def data(self) -> dict[str, pd.DataFrame]:
        return self.get_data()

    def get_data(self) -> dict[str, pd.DataFrame]:
        if self._data is None:
            self._data = iot.parse_config_tables(self.path, sep="\t")

        return self._data
    
    def update_data(self, data: dict[str, pd.DataFrame]):
        self._data = data
        iot.write_config_tables_from_sections(self.path, data, sep="\t", overwrite=True)

    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        ...
    
    def parse(self) -> pd.DataFrame:
        ...