from flask import Response

from flask_wtf import FlaskForm
from wtforms import StringField, FormField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_server.forms.MultiStepForm import StepFile

from .... import db, logger
from ...MultiStepForm import MultiStepForm
from ...SearchBar import SearchBar
from ..common import CommonIndexKitMappingForm
from .CompleteLibraryPoolingForm import CompleteLibraryPoolingForm


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(CommonIndexKitMappingForm):
    _template_path = "workflows/library_pooling/index_kit-mapping.html"
    _workflow_name = "library_pooling"
    lab_prep: models.LabPrep
        
    def __init__(
        self,
        lab_prep: models.LabPrep,
        formdata: dict | None,
        uuid: str | None = None
    ):
        CommonIndexKitMappingForm.__init__(
            self, uuid=uuid, workflow=IndexKitMappingForm._workflow_name,
            formdata=formdata,
            pool=None, lab_prep=lab_prep, seq_request=None
        )

    def fill_previous_form(self, previous_form: StepFile):
        barcode_table = previous_form.tables["barcode_table"]

        kits = set()

        counter = 0
        for (label, kit_id,), _ in barcode_table.groupby(["kit_i7", "kit_i7_id"]):
            if label in kits:
                continue
            kits.add(label)
            if counter > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry: IndexKitSubForm = self.input_fields[counter]  # type: ignore
            entry.raw_label.data = label
            entry.index_kit.selected.data = kit_id
            entry.index_kit.search_bar.data = label
            counter += 1

        for (label, kit_id), _ in barcode_table.groupby(["kit_i5", "kit_i5_id"]):
            if label in kits:
                continue
            kits.add(label)
            if counter > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry: IndexKitSubForm = self.input_fields[counter]  # type: ignore
            entry.raw_label.data = label
            entry.index_kit.selected.data = kit_id
            entry.index_kit.search_bar.data = label
            counter += 1

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.barcode_table = self.fill_barcode_table()
        self.update_table("barcode_table", self.barcode_table)
        
        complete_pool_indexing_form = CompleteLibraryPoolingForm(lab_prep=self.lab_prep, uuid=self.uuid)
        return complete_pool_indexing_form.make_response()