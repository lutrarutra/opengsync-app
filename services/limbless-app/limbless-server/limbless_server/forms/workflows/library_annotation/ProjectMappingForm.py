from typing import Optional, Any
import pandas as pd

from flask_wtf import FlaskForm
from flask import Response
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator, Length, DataRequired

from limbless_db import models, DBSession
from limbless_db.categories import LibraryType

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .IndexKitMappingForm import IndexKitMappingForm
from .CMOReferenceInputForm import CMOReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .CompleteSASForm import CompleteSASForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm


class ProjectSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[DataRequired()])
    project = FormField(OptionalSearchBar, label="Select Existing Project")
    new_project = StringField("Create New Project", validators=[OptionalValidator(), Length(min=6, max=models.Project.name.type.length)])


# 3. Map sample to existing/new projects
class ProjectMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-2.html"
    
    input_fields = FieldList(FormField(ProjectSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = formdata.get("file_uuid")
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)

    def prepare(self, user: models.User):
        library_table = self.tables["library_table"]
        projects = library_table["project"].unique().tolist()

        for i, raw_label_name in enumerate(projects):
            if i > len(self.input_fields.entries) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            entry.raw_label.data = raw_label_name
            project_select_field: OptionalSearchBar = entry.project  # type: ignore

            if (selected_id := project_select_field.selected.data) is not None:
                selected_project = db.get_project(selected_id)
            else:
                selected_project = next(iter(db.query_projects(word=raw_label_name, limit=1, user_id=user.id)), None)
                project_select_field.selected.data = selected_project.id if selected_project is not None else None
                project_select_field.search_bar.data = selected_project.search_name() if selected_project is not None else None
    
    def validate(self, user: models.User) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        project_data = {
            "id": [],
            "project": [],
            "name": [],
        }

        def add_project(project: str, name: str, project_id: Optional[int]):
            project_data["project"].append(project)
            project_data["name"].append(name)
            project_data["id"].append(project_id)
        
        with DBSession(db) as session:
            user_projects, _ = session.get_projects(user_id=user.id, limit=None)
            user_project_names = [project.name for project in user_projects]
            for sub_field in self.input_fields:
                project_select_field: OptionalSearchBar = sub_field.project  # type: ignore

                if project_select_field.selected.data is not None and sub_field.new_project.data.strip():
                    sub_field.new_project.errors = ("Please select or create a project, not both.",)
                    project_select_field.selected.errors = ("Please select or create a project, not both.",)
                    validated = False

                if (new_project_name := sub_field.new_project.data) is not None and new_project_name.strip():
                    if sub_field.new_project.data in user_project_names:
                        sub_field.new_project.errors = ("You already have a project with this name.",)
                        validated = False
                    add_project(sub_field.raw_label.data, new_project_name, None)
                elif (project_id := project_select_field.selected.data) is not None:
                    if (project := db.get_project(project_id)) is None:
                        logger.error(f"Project with ID {project_id} not found.")
                        raise Exception(f"Project with ID {project_id} not found.")
                    add_project(sub_field.raw_label.data, project.name, project_id)
                else:
                    sub_field.new_project.errors = ("Please select or create a project.",)
                    project_select_field.selected.errors = ("Please select or create a project.",)
                    validated = False

        self.project_table = pd.DataFrame(project_data)
        return validated
    
    def process_request(self, **context) -> Response:
        user: models.User = context["user"]

        validated = self.validate(user)
        if not validated:
            return self.make_response(**context)

        library_table = self.tables["library_table"]
        library_table["sample_id"] = None
        
        with DBSession(db) as session:
            for i, project_row in self.project_table.iterrows():
                if pd.isna(project_id := project_row["id"]):
                    continue
            
                if (project := session.get_project(project_id)) is None:
                    logger.error(f"{self.uuid}: Project with ID {project_id} not found.")
                    raise Exception(f"{self.uuid}: Project with ID {project_id} not found.")
                
                for sample in project.samples:
                    library_table.loc[library_table["sample_name"] == sample.name, "sample_id"] = sample.id
            
        library_table["sample_id"] = library_table["sample_id"].astype("Int64")
        self.project_table["id"] = self.project_table["id"].astype("Int64")

        self.add_table("project_table", self.project_table)
        self.update_table("library_table", library_table, True)

        if library_table["genome_id"].isna().any():
            organism_mapping_form = GenomeRefMappingForm(previous_form=self, uuid=self.uuid)
            organism_mapping_form.prepare()
            return organism_mapping_form.make_response(**context)
        
        if library_table["library_type_id"].isna().any():
            library_mapping_form = LibraryMappingForm(previous_form=self, uuid=self.uuid)
            library_mapping_form.prepare()
            return library_mapping_form.make_response(**context)

        if "index_kit" in library_table and not library_table["index_kit"].isna().all():
            index_kit_mapping_form = IndexKitMappingForm(previous_form=self, uuid=self.uuid)
            index_kit_mapping_form.prepare()
            return index_kit_mapping_form.make_response(**context)
        
        if library_table["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response(**context)
        
        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response(**context)
        
        if LibraryType.TENX_FLEX.id in library_table["library_type_id"].values and "pool" in library_table.columns:
            frp_annotation_form = FRPAnnotationForm(self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response(**context)
        
        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(previous_form=self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response(**context)
    
        complete_sas_form = CompleteSASForm(previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response(**context)
        