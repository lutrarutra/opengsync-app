from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length

from .. import logger, db, models
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession


class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = IntegerField("Organism", validators=[DataRequired()])

    def custom_validate(
        self, db_handler: DBHandler, user_id: int,
        sample_id: int | None = None,
    ) -> tuple[bool, "SampleForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        with DBSession(db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False, self
            
            user_samples = user.samples

            # Creating new sample
            if sample_id is None:
                if self.name.data in [sample.name for sample in user_samples]:
                    self.name.errors = ("You already have a sample with this name.",)
                    validated = False
            # Editing existing sample
            else:
                if (sample := session.get_sample(sample_id)) is None:
                    logger.error(f"Sample with id {sample_id} does not exist.")
                    return False, self
                
                for user_sample in user_samples:
                    if self.name.data == user_sample.name:
                        if sample_id != user_sample.id:
                            self.name.errors = ("You already have a sample with this name.",)
                            validated = False
                            break

        return validated, self


class SampleSelectForm(FlaskForm):
    query_field = StringField("Search", validators=[DataRequired()])


class ProjectSampleSelectForm(FlaskForm):
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
    
    def parse_project_samples(self, project_id: int, df: Optional[pd.DataFrame] = None) -> tuple[list[Optional[dict[str, str | int | None]]], list[Optional[str]]]:
        if df is None:
            df = pd.read_csv(StringIO(self.data.data), sep="\t", index_col=False, header=0)

        idx = df["sample_name"].duplicated(keep=False)
        df.loc[idx, "sample_name"] = df.loc[idx, "sample_name"] + "." + df.loc[idx, :].groupby("sample_name").cumcount().add(1).astype(str)

        project_samples: list[Optional[dict[str, str | int | None]]] = []
        errors: list[Optional[str]] = []

        with DBSession(db.db_handler) as session:
            project = session.get_project(project_id)
            project_names = [sample.name for sample in project.samples]

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            if row["sample_name"] in project_names:
                project_samples.append({
                    "id": None,
                    "name": row["sample_name"],
                    "organism": row["organism"],
                    "organism_id": row["organism_id"],
                })
                errors.append(f"Sample name {row['sample_name']} already exists.")
            else:
                project_samples.append({
                    "id": int(i),
                    "name": row["sample_name"],
                    "organism": row["organism"],
                    "organism_id": row["organism_id"],
                })
                errors.append(None)

        self.selected_samples.data = ",".join([str(sample["id"]) for sample in project_samples if sample and sample["id"] is not None])
        self.data.data = df.to_csv(sep="\t", index=False, header=True)

        return project_samples, errors



class SampleColSelectForm(FlaskForm):
    _sample_fields = [
        ("", "-"),
        ("sample_name", "Sample Name"),
        ("organism", "Organism"),
    ]
    select_field = SelectField(
        choices=_sample_fields,
    )


class SampleTableForm(FlaskForm):
    fields = FieldList(FormField(SampleColSelectForm))
    data = TextAreaField(validators=[DataRequired()])

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self
