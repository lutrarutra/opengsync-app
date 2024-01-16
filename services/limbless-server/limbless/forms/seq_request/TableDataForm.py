from typing import Optional
from io import StringIO

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

import pandas as pd


class TableDataForm(FlaskForm):
    raw_data = TextAreaField(validators=[DataRequired()])

    def get_df(self) -> pd.DataFrame:
        return pd.read_csv(StringIO(self.raw_data.data), sep="\t", index_col=False, header=0)
    
    def set_df(self, df: pd.DataFrame):
        self.raw_data.data = df.to_csv(sep="\t", index=False, header=True)

    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        ...
    
    def parse(self) -> pd.DataFrame:
        ...