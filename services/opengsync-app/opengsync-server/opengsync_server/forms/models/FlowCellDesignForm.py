from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length

from opengsync_db import models, categories as cats

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class FlowCellDesignForm(HTMXFlaskForm):
    _template_path = "forms/flow_cell_design.html"

    name = StringField("Name", validators=[DataRequired(), Length(min=1, max=models.FlowCellDesign.name.type.length)])
    flow_cell_type_id = SelectField("Flow Cell Type", coerce=int, choices=[(-1, "-")] + cats.FlowCellType.as_selectable())

    def __init__(
        self, flow_cell_design: models.FlowCellDesign | None, formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.flow_cell_design = flow_cell_design
        self._context["flow_cell_design"] = flow_cell_design


    def prepare(self) -> None:
        if self.flow_cell_design is None:
            return
        
        self.name.data = self.flow_cell_design.name
        self.flow_cell_type_id.data = self.flow_cell_design.flow_cell_type_id or -1

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.flow_cell_type_id.data != -1:
            try:
                cats.FlowCellType.get(self.flow_cell_type_id.data)
            except ValueError:
                self.flow_cell_type_id.errors = ("Invalid flow cell type selected.",)
                return False
        
        return True
    
    def __edit_flow_cell_design(self) -> Response:
        if self.flow_cell_design is None:
            raise exceptions.InternalServerErrorException("Flow cell design must be set when editing an existing flow cell design.")

        self.flow_cell_design.name = self.name.data  # type: ignore
        self.flow_cell_design.flow_cell_type_id = self.flow_cell_type_id.data if self.flow_cell_type_id.data != -1 else None

        db.session.add(self.flow_cell_design)
        db.flush()
        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("design_page.design"))
    
    def __create_new_flow_cell_design(self) -> Response:
        if self.flow_cell_design is not None:
            raise exceptions.InternalServerErrorException("Flow cell design must be None when creating a new flow cell design.")

        new_flow_cell_design = models.FlowCellDesign(
            name=self.name.data,
            flow_cell_type_id=self.flow_cell_type_id.data if self.flow_cell_type_id.data != -1 else None
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