from typing import Optional, TYPE_CHECKING
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db, models, logger
from .TableDataForm import TableDataForm
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user


class ProjectSubForm(FlaskForm):
    raw_category = StringField("Raw Label", validators=[OptionalValidator()])
    category = IntegerField("Select Existing Project", validators=[OptionalValidator()])

    new_category = StringField("Create New Project", validators=[OptionalValidator()])


# 3. Map sample to existing/new projects
class ProjectMappingForm(TableDataForm):
    input_fields = FieldList(FormField(ProjectSubForm), min_entries=1)

    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.data
        
        projects = data["sample_table"]["project"].unique()
        selected: list[Optional[str]] = []    # TODO: get projects for each selected

        for i, raw_project_name in enumerate(projects):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields.entries[i]

            if (selected_id := entry.category.data) is not None:
                selected_project = db.db_handler.get_project(selected_id)
            else:
                if projects[i] is None:
                    selected_project = None
                else:
                    if raw_project_name is None or pd.isna(raw_project_name):
                        raw_project_name = ""
                    
                    selected_project = next(iter(db.db_handler.query_projects(word=raw_project_name, limit=1, user_id=current_user.id)), None)
                    entry.category.data = selected_project.id if selected_project is not None else None

            selected.append(selected_project.search_name() if selected_project is not None else None)

        self.update_data(data)

        return {
            "categories": projects,
            "selected": selected,
        }
    
    def parse(self, seq_request_id: int) -> dict[str, pd.DataFrame]:
        data = self.data
        df = data["sample_table"]

        df["project_name"] = None
        df["project_id"] = None
        projects = df["project"].unique()

        for i, raw_project in enumerate(projects):
            if (project_id := self.input_fields[i].category.data) is not None:
                if (project := db.db_handler.get_project(project_id)) is None:
                    raise Exception(f"Project with id {project_id} does not exist.")
                
                df.loc[df["project"] == raw_project, "project_id"] = project.id
                df.loc[df["project"] == raw_project, "project_name"] = project.name
            elif project_name := self.input_fields[i].new_category.data:
                df.loc[df["project"] == raw_project, "project_id"] = None
                df.loc[df["project"] == raw_project, "project_name"] = project_name
                logger.debug(f"Creating project {project_name}")
            else:
                raise Exception("Project not selected or created.")

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
        
        df["sample_id"] = None
        df["tax_id"] = None
        for i, row in df.iterrows():
            if row["project_id"] is None:
                _project_samples = {}
            else:
                _project_samples = project_samples[row["project_id"]]

            if row["sample_name"] in _project_samples.keys():
                df.at[i, "sample_id"] = _project_samples[row["sample_name"]].id
                df.at[i, "tax_id"] = _project_samples[row["sample_name"]].organism.tax_id

        df["project_id"] = df["project_id"].astype("Int64")
        df["sample_id"] = df["sample_id"].astype("Int64")

        data["sample_table"] = df
        self.update_data(data)

        return data

    def custom_validate(self, db_handler: DBHandler, user_id: int):
        validated = self.validate()
        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            user_projects = session.get_user(user_id).projects
            user_project_names = [project.name for project in user_projects]
            for field in self.input_fields:
                if field.category.data is None and not field.new_category.data:
                    field.new_category.errors = ("Please select or create a project.",)
                    field.category.errors = ("Please select or create a project.",)
                    validated = False
                
                if field.category.data is not None and field.new_category.data.strip():
                    field.new_category.errors = ("Please select or create a project, not both.",)
                    field.category.errors = ("Please select or create a project, not both.",)
                    validated = False
                if field.new_category.data:
                    if field.new_category.data in user_project_names:
                        field.new_category.errors = ("You already have a project with this name.",)
                        validated = False

        return validated, self