from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, FloatField
from wtforms.validators import DataRequired, Length

from opengsync_db import models

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class PoolDesignForm(HTMXFlaskForm):
    _template_path = "forms/pool_design.html"

    name = StringField("Name", validators=[DataRequired(), Length(min=1, max=models.PoolDesign.name.type.length)], description="Name of the pool design.")
    num_requested_reads_millions = FloatField("Number of Requested Reads (Millions)", validators=[DataRequired()], description="Number of requested reads in millions for the pool design.")

    def __init__(
        self,
        flow_cell_design: models.FlowCellDesign,
        pool_design: models.PoolDesign | None,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.pool_design = pool_design
        self.flow_cell_design = flow_cell_design
        self._context["pool_design"] = pool_design
        self._context["flow_cell_design"] = flow_cell_design

    def prepare(self) -> None:
        if self.pool_design is None:
            return
        
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
    

    def __edit_existing_pool_design(self) -> Response:
        if self.pool_design is None:
            raise exceptions.InternalServerErrorException("Pool design must be set when editing an existing pool design.")

        self.pool_design.name = self.name.data  # type: ignore
        self.pool_design.num_requested_reads_millions = self.num_requested_reads_millions.data  # type: ignore

        db.session.add(self.pool_design)
        db.flush()
        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("design_page.design"))

    def __create_new_pool_design(self) -> Response:
        new_pool_design = models.PoolDesign(
            name=self.name.data,  # type: ignore
            num_m_requested_reads=self.num_requested_reads_millions.data,  # type: ignore
        )
        self.flow_cell_design.pool_design_links.append(
            models.links.DesignPoolFlowCellLink(
                flow_cell_design=self.flow_cell_design,
                pool_design=new_pool_design,
                lane_num=1
            )
        )

        db.session.add(self.flow_cell_design)
        db.flush()
        flash("Design Created!", "success")
        return make_response(redirect=url_for("design_page.design"))
    

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.pool_design is None:
            return self.__create_new_pool_design()
        else:
            return self.__edit_existing_pool_design()
        


