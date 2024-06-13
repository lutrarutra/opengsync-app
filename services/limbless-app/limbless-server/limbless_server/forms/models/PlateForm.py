from typing import Optional, Literal

from flask import Response, url_for, flash
from wtforms import StringField, IntegerField, SelectField
from wtforms.validators import DataRequired, Length

from flask_htmx import make_response

from limbless_db import models, DBSession
from limbless_db.categories import PoolType

from ... import logger, db  # noqa F401
from ..HTMXFlaskForm import HTMXFlaskForm


class PlateForm(HTMXFlaskForm):
    _template_path = "forms/plate.html"
    _form_label = "plate_form"

    name = StringField("Plate Name", validators=[DataRequired(), Length(min=2, max=models.Plate.name.type.length)])
    num_cols = IntegerField("Number of Columns", validators=[DataRequired()], default=12)
    num_rows = IntegerField("Number of Rows", validators=[DataRequired()], default=8)
    orientation = SelectField("Orientation", choices=[("default", "Default"), ("flipped", "Flipped")], default="default")

    def __init__(self, form_type: Literal["edit", "create"], formdata=None, pool: Optional[models.Pool] = None):
        super().__init__(formdata=formdata)
        self.form_type = form_type
        self.pool = pool
        self._context["form_type"] = form_type
        self._context["pool"] = pool
        self._context["identifiers"] = dict([(pool_type.id, pool_type.identifier) for pool_type in PoolType.as_list()])

    def validate(self) -> bool:
        if not super().validate():
            return False

        return True

    def prepare(self):
        if self.pool is not None:
            self.name.data = self.pool.name

    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        flipped = self.orientation.data == "flipped"

        plate = db.create_plate(
            name=self.name.data,  # type: ignore
            num_cols=self.num_cols.data,  # type: ignore
            num_rows=self.num_rows.data,  # type: ignore
            pool_id=self.pool.id if self.pool else None,
            owner_id=user.id
        )

        def get_well(i: int) -> str:
            return plate.get_well(i, flipped=flipped)

        if self.pool is not None:
            with DBSession(db) as session:
                libraries, _ = db.get_libraries(pool_id=self.pool.id, limit=None, sort_by="id")
                for i, library in enumerate(libraries):
                    session.add_library_to_plate(
                        plate_id=plate.id, library_id=library.id, well=get_well(i)
                    )

            flash(f"Plate {plate.name} created", "success")
            return make_response(redirect=url_for("pools_page.pool_page", pool_id=self.pool.id))
        
        raise NotImplementedError("Creating plates without a pool is not yet supported")