from flask import Response, flash, render_template
from flask_htmx import make_response
from wtforms import SelectField

from opengsync_db import models
from opengsync_db.categories import ProjectStatus

from ... import logger, db
from ...core import exceptions
from ..HTMXFlaskForm import HTMXFlaskForm


class APITokenForm(HTMXFlaskForm):
    _template_path = "forms/auth/api_token.html"

    time_valid_min = SelectField("Link Validity Period: ", choices=[
        (60 * 24 * 30, "1 Month"),
        (60 * 24 * 30 * 3, "3 Months"),
        (60 * 24 * 30 * 6, "6 Months"),
        (60 * 24 * 365, "1 Year"),
    ], default=60 * 24 * 365, coerce=int)

    def __init__(
        self,
        user: models.User,
        formdata: dict | None = None,

    ):
        super().__init__(formdata=formdata)
        self.user = user
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        return True
    
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        token = db.api_tokens.create(
            owner=self.user,
            time_valid_min=self.time_valid_min.data
        )

        return make_response(render_template("forms/auth/api_token_complete.html", token=token))
