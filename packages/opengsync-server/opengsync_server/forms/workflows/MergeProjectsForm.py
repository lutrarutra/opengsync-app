from wtforms import FormField
from opengsync_db import queries as Q
from flask import Response, url_for
from flask_htmx import make_response

from opengsync_db import models

from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import SearchBar
from ... import db


class MergeProjectsForm(HTMXFlaskForm):
    _template_path = "workflows/merge_projects.html"

    project_dst = FormField(SearchBar, label="Destination Project to merge samples into")
    project_src = FormField(SearchBar, label="Source Project to merge samples from")


    def __init__(self, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.post_url = url_for("merge_projects_workflow.complete")

    def validate(self, user: models.User) -> bool:
        if (_ := super().validate()) is False:
            return False
        
        if self.project_dst.selected.data is None:
            self.project_dst.selected.errors = ("Please select a destination project to merge into.",)
            return False
        
        if self.project_src.selected.data is None:
            self.project_src.selected.errors = ("Please select a source project to merge from.",)
            return False

        if self.project_dst.selected.data == self.project_src.selected.data:
            self.project_src.selected.errors = ("Source and destination projects cannot be the same.",)
            self.project_dst.selected.errors = ("Source and destination projects cannot be the same.",)
            return False
        
        self.project_dst_id: int = self.project_dst.selected.data
        self.project_src_id: int = self.project_src.selected.data

        return True
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate(user):
            return self.make_response()
        
        if (project_dst := db.session.first(Q.project.select(id=self.project_dst_id))) is None:
            self.project_dst.selected.errors = ("Selected project not found.",)
            return self.make_response()
        
        if (project_src := db.session.first(Q.project.select(id=self.project_src_id))) is None:
            self.project_src.selected.errors = ("Selected project not found.",)
            return self.make_response()
        
        dst_sample_mapping = {sample.name: sample for sample in project_dst.samples}
        
        for sample in project_src.samples:
            if sample.name in dst_sample_mapping:
                dst_sample = dst_sample_mapping[sample.name]
                for attr in sample.attributes:
                    if (dst_attr := dst_sample.get_attribute(attr.name)) is not None:
                        if dst_attr.type_id != attr.type_id:
                            self.project_src.selected.errors = (f"Sample name conflict for sample '{sample.name}' with incompatible attribute types.",)
                            self.project_dst.selected.errors = (f"Sample name conflict for sample '{sample.name}' with incompatible attribute types.",)
                            return self.make_response()
                        elif dst_attr.value != attr.value:
                            self.project_src.selected.errors = (f"Sample name conflict for sample '{sample.name}' with incompatible attribute values.",)
                            self.project_dst.selected.errors = (f"Sample name conflict for sample '{sample.name}' with incompatible attribute values.",)
                            return self.make_response()
        
        project = db.actions.merge_projects(project_dst, project_src)
        return make_response(redirect=url_for("project_page", project_id=project.id))
                    