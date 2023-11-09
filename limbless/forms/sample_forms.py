from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length
from wtforms.validators import Optional as OptionalValidator


from .. import logger, db, models
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession
from .categorical_mapping import CategoricalMappingField, CategoricalMappingFieldWithNewCategory


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
        choices=required_fields + optional_fields,
    )


# 2. This form is used to select what each column in the sample table represents
class SampleColTableForm(FlaskForm):
    fields = FieldList(FormField(SampleColSelectForm))
    data = TextAreaField()

###
# Seq request sample forms
###


# 3. Map sample to existing/new projects
class ProjectMappingForm(FlaskForm):
    fields = FieldList(FormField(CategoricalMappingFieldWithNewCategory))
    data = TextAreaField(validators=[DataRequired()])

    def custom_validate(self, db_handler: DBHandler, user_id: int):
        validated = self.validate()
        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            user_projects = session.get_user(user_id).projects
            user_project_names = [project.name for project in user_projects]
            for field in self.fields:
                if field.category.data is None and not field.new_category.data:
                    field.new_category.errors = ("Please select or create a project.",)
                    field.category.errors = ("Please select or create a project.",)
                    validated = False
                if field.category.data and field.new_category.data:
                    field.new_category.errors = ("Please select or create a project, not both.",)
                    field.category.errors = ("Please select or create a project, not both.",)
                    validated = False
                if field.new_category.data:
                    if field.new_category.data in user_project_names:
                        field.new_category.errors = ("You already have a project with this name.",)
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
                    project_id = int(project_id)
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    projects[project_id] = project
                    project_samples[project_id] = dict([(sample.name, sample) for sample in project.samples])
            
            seq_request_samples = dict([(sample.name, sample) for sample in seq_request.samples])

        df["sample_id"] = None
        df["tax_id"] = None
        df["duplicate"] = False

        for i, row in df.iterrows():
            if row["project_id"] is None:
                _project_samples = {}
            else:
                _project_samples = project_samples[row["project_id"]]
            if row["sample_name"] in _project_samples.keys():
                project = projects[row["project_id"]]

                df.at[i, "sample_id"] = _project_samples[row["sample_name"]].id
                df.at[i, "tax_id"] = _project_samples[row["sample_name"]].organism.tax_id

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
    
    def parse_samples(self, seq_request_id: int, df: Optional[pd.DataFrame] = None) -> list[dict[str, str | int | None]]:
        if df is None:
            df = pd.read_csv(StringIO(self.data.data), sep="\t", index_col=False, header=0)

        idx = df["sample_name"].duplicated(keep=False)
        df.loc[idx, "sample_name"] = df.loc[idx, "sample_name"] + "." + df.loc[idx, :].groupby("sample_name").cumcount().add(1).astype(str)

        samples: list[dict[str, str | int | None]] = []
        
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                raise Exception(f"Seq request with id {seq_request_id} does not exist.")
            
            projects: dict[int, models.Project] = {}
            project_samples: dict[int, dict[str, models.Sample]] = {}
            for project_id in df["project_id"].unique():
                if not pd.isnull(project_id):
                    project_id = int(project_id)
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    projects[project_id] = project
                    project_samples[project_id] = dict([(sample.name, sample) for sample in project.samples])
            
            seq_request_samples = dict([(sample.name, sample) for sample in seq_request.samples])

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            data = {
                "id": int(i) + 1,
                "name": row["sample_name"],
                "organism": row["organism"],
                "tax_id": row["tax_id"],
                "error": None,
                "info": "",
                "sample_id": int(row["sample_id"]) if not pd.isnull(row["sample_id"]) else None,
                "project_id": int(row["project_id"]) if not pd.isnull(row["project_id"]) else None,
                "project_name": row["project_name"],
                "index_1": row["index_1"],
                "index_2": row["index_2"],
                "adapter": row["adapter"],
            }

            _project_sampels = project_samples[row["project_id"]] if row["project_id"] in project_samples.keys() else {}

            if row["sample_name"] in seq_request_samples.keys():
                data["error"] = f"Error: Sample name {row['sample_name']} already exists in this request."
            elif row["sample_name"] in _project_sampels.keys():
                data["info"] = "Existing sample found from project."
            else:
                data["info"] = "New sample."

            samples.append(data)

        self.data.data = df.to_csv(sep="\t", index=False, header=True)

        return samples
    

# 6. Check indices
class CheckIndexForm(FlaskForm):
    data = TextAreaField(validators=[DataRequired()])
    reverse_complement_index_1 = BooleanField("Reverse complement index 1")
    reverse_complement_index_2 = BooleanField("Reverse complement index 2")

    def custom_validate(self):
        validated = self.validate()
        if not validated:
            return False, self

        return validated, self
    
    def init(self, df: pd.DataFrame) -> list[dict[str, str | int | None]]:
        samples_data: list[dict[str, str | int | None]] = []
        
        reused_indices = df[["index_1", "index_2"]].duplicated(keep=False).values.tolist()

        for i, row in df.iterrows():
            # Check if sample names are unique in project
            data = {
                "id": int(i) + 1,
                "name": row["sample_name"],
                "error": None,
                "warning": None,
                "info": "",
                "index_1": row["index_1"],
                "index_2": row["index_2"],
                "adapter": row["adapter"],
            }

            if data["index_1"] == data["index_2"]:
                data["warning"] = "Warning: Index 1 and index 2 are the same."

            if reused_indices[i]:
                data["warning"] = "Index combination is reused in two or more samples."

            samples_data.append(data)

        self.data.data = df.to_csv(sep="\t", index=False, header=True)

        return samples_data