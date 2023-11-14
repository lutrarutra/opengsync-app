from typing import Optional
from io import StringIO
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from ... import db
from .TableDataForm import TableDataForm
from ...core.DBHandler import DBHandler
from ...core.DBSession import DBSession


class ProjectSubForm(FlaskForm):
    raw_category = StringField("Raw Label", validators=[OptionalValidator()])
    category = IntegerField("Project", validators=[OptionalValidator()])

    new_category = StringField("Create New Project", validators=[OptionalValidator()])


# 3. Map sample to existing/new projects
class ProjectMappingForm(TableDataForm):
    input_fields = FieldList(FormField(ProjectSubForm), min_entries=1)

    def prepare(self, df: Optional[pd.DataFrame] = None) -> dict:
        if df is None:
            df = self.get_df()
        else:
            self.set_df(df)
        
        projects = sorted(df["project"].unique())
        selected: list[str] = []    # TODO: get projects for each selected

        return {
            "categories": projects,
            "selected": selected,
        }
    
    def parse(self) -> pd.DataFrame:
        df = self.get_df()

        df["project_name"] = None
        df["project_id"] = None
        projects = sorted(df["project"].unique())
        for i, raw_project in enumerate(projects):
            if (project_id := self.input_fields.entries[i].category.data) is not None:
                if (project := db.db_handler.get_project(project_id)) is None:
                    raise Exception(f"Project with id {project_id} does not exist.")
                
                df.loc[df["project"] == raw_project, "project_id"] = project.id
                df.loc[df["project"] == raw_project, "project_name"] = project.name
            elif project_name := self.input_fields.entries[i].new_category.data:
                df.loc[df["project"] == raw_project, "project_id"] = None
                df.loc[df["project"] == raw_project, "project_name"] = project_name
            else:
                return Exception("Project not selected or created.")

        return df

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
                if field.category.data and field.new_category.data:
                    field.new_category.errors = ("Please select or create a project, not both.",)
                    field.category.errors = ("Please select or create a project, not both.",)
                    validated = False
                if field.new_category.data:
                    if field.new_category.data in user_project_names:
                        field.new_category.errors = ("You already have a project with this name.",)
                        validated = False

        return validated, self