from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length


from limbless_db import models, DBSession
from limbless_db.categories import SampleStatus
from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm


class SampleForm(HTMXFlaskForm):
    _template_path = "forms/sample.html"
    _form_label = "sample_form"

    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=models.Sample.name.type.length)])
    status = SelectField("Status", choices=SampleStatus.as_selectable(), coerce=int)

    def __init__(self, formdata: Optional[dict[str, Any]] = None, sample: Optional[models.Sample] = None):
        super().__init__(formdata=formdata)
        if sample is not None:
            self.__fill_form(sample)

    def __fill_form(self, sample: models.Sample):
        self.name.data = sample.name
        self.status.data = sample.status.id

    def validate(self, user_id: int, sample: models.Sample) -> bool:
        if not super().validate():
            return False
        
        with DBSession(db) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False
            
            user_samples = user.samples
            
            for user_sample in user_samples:
                if self.name.data == user_sample.name:
                    if sample.id != user_sample.id:
                        self.name.errors = ("You already have a sample with this name.",)
                        return False
        
        return True
    
    def process_request(self, **context) -> Response:
        user_id = context["user_id"]
        sample: models.Sample = context["sample"]

        if not self.validate(user_id=user_id, sample=sample):
            return self.make_response(**context)
        
        sample.name = self.name.data  # type: ignore
        sample.status_id = self.status.data
       
        sample = db.update_sample(sample)

        flash("Changes saved succesfully!", "success")
        return make_response(
            redirect=url_for("samples_page.sample_page", sample_id=sample.id),
        )