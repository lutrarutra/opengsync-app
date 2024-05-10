from typing import Any, Optional
from flask import Response
from wtforms import StringField, FormField, IntegerField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from limbless_db import models

from .... import logger, db  # noqa
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .SelectLibrariesForm import SelectLibrariesForm


class DefinePoolForm(HTMXFlaskForm):
    _template_path = "workflows/library_pooling/pooling-1.html"
    _form_label = "library_pooling_form"

    pool_name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)], description="Unique label to identify the pool")  # type: ignore
    seq_request_id = IntegerField(validators=[OptionalValidator()])
    contact_person = FormField(SearchBar, label="Contact Person", description="Who prepared the libraries?")

    def __init__(self, formdata: dict = {}, **kwargs):
        super().__init__(formdata, **kwargs)

    def prepare(self, current_user: models.User, seq_request_id: Optional[int]):
        self.seq_request_id.data = seq_request_id
        self.contact_person.search_bar.data = current_user.search_name()
        self.contact_person.selected.data = current_user.search_value()

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        select_libraries_form = SelectLibrariesForm(seq_request_id=self.seq_request_id.data)
        metadata: dict[str, Any] = dict(
            workflow="library_pooling",
            pool_name=self.pool_name.data,
            contact_person_id=self.contact_person.selected.data,
        )
        if self.seq_request_id.data is not None:
            metadata["seq_request_id"] = self.seq_request_id.data
            self._context["seq_request_id"] = self.seq_request_id.data

        select_libraries_form.metadata = metadata

        select_libraries_form.update_data()
        return select_libraries_form.make_response()