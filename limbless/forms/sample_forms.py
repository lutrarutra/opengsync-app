from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length
from wtforms.validators import Optional as OptionalValidator


from .. import logger, db, models
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession
from .categorical_mapping import CategoricalMappingField


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


# Select a single sample for something
class SampleSelectForm(FlaskForm):
    query_field = StringField("Search", validators=[DataRequired()])


# Column selection form for sample table
class SampleColSelectForm(FlaskForm):
    required_fields = [
        ("", "-"),
        ("sample_name", "Sample Name"),
        ("organism", "Organism"),
    ]
    optional_fields = [
        ("adapter", "Adapter"),
        ("index_1", "Index 1"),
        ("index_2", "Index 2"),
        ("project", "Project"),
    ]
    select_field = SelectField(
        choices=required_fields,
    )


# 2. This form is used to select what each column in the sample table represents
class SampleColTableForm(FlaskForm):
    fields = FieldList(FormField(SampleColSelectForm))
    data = TextAreaField()

###
# Seq request sample forms
###


# 3. Select existing project for samples
class SampleProjectSelectForm(FlaskForm):
    existing_project = IntegerField("Project", validators=[OptionalValidator()])
    new_project = StringField("New Project", validators=[OptionalValidator(), Length(min=6, max=64)])
    data = TextAreaField(validators=[DataRequired()])

    def custom_validate(self, db_handler: DBHandler, user_id: int):
        validated = self.validate()
        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False, self
            if (not self.existing_project.data) and (not self.new_project.data):
                self.new_project.errors = ("Please select or create a project.",)
                validated = False
            if self.existing_project.data and self.new_project.data:
                self.new_project.errors = ("Please select or create a project, not both.",)
                validated = False
            if self.existing_project.data:
                if (project := session.get_project(self.existing_project.data)) is None:
                    logger.error(f"Project with id {self.existing_project.data} does not exist.")
                    return False, self
                if project.owner_id != user_id:
                    self.existing_project.errors = ("You do not have access to this project.",)
                    validated = False
            if self.new_project.data:
                if self.new_project.data in [project.name for project in user.projects]:
                    self.new_project.errors = ("You already have a project with this name.",)
                    validated = False

        return validated, self


# 4. Select organism for samples
class OrganismMappingForm(FlaskForm):
    fields = FieldList(FormField(CategoricalMappingField))
    data = TextAreaField(validators=[DataRequired()])

    def custom_validate(self, db_handler: DBHandler):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self

    def prepare(self, seq_request_id: int, df: pd.DataFrame) -> pd.DataFrame:
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                raise Exception(f"Seq request with id {seq_request_id} does not exist.")
            
            projects: dict[int, models.Project] = {}
            project_samples: dict[int, dict[str, models.Sample]] = {}
            for project_id in df["project_id"].unique():
                if not pd.isnull(project_id):
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    projects[project_id] = project
                    project_samples[project_id] = dict([(sample.name, sample) for sample in project.samples])
            
            seq_request_samples = dict([(sample.name, sample) for sample in seq_request.samples])

        df["sample_id"] = None
        df["tax_id"] = None
        df["project_id"] = None
        df["duplicate"] = False

        for i, row in df.iterrows():
            if row["sample_name"] in project_samples.keys():
                project = projects[row["project_id"]]
                _project_samples = project_samples[row["project_id"]]

                df.at[i, "sample_id"] = _project_samples[row["sample_name"]].id
                df.at[i, "tax_id"] = _project_samples[row["sample_name"]].organism.tax_id
                df.at[i, "project_id"] = _project_samples[row["sample_name"]].project_id

            if row["sample_name"] in seq_request_samples.keys():
                df.at[i, "duplicate"] = True

        self.data.data = df.to_csv(sep="\t", index=False, header=True)
        return df


# 5. Confirm samples before creating
class SampleConfirmForm(FlaskForm):
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
    
    def parse_samples(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> list[Optional[dict[str, str | int | None]]]:
        if df is None:
            df = pd.read_csv(StringIO(self.data.data), sep="\t", index_col=False, header=0)

        idx = df["sample_name"].duplicated(keep=False)
        df.loc[idx, "sample_name"] = df.loc[idx, "sample_name"] + "." + df.loc[idx, :].groupby("sample_name").cumcount().add(1).astype(str)

        samples: list[Optional[dict[str, str | int | None]]] = []
        
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                raise Exception(f"Seq request with id {seq_request_id} does not exist.")
            
            projects: dict[int, models.Project] = {}
            project_samples: dict[int, dict[str, models.Sample]] = {}
            for project_id in df["project_id"].unique():
                if not pd.isnull(project_id):
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    projects[project_id] = project
                    project_samples[project_id] = dict([(sample.name, sample) for sample in project.samples])
            
            seq_request_samples = dict([(sample.name, sample) for sample in seq_request.samples])

        selected: list[str] = []
        for i, row in df.iterrows():
            # Check if sample names are unique in project
            data = {
                "id": int(i) + 1,
                "name": row["sample_name"],
                "organism": row["organism"],
                "tax_id": row["tax_id"],
                "error": None,
                "info": "",
                "sample_id": row["sample_id"],
                "project_name": row["project_name"],
            }

            _project_sampels = project_samples[row["project_id"]] if row["project_id"] in project_samples.keys() else {}

            if row["sample_name"] in seq_request_samples.keys():
                data["error"] = f"Error: Sample name {row['sample_name']} already exists in seq request."
            elif row["sample_name"] in _project_sampels.keys():
                data["info"] = "Existing sample found from project."
                selected.append(str(int(i) + 1))
            else:
                selected.append(str(int(i) + 1))

            samples.append(data)

        self.selected_samples.data = ",".join(selected)
        self.data.data = df.to_csv(sep="\t", index=False, header=True)

        return samples