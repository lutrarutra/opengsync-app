from typing import Optional, TYPE_CHECKING

from flask import Response
from wtforms import FormField, BooleanField

from limbless_db import models

from .... import logger, db  # noqa F401
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar
from .SASInputForm import SASInputForm

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user


class IndexKitSelectForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-1.3.html"
    _form_label = "index_kit_select_form"

    index_1_kit = FormField(OptionalSearchBar, label="Select Index Kit")
    index_2_kit = FormField(OptionalSearchBar, label="Select Index Kit for index 2 (i5) if different from index 1 (i7)")

    custom_indices_used = BooleanField("I used a custom kit that is not in the list and will specify index sequences manually in forward orientation.", default=False)

    def __init__(self, seq_request: models.SeqRequest, formdata: dict = {}, uuid: Optional[str] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = formdata.get("file_uuid")
        TableDataForm.__init__(self, uuid=uuid, dirname="library_annotation")
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.index_1_kit.selected.data and not self.custom_indices_used.data:
            self.index_1_kit.selected.errors = ["Select kit or check the box below."]
            return False
        
        if self.index_1_kit.selected.data and self.custom_indices_used.data:
            self.custom_indices_used.errors = ["Select either a kit or check the box."]
            return False
        
        if self.index_2_kit.selected.data and self.custom_indices_used.data:
            self.custom_indices_used.errors = ["Select either a kit or check the box."]
            return False

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        logger.debug(self.index_1_kit.selected.data)
        sas_input_form = SASInputForm(seq_request=self.seq_request, uuid=self.uuid)
        sas_input_form.metadata["index_1_kit_id"] = self.index_1_kit.selected.data
        sas_input_form.metadata["index_2_kit_id"] = self.index_2_kit.selected.data if self.index_2_kit.selected.data else self.index_1_kit.selected.data
        sas_input_form.update_data()
        sas_input_form.prepare()
        return sas_input_form.make_response()
