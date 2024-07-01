from wtforms import FormField

from ... import db, logger  # noqa F401
from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import SearchBar


class PoolSelectForm(HTMXFlaskForm):
    _template_path = "workflows/library_pooling/pooling-0.html"
    _form_label = "pool_select_form"

    pool = FormField(SearchBar, label="Select Pool")

    def __init__(self, formdata: dict = {}, context: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["url_context"] = {}
        if (seq_request := context.get("seq_request")) is not None:
            self._context["seq_request"] = seq_request
            self._context["context"] = f"{seq_request.name} ({seq_request.id})"
            self._context["url_context"]["seq_request_id"] = seq_request.id
