from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, IntegerField, SelectField, FormField
from wtforms.validators import DataRequired, Length, NumberRange, Optional as OptionalValidator

from limbless_db import models
from limbless_db.core.categories import FlowCellType
from ..HTMXFlaskForm import HTMXFlaskForm
from ... import db, logger
from ..SearchBar import SearchBar


class ExperimentForm(HTMXFlaskForm):
    _template_path = "forms/experiment.html"
    _form_label = "experiment_form"

    sequencer = FormField(SearchBar, label="Select Sequencer", description="Select the sequencer that will be used for sequencing.")
    flowcell_type = SelectField(
        "Flowcell Type", choices=FlowCellType.as_selectable(),
        description="Type of flowcell to use for sequencing.",
        coerce=int, default=0
    )
    flowcell = StringField("Flowcell ID", validators=[DataRequired(), Length(min=3, max=models.Experiment.flowcell_id.type.length)])  # type: ignore
    num_lanes = IntegerField("Number of Lanes", default=1, validators=[DataRequired(), NumberRange(min=1, max=8)])
    
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[OptionalValidator()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[OptionalValidator()])

    sequencing_person = FormField(SearchBar, label="Sequencing Person")

    def __init__(self, user: Optional[models.User] = None, experiment: Optional[models.Experiment] = None, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.prepare(user, experiment)

    def prepare(self, user: Optional[models.User], experiment: Optional[models.Experiment]):
        if user is not None:
            self.sequencing_person.selected.data = user.id
            self.sequencing_person.search_bar.data = user.search_name()

        if experiment is not None:
            self.flowcell.data = experiment.flowcell_id
            self.sequencer.selected.data = experiment.sequencer.id
            self.sequencer.search_bar.data = experiment.sequencer.name
            self.r1_cycles.data = experiment.r1_cycles
            self.r2_cycles.data = experiment.r2_cycles
            self.i1_cycles.data = experiment.i1_cycles
            self.i2_cycles.data = experiment.i2_cycles
            self.num_lanes.data = experiment.num_lanes
            self.flowcell_type.data = experiment.flowcell_type.id
            self.sequencing_person.selected.data = experiment.sequencing_person_id
            self.sequencing_person.search_bar.data = experiment.sequencing_person.name

    def validate(self) -> bool:
        logger.debug(self.flowcell_type.data)
        if (validated := super().validate()) is False:
            return False
        
        return validated
    
    def __update_existing_experiment(self, experiment: models.Experiment) -> Response:
        experiment.flowcell_id = self.flowcell.data        # type: ignore
        experiment.flowcell_type_id = self.flowcell_type.data
        experiment.r1_cycles = self.r1_cycles.data    # type: ignore
        experiment.r2_cycles = self.r2_cycles.data  # type: ignore
        experiment.i1_cycles = self.i1_cycles.data  # type: ignore
        experiment.i2_cycles = self.i2_cycles.data     # type: ignore
        experiment.num_lanes = self.num_lanes.data   # type: ignore
        experiment.sequencer_id = self.sequencer.selected.data
        experiment.sequencing_person_id = self.sequencing_person.selected.data
        experiment = db.update_experiment(experiment)

        flash(f"Edited experiment on flowcell '{experiment.flowcell_id}'.", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))

    def __create_new_experiment(self) -> Response:
        experiment = db.create_experiment(
            flowcell_id=self.flowcell.data,  # type: ignore
            flowcell_type=FlowCellType.get(self.flowcell_type.data),
            sequencer_id=self.sequencer.selected.data,
            r1_cycles=self.r1_cycles.data,  # type: ignore
            r2_cycles=self.r2_cycles.data,  # type: ignore
            i1_cycles=self.i1_cycles.data,  # type: ignore
            i2_cycles=self.i2_cycles.data,
            num_lanes=self.num_lanes.data,  # type: ignore
            sequencing_person_id=self.sequencing_person.selected.data
        )

        flash(f"Created experiment on flowcell '{experiment.flowcell_id}'.", "success")

        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        )

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        experiment = context.get("experiment")

        if experiment is not None:
            return self.__update_existing_experiment(experiment)

        return self.__create_new_experiment()
    