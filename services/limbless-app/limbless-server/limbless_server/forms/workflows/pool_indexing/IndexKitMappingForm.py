from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import DBSession

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .CompleteLibraryIndexingForm import CompleteLibraryIndexingForm


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/pool_indexing/indexing-2.html"
    _form_label = "pool_indexing_form"

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    def __init__(self, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="pool_indexing", uuid=uuid, previous_form=previous_form)

    def prepare(self):
        barcode_table = self.tables["barcode_table"]

        index_kits = barcode_table["kit"].unique().tolist()

        for i, index_kit in enumerate(index_kits):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            entry.raw_label.data = index_kit

            if index_kit is None:
                selected_kit = None
            elif index_kit_search_field.selected.data is None:
                selected_kit = next(iter(db.query_index_kit(index_kit, 1)), None)
                index_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
            else:
                selected_kit = db.get_index_kit(index_kit_search_field.selected.data)
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None

            logger.debug(entry.raw_label.data)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        barcode_table = self.tables["barcode_table"]
        barcode_table["kit_id"] = None

        with DBSession(db) as session:
            for i, entry in enumerate(self.input_fields):
                raw_index_kit_label = entry.raw_label.data
                _df = barcode_table[barcode_table["kit"] == raw_index_kit_label]
                index_kit_search_field: SearchBar = entry.index_kit  # type: ignore

                if (kit_id := index_kit_search_field.selected.data) is None:
                    if (pd.isna(_df["index_1"]) & pd.isna(_df["index_1"])).any():
                        index_kit_search_field.selected.errors = ("You must specify either an index kit or indices manually",)
                        return False
                    continue
                
                if (kit := session.get_index_kit(kit_id)) is None:
                    index_kit_search_field.selected.errors = ("Not valid index kit selected",)
                    return False
                
                for idx, row in _df.iterrows():
                    adapter_name = str(row["adapter"])
                    if (adapter := session.get_adapter_from_index_kit(adapter=adapter_name, index_kit_id=kit_id)) is None:
                        index_kit_search_field.selected.errors = (f"Unknown adapter '{adapter_name}' does not belong to this index kit.",)
                        return False
                    
                    barcode_table.at[idx, "kit_id"] = kit_id
                    barcode_table.at[idx, "kit_name"] = kit.name
                    barcode_table.at[idx, "index_1"] = adapter.barcode_1.sequence if adapter.barcode_1 else None
                    barcode_table.at[idx, "index_2"] = adapter.barcode_2.sequence if adapter.barcode_2 else None
                    barcode_table.at[idx, "index_3"] = adapter.barcode_3.sequence if adapter.barcode_3 else None
                    barcode_table.at[idx, "index_4"] = adapter.barcode_4.sequence if adapter.barcode_4 else None
                
        self.barcode_table = barcode_table
        return True
        
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        if not self.validate():
            return self.make_response(**context)

        self.update_table("barcode_table", self.barcode_table)

        complete_pool_indexing_form = CompleteLibraryIndexingForm(previous_form=self, uuid=self.uuid)
        complete_pool_indexing_form.prepare()
        return complete_pool_indexing_form.make_response(**context)