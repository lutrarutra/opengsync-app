from typing import Optional

from flask import Response, url_for, flash
from wtforms import StringField, SelectField, FloatField
from wtforms.validators import DataRequired, Length

from flask_htmx import make_response

from limbless_db import DBSession, models
from limbless_db.categories import PoolStatus

from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm


class PoolForm(HTMXFlaskForm):
    _template_path = "forms/pool.html"
    _form_label = "pool_form"

    name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)])  # type: ignore
    num_m_reads_requested = FloatField("Number of M Reads Requested", validators=[DataRequired()])
    status = SelectField("Status", choices=PoolStatus.as_selectable(), coerce=int)

    def __init__(self, pool: Optional[models.Pool] = None, formdata=None):
        super().__init__(formdata=formdata)
        self.pool = pool
        if pool is not None:
            self.fill_form(pool)

    def fill_form(self, pool: models.Pool):
        self.name.data = pool.name
        self.status.data = pool.status_id
        self.num_m_reads_requested.data = pool.num_m_reads_requested

    def validate(self) -> bool:
        if not super().validate():
            return False

        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        pool: models.Pool = context["pool"]
        pool.name = self.name.data  # type: ignore
        pool.status_id = PoolStatus.get(self.status.data).id
        pool.num_m_reads_requested = self.num_m_reads_requested.data

        db.update_pool(pool)
        
        flash(f"Edited pool {pool.name}", "success")
        return make_response(redirect=url_for("pools_page.pool_page", pool_id=pool.id),)
        
