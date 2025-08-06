from abc import ABC, abstractmethod
from typing import Optional, Any

from flask import Response, render_template
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms.form import FormMeta

from ..tools import classproperty


class ABCHTMXFlaskForm(FormMeta, ABC):
    pass


class HTMXFlaskForm(FlaskForm, metaclass=ABCHTMXFlaskForm):
    _template_path: Optional[str] = None
    _form_label: str = "form"

    def __init__(self, formdata: Optional[dict[str, Any]] = None, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self.formdata = formdata if formdata is not None else dict()
        if (csrf_token := self.formdata.get("csrf_token")) is None:
            self._csrf_token = self.csrf_token._value()  # type: ignore
        else:
            self._csrf_token = csrf_token
        self._context = {}

    @abstractmethod
    def process_request(self) -> Response:
        ...

    @classproperty
    def template_path(self) -> str:
        if self._template_path is None:
            raise NotImplementedError("You must implement this property in your subclass.")
        return self._template_path
    
    @classproperty
    def form_label(self) -> str:
        return self._form_label
    
    def prepare(self) -> None:
        """Prepare the form for rendering or processing."""
        pass
    
    def get_context(self, **context) -> dict:
        context = context | self._context | {self._form_label: self}
        return context

    def make_response(self, **context) -> Response:
        if not self.formdata:
            self.prepare()
        context = self.get_context(**context)
        return make_response(
            render_template(
                self.template_path, **context
            )
        )