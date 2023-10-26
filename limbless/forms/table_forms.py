from typing import Optional
from io import StringIO
from uuid import uuid4

import pandas as pd

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, DataRequired
from wtforms import TextAreaField, FieldList, FormField, SelectField, StringField
from werkzeug.utils import secure_filename
from flask_login import current_user

from .. import logger, db, models
from ..core.DBSession import DBSession


class LibrarySampleSelectForm(FlaskForm):
    data = TextAreaField(validators=[DataRequired()])
    selected_samples = StringField()

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        if self.selected_samples.data is None or len(self.selected_samples.data) == 0:
            self.selected_samples.errors = ("Please select at least one sample.",)
            validated = False

        return validated, self
    
    def parse_library_samples(self, library_id: int, df: Optional[pd.DataFrame] = None) -> tuple[list[Optional[dict[str, str | int | None]]], list[Optional[str]]]:
        if df is None:
            df = pd.read_csv(StringIO(self.data.data), sep="\t", index_col=False, header=0)

        user_samples = db.db_handler.get_samples(user_id=current_user.id, limit=None)
        user_sample_names = [sample.name for sample in user_samples]

        library_samples: list[Optional[dict[str, str | int | None]]] = []
        errors: list[Optional[str]] = []

        with DBSession(db.db_handler) as session:
            library = db.db_handler.get_library(library_id=library_id)
            library_samples_ids: list[int] = [sample.id for sample in library.samples]

        df["id"] = None

        for i, row in df.iterrows():
            sample_name = row["sample_name"].strip()
            if sample_name in user_sample_names:
                user_sample = user_samples[user_sample_names.index(sample_name)]
                # Check if sample is already in library
                if user_sample.id in library_samples_ids:
                    library_samples.append({
                        "id": None,
                        "name": sample_name,
                        "adapter": row["adapter"].strip(),
                        "organism": None,
                    })
                    errors.append(f"Duplicate sample '{sample_name}' in this library")
                # Check if there exists adapter in library's indexkit

                elif (not library.is_raw_library()) and db.db_handler.get_adapter_by_name(library.index_kit_id, row["adapter"].strip()) is None:
                    library_samples.append({
                        "id": None,
                        "name": sample_name,
                        "adapter": row["adapter"].strip(),
                        "organism": None,
                    })
                    errors.append(f"Unknown adapter '{sample_name}' for {library.index_kit.name}")
                else:
                    library_samples.append({
                        "id": user_sample.id,
                        "name": sample_name,
                        "adapter": row["adapter"].strip(),
                        "organism": user_sample.organism.scientific_name,
                    })
                    df.at[i, "id"] = user_sample.id
                    errors.append(None)
            else:
                # User does not have a sample with name
                library_samples.append({
                    "id": None,
                    "name": sample_name,
                    "adapter": row["adapter"].strip(),
                    "organism": None,
                })
                errors.append(f"Unknown sample '{sample_name}'")

        self.selected_samples.data = ",".join([str(sample["id"]) for sample in library_samples if sample and sample["id"] is not None])
        df["id"] = df["id"].astype(pd.Int32Dtype())
        self.data.data = df.to_csv(sep="\t", index=False, header=True)
        return library_samples, errors


class LibraryColSelectForm(FlaskForm):
    _fields: list[tuple[str, str]] = [
        ("", "-"),
        ("sample_name", "Sample Name"),
        ("adapter", "Adapter"),
    ]
    select_field = SelectField(
        choices=_fields,
    )
    

class LibraryColMappingForm(FlaskForm):
    fields = FieldList(FormField(LibraryColSelectForm))
    data = TextAreaField(validators=[DataRequired()])

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self


class TableForm(FlaskForm):
    _allowed_extensions: list[tuple[str, str]] = [
        ("tsv", "Tab-separated"),
        ("csv", "Comma-separated")
    ]
    separator = SelectField(choices=_allowed_extensions, default="tsv")
    file = FileField(validators=[FileAllowed([ext for ext, _ in _allowed_extensions])])
    data = TextAreaField()

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        file_field_empty = self.file.data is None
        data_field_empty = self.data.data == "" or self.data.data is None

        if file_field_empty and data_field_empty:
            self.file.errors = ("Please upload a file or paste data.",)
            self.data.errors = ("Please upload a file or paste data.",)
            validated = False

        elif (not file_field_empty) and (not data_field_empty):
            self.file.errors = ("Please upload a file or paste data, not both.",)
            self.data.errors = ("Please upload a file or paste data, not both.",)
            validated = False

        return validated, self
    
    def get_data(self):
        if self.separator.data == "tsv":
            sep = "\t"
        else:
            sep = ","

        if self.data.data:
            raw_text = self.data.data
        else:
            filename = f"{self.file.data.filename.split('.')[0]}_{uuid4()}.{self.file.data.filename.split('.')[-1]}"
            filename = secure_filename(filename)
            self.file.data.save("data/uploads/" + filename)
            logger.debug(f"Saved file to data/uploads/{filename}")
            raw_text = open("data/uploads/" + filename).read()
        
        return raw_text, sep

        
