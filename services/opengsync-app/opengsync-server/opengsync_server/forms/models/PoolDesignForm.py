from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, FloatField, IntegerField
from wtforms.validators import DataRequired, Length

from opengsync_db import models

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class PoolDesignForm(HTMXFlaskForm):
    _template_path = "forms/pool_design.html"

    pool_design_name = StringField("Name", validators=[DataRequired(), Length(min=1, max=models.PoolDesign.name.type.length)], description="Name of the pool design.")
    r1_cycles = IntegerField("R1 Cycles", validators=[DataRequired()])
    i1_cycles = IntegerField("I1 Cycles", validators=[DataRequired()])
    i2_cycles = IntegerField("I2 Cycles", validators=[DataRequired()])
    r2_cycles = IntegerField("R2 Cycles", validators=[DataRequired()])
    num_requested_reads_millions = FloatField("Number of Requested Reads (Millions)", validators=[DataRequired()], description="Number of requested reads in millions for the pool design.")

    def __init__(
        self,
        pool_design: models.PoolDesign | None,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        self.pool_design = pool_design
        self._context["pool_design"] = pool_design
        
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True

    def __edit_existing_pool_design(self) -> Response:
        if self.pool_design is None:
            raise exceptions.InternalServerErrorException("Pool design must be set when editing an existing pool design.")

        self.pool_design.name = self.pool_design_name.data  # type: ignore
        self.pool_design.num_requested_reads_millions = self.num_requested_reads_millions.data  # type: ignore
        self.pool_design.cycles_r1 = self.r1_cycles.data  # type: ignore
        self.pool_design.cycles_i1 = self.i1_cycles.data  # type: ignore
        self.pool_design.cycles_r2 = self.r2_cycles.data  # type: ignore
        self.pool_design.cycles_i2 = self.i2_cycles.data  # type: ignore

        db.session.add(self.pool_design)
        db.flush()
        flash("Changes Saved!", "success")
        return make_response(redirect=url_for("design_page.design"))

    def __create_new_pool_design(self) -> Response:
        new_pool_design = db.pool_designs.create(
            name=self.pool_design_name.data,  # type: ignore
            num_m_requested_reads=self.num_requested_reads_millions.data,  # type: ignore
            cycles_r1=self.r1_cycles.data,  # type: ignore
            cycles_i1=self.i1_cycles.data,  # type: ignore
            cycles_r2=self.r2_cycles.data,  # type: ignore
            cycles_i2=self.i2_cycles.data,  # type: ignore
        )

        db.session.add(new_pool_design)
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
        


