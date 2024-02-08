import os
from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from flask_wtf.file import FileField, FileAllowed
from wtforms import TextAreaField
from wtforms.validators import Optional as OptionalValidator, Length
from werkzeug.utils import secure_filename

from .HTMXFlaskForm import HTMXFlaskForm
from .. import models, logger


class CompleteExperimentForm(HTMXFlaskForm):
    _template_path = "forms/complete-experiment.html"
    _form_label = "complete_experiment_form"

    file = FileField("Sequencing Quality Control", validators=[FileAllowed(["pdf"])])
    comment = TextAreaField("Complications, errors, etc..", validators=[OptionalValidator(), Length(min=1, max=1024)], default="")

    def __init__(self, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("media", "sequencing_quality_control")

    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False

        if self.file.data is None:
            self.file.errors = ("File is required.",)
            return False

        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        experiment: models.Experiment = context["experiment"]

        filename = secure_filename(self.file.data.filename)
        self.file.data.save(os.path.join(self.upload_path, filename))

        flash("Sequencing quality control file uploaded successfully.", "success")
        logger.info(f"Sequencing quality control file for experiment {experiment.id} uploaded successfully.")

        return make_response(
            redirect=url_for(
                "experiments_page.experiment_page", experiment_id=experiment.id
            )
        )