from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length


from opengsync_db import models
from opengsync_db.categories import SampleStatus

from ... import db
from ...tools import utils
from ..HTMXFlaskForm import HTMXFlaskForm


class SampleForm(HTMXFlaskForm):
    _template_path = "forms/sample.html"
    _form_label = "sample_form"

    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=models.Sample.name.type.length)])
    status = SelectField("Status", choices=SampleStatus.as_selectable(), coerce=int)

    def __init__(self, sample: models.Sample, formdata: Optional[dict[str, Any]] = None):
        super().__init__(formdata=formdata)
        self.sample = sample
        self._context["sample"] = sample

    def prepare(self):
        self.name.data = self.sample.name
        self.status.data = self.sample.status.id if self.sample.status is not None else None

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if (error := utils.check_string(self.name.data)):
            self.name.errors = (error,)
            return False
        
        for user_sample in self.sample.project.samples:
            if self.name.data == user_sample.name:
                if self.sample.id != user_sample.id:
                    self.name.errors = ("Project has already a sample with this name.",)
                    return False
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.sample.name = self.name.data  # type: ignore
        self.sample.status_id = self.status.data
       
        db.samples.update(self.sample)

        flash("Changes saved!", "success")
        return make_response(
            redirect=url_for("samples_page.sample", sample_id=self.sample.id),
        )