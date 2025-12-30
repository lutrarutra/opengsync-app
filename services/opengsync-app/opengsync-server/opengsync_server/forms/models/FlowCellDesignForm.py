from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import ExperimentWorkFlow

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class FlowCellDesignForm(HTMXFlaskForm):
    _template_path = "forms/flow_cell_design.html"

    name = StringField("Name", validators=[DataRequired(), Length(min=1, max=models.FlowCellDesign.name.type.length)])
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[DataRequired()])
    workflow_id = SelectField(
        "Workflow", choices=ExperimentWorkFlow.as_selectable(),
        description="Select the workflow for the experiment.",
        coerce=int, default=None
    )

    def __init__(
        self,
        flow_cell_design: models.FlowCellDesign | None,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.flow_cell_design = flow_cell_design
        self._context["flow_cell_design"] = flow_cell_design


    def prepare(self) -> None:
        if self.flow_cell_design is None:
            return
        
        self.name.data = self.flow_cell_design.name
        self.workflow_id.data = self.flow_cell_design.workflow_id
        self.r1_cycles.data = self.flow_cell_design.cycles_r1
        self.r2_cycles.data = self.flow_cell_design.cycles_r2

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
    
    def __edit_flow_cell_design(self) -> Response:
        if self.flow_cell_design is None:
            raise exceptions.InternalServerErrorException("Flow cell design must be set when editing an existing flow cell design.")

        self.flow_cell_design.name = self.name.data  # type: ignore
        self.flow_cell_design.workflow_id = self.workflow_id.data  # type: ignore
        self.flow_cell_design.cycles_r1 = self.r1_cycles.data  # type: ignore
        self.flow_cell_design.cycles_r2 = self.r2_cycles.data  # type: ignore

        db.session.add(self.flow_cell_design)
        db.flush()
        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("design_page.design"))
    
    def __create_new_flow_cell_design(self) -> Response:
        if self.flow_cell_design is not None:
            raise exceptions.InternalServerErrorException("Flow cell design must be None when creating a new flow cell design.")

        new_flow_cell_design = models.FlowCellDesign(
            name=self.name.data,  # type: ignore
            workflow_id=self.workflow_id.data,  # type: ignore
            cycles_r1=self.r1_cycles.data,  # type: ignore
            cycles_r2=self.r2_cycles.data,  # type: ignore
        )

        db.session.add(new_flow_cell_design)
        db.flush()
        flash("Design Created!", "success")
        return make_response(redirect=url_for("design_page.design"))
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.flow_cell_design is not None:
            return self.__edit_flow_cell_design()
        else:
            return self.__create_new_flow_cell_design()