from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, IntegerField, SelectField, FormField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import FlowCellType, SequencingWorkFlowType
from ..HTMXFlaskForm import HTMXFlaskForm
from ... import db
from ..SearchBar import SearchBar


class ExperimentForm(HTMXFlaskForm):
    _template_path = "forms/experiment.html"
    _form_label = "experiment_form"

    name = StringField("Experiment Name", validators=[DataRequired(), Length(min=3, max=models.Experiment.name.type.length)])
    sequencer = FormField(SearchBar, label="Select Sequencer", description="Select the sequencer that will be used for sequencing.")

    workflow_type = SelectField(
        "Workflow Type", choices=SequencingWorkFlowType.as_selectable(),
        description="Select the workflow type for the experiment.",
        coerce=int, default=None
    )
    
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[OptionalValidator()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[OptionalValidator()])

    operator = FormField(SearchBar, label="Sequencer Operator")

    def __init__(self, user: Optional[models.User] = None, experiment: Optional[models.Experiment] = None, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.prepare(user, experiment)

    def prepare(self, user: Optional[models.User], experiment: Optional[models.Experiment]):
        if user is not None:
            self.operator.selected.data = user.id
            self.operator.search_bar.data = user.search_name()

        if experiment is not None:
            self.name.data = experiment.name
            self.workflow_type.data = experiment.workflow_id
            self.sequencer.selected.data = experiment.sequencer.id
            self.sequencer.search_bar.data = experiment.sequencer.name
            self.r1_cycles.data = experiment.r1_cycles
            self.r2_cycles.data = experiment.r2_cycles
            self.i1_cycles.data = experiment.i1_cycles
            self.i2_cycles.data = experiment.i2_cycles
            self.operator.selected.data = experiment.operator_id
            self.operator.search_bar.data = experiment.operator.search_name()

    def validate(self, experiment: Optional[models.Experiment]) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        if (e := db.get_experiment(name=self.name.data)) is not None:
            if experiment is None or experiment.id != e.id:
                self.name.errors = ("An experiment with this name already exists.",)
                return False
        
        return validated
    
    def __update_existing_experiment(self, experiment: models.Experiment) -> Response:
        workflow_type = SequencingWorkFlowType.get(self.workflow_type.data)
        experiment.name = self.name.data  # type: ignore
        experiment.flowcell_type_id = workflow_type.flow_cell_type.id
        experiment.r1_cycles = self.r1_cycles.data    # type: ignore
        experiment.r2_cycles = self.r2_cycles.data  # type: ignore
        experiment.i1_cycles = self.i1_cycles.data  # type: ignore
        experiment.i2_cycles = self.i2_cycles.data     # type: ignore
        experiment.sequencer_id = self.sequencer.selected.data
        experiment.operator_id = self.operator.selected.data
        experiment.workflow_id = workflow_type.id
        experiment = db.update_experiment(experiment)

        flash(f"Edited experiment '{experiment.name}'.", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))

    def __create_new_experiment(self) -> Response:
        workflow_type = SequencingWorkFlowType.get(self.workflow_type.data)
        experiment = db.create_experiment(
            name=self.name.data,  # type: ignore
            flowcell_type=workflow_type.flow_cell_type,
            workflow_type=workflow_type,
            sequencer_id=self.sequencer.selected.data,
            r1_cycles=self.r1_cycles.data,  # type: ignore
            r2_cycles=self.r2_cycles.data,
            i1_cycles=self.i1_cycles.data,  # type: ignore
            i2_cycles=self.i2_cycles.data,
            num_lanes=workflow_type.flow_cell_type.num_lanes,
            operator_id=self.operator.selected.data,
        )

        for lane_num in range(1, workflow_type.flow_cell_type.num_lanes + 1):
            db.create_lane(lane_num, experiment.id)

        flash(f"Created experiment '{experiment.name}'.", "success")

        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        )

    def process_request(self, **context) -> Response:
        experiment = context.get("experiment")

        if not self.validate(experiment):
            return self.make_response(**context)
        
        if experiment is not None:
            return self.__update_existing_experiment(experiment)

        return self.__create_new_experiment()
    