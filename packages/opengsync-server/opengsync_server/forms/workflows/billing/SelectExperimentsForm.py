import json

from flask import url_for
from wtforms import StringField
from wtforms.validators import DataRequired

from opengsync_db import models

from .... import db
from ....core import exceptions
from ...HTMXFlaskForm import HTMXFlaskForm


class SelectExperimentsForm(HTMXFlaskForm):
    selected_users: list[models.User]
    _template_path = "workflows/billing/billing-1.html"
    __selected_experiments: list[models.Experiment] | None = None

    selected_experiment_ids = StringField(validators=[DataRequired()])

    def __init__(self, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.post_url = url_for("billing_workflow.select")
        self.url_context = {}
        self._context["url_context"] = {"workflow": "billing"}
        self._context["workflow"] = "billing"

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        selected_experiment_ids = self.selected_experiment_ids.data

        if not selected_experiment_ids:
            self.selected_experiment_ids.errors = ("No experiments selected",)
            return False
        
        experiment_ids = json.loads(selected_experiment_ids)
        selected_experiments = []
        try:
            for experiment_id in experiment_ids:
                if (experiment := db.experiments.get(int(experiment_id))) is None:
                    raise exceptions.NotFoundException(f"Experiment with id {experiment_id} not found")
                selected_experiments.append(experiment)
        except ValueError:
            self.selected_experiment_ids.errors = ("Invalid experiment ids",)
            return False
                
        self.__selected_experiments = selected_experiments

        return True

    @property
    def selected_experiments(self) -> list[models.Experiment]:
        if self.__selected_experiments is None:
            raise exceptions.InternalServerErrorException("Form not validated yet")
        return self.__selected_experiments