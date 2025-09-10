from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, IntegerField, SelectField, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models, exceptions
from opengsync_db.categories import ExperimentWorkFlow, ExperimentStatus
from ..HTMXFlaskForm import HTMXFlaskForm
from ... import db
from ..SearchBar import SearchBar


class ExperimentForm(HTMXFlaskForm):
    _template_path = "forms/experiment.html"

    name = StringField("Experiment Name", validators=[DataRequired(), Length(min=3, max=models.Experiment.name.type.length)])
    sequencer = FormField(SearchBar, label="Select Sequencer", description="Select the sequencer that will be used for sequencing.")
    operator = FormField(SearchBar, label="Operator")

    workflow = SelectField(
        "Workflow", choices=ExperimentWorkFlow.as_selectable(),
        description="Select the workflow for the experiment.",
        coerce=int, default=None
    )

    status = SelectField(
        "Status", choices=ExperimentStatus.as_selectable(),
        coerce=int, default=ExperimentStatus.DRAFT.id
    )
    
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[OptionalValidator()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[OptionalValidator()])

    def __init__(self, form_type: Literal["create", "edit"], current_user: Optional[models.User] = None, experiment: Optional[models.Experiment] = None, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = form_type
        self.__prepare(current_user, experiment)
        if experiment is not None:
            self._context["experiment"] = experiment

    def __prepare(self, user: Optional[models.User], experiment: Optional[models.Experiment]):
        if user is not None:
            self.operator.selected.data = user.id
            self.operator.search_bar.data = user.search_name()

        if experiment is not None:
            self.name.data = experiment.name
            self.workflow.data = experiment.workflow_id
            self.sequencer.selected.data = experiment.sequencer.id
            self.sequencer.search_bar.data = experiment.sequencer.name
            self.r1_cycles.data = experiment.r1_cycles
            self.r2_cycles.data = experiment.r2_cycles
            self.i1_cycles.data = experiment.i1_cycles
            self.i2_cycles.data = experiment.i2_cycles
            self.operator.selected.data = experiment.operator_id
            self.operator.search_bar.data = experiment.operator.search_name()
            self.status.data = experiment.status_id

    def validate(self, experiment: Optional[models.Experiment]) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        try:
            if (e := db.experiments.get(self.name.data)) is not None:  # type: ignore
                if experiment is None or experiment.id != e.id:
                    self.name.errors = ("An experiment with this name already exists.",)
                    return False
        except exceptions.ElementDoesNotExist:
            pass
        
        try:
            ExperimentWorkFlow.get(self.workflow.data)
        except ValueError:
            self.workflow.errors = ("Invalid workflow",)
            return False
        
        try:
            ExperimentStatus.get(self.status.data)
        except ValueError:
            self.status.errors = ("Invalid status",)
            return False
            
        return validated
    
    def __update_existing_experiment(self, experiment: models.Experiment) -> Response:
        workflow = ExperimentWorkFlow.get(self.workflow.data)
        status = ExperimentStatus.get(self.status.data)

        experiment.name = self.name.data  # type: ignore
        experiment.workflow = workflow
        experiment.sequencer_id = self.sequencer.selected.data
        experiment.r1_cycles = self.r1_cycles.data  # type: ignore
        experiment.r2_cycles = self.r2_cycles.data
        experiment.i1_cycles = self.i1_cycles.data  # type: ignore
        experiment.i2_cycles = self.i2_cycles.data
        experiment.operator_id = self.operator.selected.data
        experiment.status = status

        db.experiments.update(experiment)

        flash(f"Edited experiment '{experiment.name}'.", "success")

        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=experiment.id))

    def __create_new_experiment(self) -> Response:
        workflow = ExperimentWorkFlow.get(self.workflow.data)
        status = ExperimentStatus.get(self.status.data)

        experiment = db.experiments.create(
            name=self.name.data,  # type: ignore
            workflow=workflow,
            sequencer_id=self.sequencer.selected.data,
            r1_cycles=self.r1_cycles.data,  # type: ignore
            r2_cycles=self.r2_cycles.data,
            i1_cycles=self.i1_cycles.data,  # type: ignore
            i2_cycles=self.i2_cycles.data,
            operator_id=self.operator.selected.data,
            status=status
        )

        flash(f"Created experiment '{experiment.name}'.", "success")

        return make_response(
            redirect=url_for("experiments_page.experiment", experiment_id=experiment.id),
        )

    def process_request(self, **context) -> Response:
        experiment = context.get("experiment")

        if not self.validate(experiment):
            return self.make_response(**context)
        
        if experiment is not None:
            return self.__update_existing_experiment(experiment)

        return self.__create_new_experiment()
    