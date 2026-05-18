from wtforms import FormField
from flask import Response, url_for
from flask_htmx import make_response

from opengsync_db import models

from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import SearchBar
from ... import db


class MergeProjectsForm(HTMXFlaskForm):
    _template_path = "workflows/merge_projects.html"

    project_dst = FormField(SearchBar, label="Project to merge into")
    project_src = FormField(SearchBar, label="Project to merge from")


    def __init__(self, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)

    def validate(self, user: models.User) -> bool:
        if (_ := super().validate()) is False:
            return False
        
        if self.project_dst.search_bar.data is None:
            self.project_dst.search_bar.errors = ("Please select a project to merge into.",)
            return False
        
        if self.project_src.search_bar.data is None:
            self.project_src.search_bar.errors = ("Please select a project to merge from.",)
            return False

        if self.project_dst.search_bar.data == self.project_src.search_bar.data:
            self.project_src.search_bar.errors = ("Source and destination projects cannot be the same.",)
            self.project_dst.search_bar.errors = ("Source and destination projects cannot be the same.",)
            return False
        
        self.project_dst_id: int = self.project_dst.selected.data
        self.project_src_id: int = self.project_src.selected.data

        return True
    
    def process(self, user: models.User) -> Response:
        if not self.validate(user):
            return self.make_response()
        
        if (project_dst := db.projects.get(self.project_dst_id)) is None:
            self.project_dst.search_bar.errors = ("Selected project not found.",)
            return self.make_response()
        
        if (project_src := db.projects.get(self.project_src_id)) is None:
            self.project_src.search_bar.errors = ("Selected project not found.",)
            return self.make_response()
        
        project = db.projects.merge_projects(project_dst, project_src)
        return make_response(redirect=url_for("projects_page", project_id=project.id))
                    