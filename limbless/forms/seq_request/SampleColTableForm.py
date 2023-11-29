from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import tools


# Column selection form for sample table
class SampleColSelectForm(FlaskForm):
    required_fields = [
        ("", "-"),
        ("sample_name", "Sample Name"),
    ]
    optional_fields = [
        ("organism", "Organism"),
        ("library_type", "Library Type"),
        ("adapter", "Adapter"),
        ("index_1", "Index 1 (i7)"),
        ("index_2", "Index 2 (i5)"),
        ("index_3", "Index 3"),
        ("index_4", "Index 4"),
        ("project", "Project"),
        ("pool", "Pool"),
    ]
    _similars = {
        "index1(i7)": "index_1",
        "index1": "index_1",
        "i7": "index_1",
        "barcode": "index_1",
        "index2(i5)": "index_2",
        "index2": "index_2",
        "i5": "index_2",
        "index3": "index_3",
        "index4": "index_4",
        "adapter": "adapter",
        "organism": "organism",
        "samplename": "sample_name",
        "librarytype": "library_type",
        "pool": "pool",
        "librarypool": "pool"
    }
    select_field = SelectField(
        choices=required_fields + optional_fields,
    )


# 2. This form is used to select what each column in the sample table represents
class SampleColTableForm(FlaskForm):
    input_fields = FieldList(FormField(SampleColSelectForm))
    data = TextAreaField()

    def prepare(self, df: pd.DataFrame):
        required_fields = SampleColSelectForm.required_fields
        optional_fields = SampleColSelectForm.optional_fields
        
        self.data.data = df.to_csv(sep="\t", index=False, header=True)
        columns = df.columns.tolist()
        refs = [key for key, _ in required_fields if key]
        opts = [key for key, _ in optional_fields]
        matches = tools.connect_similar_strings(required_fields + optional_fields, columns, similars=SampleColSelectForm._similars)

        for i, col in enumerate(columns):
            select_form = SampleColSelectForm()
            select_form.select_field.label.text = col
            self.input_fields.append_entry(select_form)
            self.input_fields.entries[i].select_field.label.text = col
            if col in matches.keys():
                self.input_fields.entries[i].select_field.data = matches[col]
            
        return {
            "columns": columns,
            "required_fields": refs,
            "optional_fields": opts,
            "matches": matches,
        }
    
    def parse(self) -> pd.DataFrame:
        df = pd.read_csv(StringIO(self.data.data), sep="\t", index_col=False, header=0)
        selected_features = []
        features = SampleColSelectForm.required_fields + SampleColSelectForm.optional_fields
        features = [key for key, _ in features if key]
        for feature in features:
            df[feature] = None

        for i, entry in enumerate(self.input_fields.entries):
            val = entry.select_field.data.strip()
            if not val:
                continue
            selected_features.append(val)
            df[val] = df[df.columns[i]]
        
        df = df[features]
        return df