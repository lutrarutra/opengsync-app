from typing import Optional, TYPE_CHECKING
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db, models, logger, tools
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession
from ...categories import LibraryType
from .TableDataForm import TableDataForm

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


class PoolSubForm(FlaskForm):
    pool_label = StringField("Library (-Pool) Label", validators=[DataRequired(), Length(min=6, max=64)], description="Unique label to identify the pool")
    index_kit = IntegerField("Index Kit (optional)", validators=[OptionalValidator()], description="Index kit used in the pool. If a custom kit or more than a single kit is used, leave this field empty.")
    contact_person_name = StringField("Contact Person Name", validators=[DataRequired(), Length(max=128)], description="Who prepared the libraries?")
    contact_person_email = StringField("Contact Person Email", validators=[DataRequired(), Length(max=128)], description="Who prepared the libraries?")
    contact_person_phone = StringField("Contact Person Phone", validators=[OptionalValidator(), Length(max=16)], description="Who prepared the libraries?")


class PoolMappingForm(TableDataForm):
    input_fields = FieldList(FormField(PoolSubForm), min_entries=1)

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self
        
        reused_labels = []
        for entry in self.input_fields:
            pool_label = entry.pool_label.data
            if pool_label in reused_labels:
                entry.pool_label.errors = ("Pool label is not unique.",)
                return False, self
            reused_labels.append(pool_label)

        return validated, self
    
    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()
        
        df["pool"] = df["pool"].apply(lambda x: str(x) if x and not pd.isna(x) and not pd.isnull(x) else "__NONE__")
        pools = []
        pool_libraries = []
        for i, (pool_label, _df) in enumerate(df.groupby("pool")):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            pool_raw_label = pool_label if pool_label != "__NONE__" else f"Pool {i+1}"
            pools.append(pool_raw_label)

            entry = self.input_fields[i]
            if entry.pool_label.data is None:
                entry.pool_label.data = pool_label if pool_label != "__NONE__" else ""
            if entry.contact_person_name.data is None:
                entry.contact_person_name.data = current_user.name
            if entry.contact_person_email.data is None:
                entry.contact_person_email.data = current_user.email

            _data = {}
            for _, row in _df.iterrows():
                sample_name = row["sample_name"]
                if sample_name not in _data.keys():
                    _data[sample_name] = []

                _data[sample_name].append({
                    "library_type": row["library_type"],
                    "library_volume": row["library_volume"],
                    "library_concentration": row["library_concentration"],
                    "library_total_size": row["library_total_size"],
                })

            pool_libraries.append(_data)

        self.set_df(df)

        return {
            "pools": pools,
            "pool_libraries": pool_libraries,
        }

    def parse(self) -> pd.DataFrame:
        df = self.get_df()

        df["contact_person_name"] = None
        df["contact_person_email"] = None
        df["contact_person_phone"] = None
        df["index_kit"] = None

        df["pool"] = df["pool"].astype(str)
        raw_pool_labels = df["pool"].unique().tolist()
        for i, entry in enumerate(self.input_fields.entries):
            pool_label = entry.pool_label.data
            index_kit = entry.index_kit.data
            contact_person_name = entry.contact_person_name.data
            contact_person_email = entry.contact_person_email.data
            contact_person_phone = entry.contact_person_phone.data

            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_name"] = contact_person_name
            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_email"] = contact_person_email
            df.loc[df["pool"] == raw_pool_labels[i], "contact_person_phone"] = contact_person_phone
            df.loc[df["pool"] == raw_pool_labels[i], "pool"] = pool_label
            df.loc[df["pool"] == raw_pool_labels[i], "index_kit"] = index_kit

        self.set_df(df)
        return df