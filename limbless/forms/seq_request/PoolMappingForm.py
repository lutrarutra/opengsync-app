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
    pool_label = StringField("Pool Label", validators=[DataRequired(), Length(max=64)])
    contact_person_name = StringField("Contact Person Name", validators=[DataRequired(), Length(max=128)])
    contact_person_email = StringField("Contact Person Email", validators=[DataRequired(), Length(max=128)])
    contact_person_phone = StringField("Contact Person Phone", validators=[OptionalValidator(), Length(max=16)])


class PoolMappingForm(TableDataForm):
    input_fields = FieldList(FormField(PoolSubForm), min_entries=1)

    def custom_validate(self, db_handler: DBHandler):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self
    
    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()
        
        pools = df["pool"].unique().tolist()
        pool_libraries = []
        for i, (pool_label, _df) in enumerate(df.groupby("pool")):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()
            entry = self.input_fields.entries[i]
            entry.pool_label.data = pool_label
            entry.contact_person_name.data = current_user.name
            entry.contact_person_email.data = current_user.email

            _data = {}
            for _, row in _df.iterrows():
                sample_name = row["sample_name"]
                if sample_name not in _data.keys():
                    _data[sample_name] = []

                _data[sample_name].append({
                    "library_type": row["library_type"],
                    "library_kit": row["library_kit"],
                    "library_volume": row["library_volume"],
                    "library_concentration": row["library_concentration"],
                    "library_total_size": row["library_total_size"],
                })

            pool_libraries.append(_data)

        logger.debug(pool_libraries)

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

        for i, entry in enumerate(self.input_fields.entries):
            pool_label = entry.pool_label.data
            contact_person_name = entry.contact_person_name.data
            contact_person_email = entry.contact_person_email.data
            contact_person_phone = entry.contact_person_phone.data

            df.loc[df["pool"] == pool_label, "contact_person_name"] = contact_person_name
            df.loc[df["pool"] == pool_label, "contact_person_email"] = contact_person_email
            df.loc[df["pool"] == pool_label, "contact_person_phone"] = contact_person_phone

        self.set_df(df)
        return df