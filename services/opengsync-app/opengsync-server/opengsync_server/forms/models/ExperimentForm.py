from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, IntegerField, SelectField, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models, exceptions
from opengsync_db.categories import ExperimentWorkFlow, ExperimentStatus
from ..HTMXFlaskForm import HTMXFlaskForm

from ... import db, logger
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

    def __init__(self, current_user: models.User, experiment: models.Experiment | None = None, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = "create" if experiment is None else "edit"
        self.experiment = experiment
        if not formdata:
            self.__prepare(current_user)
        if experiment is not None:
            self._context["experiment"] = experiment

    def __prepare(self, user: models.User):
        if user is not None:
            self.operator.selected.data = user.id
            self.operator.search_bar.data = user.search_name()

        if self.experiment is not None:
            self.name.data = self.experiment.name
            self.workflow.data =  self.experiment.workflow_id
            self.sequencer.selected.data =  self.experiment.sequencer.id
            self.sequencer.search_bar.data =  self.experiment.sequencer.name
            self.r1_cycles.data =  self.experiment.r1_cycles
            self.r2_cycles.data =  self.experiment.r2_cycles
            self.i1_cycles.data =  self.experiment.i1_cycles
            self.i2_cycles.data =  self.experiment.i2_cycles
            self.operator.selected.data =  self.experiment.operator_id
            self.operator.search_bar.data =  self.experiment.operator.search_name()
            self.status.data =  self.experiment.status_id

    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        try:
            if (e := db.experiments.get(self.name.data)) is not None:  # type: ignore
                if self.experiment is None or  self.experiment.id != e.id:
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
    
    def __update_existing_experiment(self) -> Response:
        if self.experiment is None:
            raise ValueError("No experiment provided for update.")
        workflow = ExperimentWorkFlow.get(self.workflow.data)
        status = ExperimentStatus.get(self.status.data)

        self.experiment.name = self.name.data  # type: ignore
        self.experiment.workflow = workflow
        self.experiment.sequencer_id = self.sequencer.selected.data
        self.experiment.r1_cycles = self.r1_cycles.data  # type: ignore
        self.experiment.r2_cycles = self.r2_cycles.data
        self.experiment.i1_cycles = self.i1_cycles.data  # type: ignore
        self.experiment.i2_cycles = self.i2_cycles.data
        self.experiment.operator_id = self.operator.selected.data
        self.experiment.status = status

        logger.debug(self.experiment.name)
        logger.debug(self.name.data)

        db.experiments.update(self.experiment)

        flash(f"Changes Saved!.", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))

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

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.form_type == "edit":
            return self.__update_existing_experiment()

        return self.__create_new_experiment()
    