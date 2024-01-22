from typing import Optional
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import tools, logger
from .TableDataForm import TableDataForm


# Column selection form for sample table
class SampleColSelectForm(FlaskForm):
    required_fields = [
        ("", "-"),
        ("sample_name", "Sample/Library Name"),
    ]
    optional_fields = [
        ("organism", "Organism"),
        ("library_type", "Library Type"),
        ("adapter", "Adapter"),
        ("index_kit", "Index Kit"),
        ("index_1", "Index 1 (i7)"),
        ("index_2", "Index 2 (i5)"),
        ("index_3", "Index 3"),
        ("index_4", "Index 4"),
        ("project", "Project"),
        ("pool", "Pool"),
        ("library_volume", "Library Volume (uL)"),
        ("library_concentration", "Library DNA Concentration (nM)"),
        ("library_total_size", "Library Total Size (bp)"),
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
        "sample/libraryname": "sample_name",
        "librarytype": "library_type",
        "pool": "pool",
        "librarypool": "pool",
        "libraryvolume": "library_volume",
        "volume": "library_volume",
        "libraryconcentration": "library_concentration",
        "concentration": "library_concentration",
        "librarytotalsize": "library_total_size",
        "librarysize": "library_total_size",
    }
    select_field = SelectField(
        choices=required_fields + optional_fields,
        validators=[OptionalValidator()],
    )


# 2. This form is used to select what each column in the sample table represents
class SampleColTableForm(TableDataForm):
    input_fields = FieldList(FormField(SampleColSelectForm))

    def custom_validate(self) -> tuple[bool, "SampleColTableForm"]:
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data

        required_fields = SampleColSelectForm.required_fields
        optional_fields = SampleColSelectForm.optional_fields
        
        columns = data["sample_table"].columns.tolist()
        refs = [key for key, _ in required_fields if key]
        opts = [key for key, _ in optional_fields]
        matches = tools.connect_similar_strings(required_fields + optional_fields, columns, similars=SampleColSelectForm._similars)

        for i, col in enumerate(columns):
            if i >= len(self.input_fields.entries):
                select_form = SampleColSelectForm()
                select_form.select_field.label.text = col
                self.input_fields.append_entry(select_form)
            self.input_fields[i].select_field.label.text = col
            if col in matches.keys():
                self.input_fields[i].select_field.data = matches[col]
            
        self.update_data(data)
        return {
            "columns": columns,
            "required_fields": refs,
            "optional_fields": opts,
            "matches": matches,
        }
    
    def __clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df["sample_name"] = df["sample_name"].apply(tools.make_filenameable)
        if "pool" in df.columns:
            df["pool"] = df["pool"].apply(tools.make_filenameable)
        df["index_1"] = df["index_1"].astype(str).str.strip()
        df["index_2"] = df["index_2"].astype(str).str.strip()
        df["index_3"] = df["index_3"].astype(str).str.strip()
        df["index_4"] = df["index_4"].astype(str).str.strip()
        df["adapter"] = df["adapter"].astype(str).str.strip()

        df["library_volume"] = df["library_volume"].apply(tools.make_numeric)
        df["library_concentration"] = df["library_concentration"].apply(tools.make_numeric)
        df["library_total_size"] = df["library_total_size"].apply(tools.make_numeric)

        return df
    
    def parse(self) -> dict[str, pd.DataFrame]:
        data = self.data
        selected_features = []
        features = SampleColSelectForm.required_fields + SampleColSelectForm.optional_fields
        
        features = [key for key, _ in features if key]

        for feature in features:
            if feature not in data["sample_table"].columns:
                data["sample_table"][feature] = None

        for i, entry in enumerate(self.input_fields):
            if not (val := entry.select_field.data):
                continue
            val = val.strip()
            selected_features.append(val)
            data["sample_table"][val] = data["sample_table"][data["sample_table"].columns[i]]
        
        df = data["sample_table"][features]
        df.loc[df["project"].isna(), "project"] = "Project"
        df.loc[df["organism"].isna(), "organism"] = "Organism"

        df["id"] = df.reset_index(drop=True).index + 1
        df = self.__clean_df(df)
        data["sample_table"] = df
        
        self.update_data(data)

        return data