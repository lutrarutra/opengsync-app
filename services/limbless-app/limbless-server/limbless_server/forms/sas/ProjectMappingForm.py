from typing import Optional
import pandas as pd

from flask_wtf import FlaskForm
from flask import Response
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models, DBSession
from ... import db, logger
from ..TableDataForm import TableDataForm

from ..HTMXFlaskForm import HTMXFlaskForm

from .OrganismMappingForm import OrganismMappingForm
from .LibraryMappingForm import LibraryMappingForm
from ..SearchBar import OptionalSearchBar


class ProjectSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    project = FormField(OptionalSearchBar, label="Select Existing Project")
    new_project = StringField("Create New Project", validators=[OptionalValidator()])


# 3. Map sample to existing/new projects
class ProjectMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "components/popups/seq_request/sas-2.html"
    
    input_fields = FieldList(FormField(ProjectSubForm), min_entries=1)

    def __init__(self, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=None)

    def prepare(self, user_id: int, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()
        
        projects = data["library_table"]["project"].unique().tolist()

        for i, raw_label_name in enumerate(projects):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.raw_label.data = raw_label_name

            if (selected_id := entry.project.selected.data) is not None:
                selected_project = db.db_handler.get_project(selected_id)
            else:
                if raw_label_name is None or pd.isna(raw_label_name):
                    entry.raw_label.data = "Project"
                    selected_project = None
                else:
                    selected_project = next(iter(db.db_handler.query_projects(word=raw_label_name, limit=1, user_id=user_id)), None)
                    entry.project.selected.data = selected_project.id if selected_project is not None else None
                    entry.project.search_bar.data = selected_project.search_name() if selected_project is not None else None

        self.update_data(data)

        return {}
    
    def validate(self, user_id: int) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        with DBSession(db.db_handler) as session:
            user_projects = session.get_user(user_id).projects
            user_project_names = [project.name for project in user_projects]
            for field in self.input_fields:
                if field.project.selected.data is None and not field.new_project.data:
                    field.new_project.errors = ("Please select or create a project.",)
                    field.project.selected.errors = ("Please select or create a project.",)
                    validated = False

                if field.project.selected.data is not None and field.new_project.data.strip():
                    field.new_project.errors = ("Please select or create a project, not both.",)
                    field.project.selected.errors = ("Please select or create a project, not both.",)
                    validated = False

                if field.new_project.data:
                    if field.new_project.data in user_project_names:
                        field.new_project.errors = ("You already have a project with this name.",)
                        validated = False

        return validated
    
    def __parse(self, seq_request_id: int) -> dict[str, pd.DataFrame]:
        data = self.get_data()
        df = data["library_table"]

        df["project_name"] = None
        df["project_id"] = None
        projects = df["project"].unique().tolist()

        for i, raw_label in enumerate(projects):
            input_field = self.input_fields[i]
            
            if pd.isnull(raw_label):
                idx = df["project"].isna()
            else:
                idx = df["project"] == raw_label
            if (project_id := input_field.project.selected.data) is not None:
                if (project := db.db_handler.get_project(project_id)) is None:
                    raise Exception(f"Project with id {project_id} does not exist.")
                df.loc[idx, "project_id"] = project.id
                df.loc[idx, "project_name"] = project.name
            elif project_name := self.input_fields[i].new_project.data:
                df.loc[idx, "project_id"] = None
                df.loc[idx, "project_name"] = project_name
                logger.debug(f"Creating project {project_name}")
            else:
                raise Exception("Project not selected or created.")

        with DBSession(db.db_handler) as session:
            if (_ := session.get_seq_request(seq_request_id)) is None:
                raise Exception(f"Seq request with id {seq_request_id} does not exist.")
            
            # projects: dict[int, models.Project] = {}
            project_samples: dict[int, dict[str, models.Sample]] = {}
            for project_id in df["project_id"].unique():
                if not pd.isnull(project_id):
                    project_id = int(project_id)
                    if (project := session.get_project(project_id)) is None:
                        raise Exception(f"Project with id {project_id} does not exist.")
                    
                    # projects[project_id] = project
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

        data["library_table"] = df
        self.update_data(data)

        return data
    
    def process_request(self, **context) -> Response:
        user_id = context.pop("user_id")
        seq_request_id = context.pop("seq_request_id")

        validated = self.validate(user_id)
        if not validated:
            return self.make_response(**context)

        data = self.__parse(seq_request_id=seq_request_id)

        if data["library_table"]["sample_id"].isna().any():
            organism_mapping_form = OrganismMappingForm(uuid=self.uuid)
            context = organism_mapping_form.prepare(data) | context
            return organism_mapping_form.make_response(**context)

        library_mapping_form = LibraryMappingForm(uuid=self.uuid)
        context = library_mapping_form.prepare(data) | context
        return library_mapping_form.make_response(**context)
        