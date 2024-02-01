from typing import Type, Optional, Any

from flask import Response, render_template
from flask_htmx import make_response
from flask_wtf import FlaskForm
from werkzeug.datastructures import ImmutableMultiDict

from ..tools import classproperty

from .. import logger


class ExtendedFlaskForm(FlaskForm):
    _template_path: Optional[str] = None

    def __init__(self, formdata: Optional[dict[str, Any]]):
        super().__init__(formdata=ImmutableMultiDict(formdata))

    def process_request(self, **context) -> Response:
        raise NotImplementedError("You must implement this method in your subclass.")
    
    @classproperty
    def template_path(self) -> str:
        if self._template_path is None:
            raise NotImplementedError("You must implement this property in your subclass.")
        return self._template_path

    def make_response(self, **context) -> Response:
        return make_response(
            render_template(
                self.template_path,
                form=self, **context
            ), push_url=False
        )