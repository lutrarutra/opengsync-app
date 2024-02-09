import os
from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import TextAreaField
from wtforms.validators import Optional as OptionalValidator, Length

from .HTMXFlaskForm import HTMXFlaskForm
from .. import models, logger, db, categories


class CompleteExperimentForm(HTMXFlaskForm):
    _template_path = "forms/complete-experiment.html"
    _form_label = "complete_experiment_form"

    comment = TextAreaField("Complications, errors, etc..", validators=[OptionalValidator(), Length(min=1, max=1024)], default="")

    def __init__(self, formdata: Optional[dict] = None):
        super().__init__(formdata=formdata)
        self.upload_path = os.path.join("media", "sequencing_quality_control")

    def validate(self) -> bool:
        validated = super().validate()
        if not validated:
            return False

        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        experiment: models.Experiment = context["experiment"]
        experiment.status_id = categories.ExperimentStatus.FINISHED.value.id
        experiment = db.db_handler.update_experiment(experiment)
        
        flash("Experiment completed!.", "success")
        logger.info(f"Experiment '{experiment.id}' completed!.")

        return make_response(
            redirect=url_for(
                "experiments_page.experiment_page", experiment_id=experiment.id
            )
        )