from typing import Optional
from flask import Response
import pandas as pd

from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import LibraryType

from .... import db
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .CMOReferenceInputForm import CMOReferenceInputForm
from .FeatureReferenceInputForm import FeatureReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .CompleteSASForm import CompleteSASForm
from .FRPAnnotationForm import FRPAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-5.html"

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    def __init__(self, seq_request: models.SeqRequest, previous_form: Optional[TableDataForm] = None, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid, previous_form=previous_form)
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        library_table = self.tables["library_table"]

        index_kits = library_table["index_kit"].unique().tolist()
        index_kits = [index_kit if index_kit and not pd.isna(index_kit) else "Index Kit" for index_kit in index_kits]
        
        for i, entry in enumerate(self.input_fields):
            raw_index_kit_label = index_kits[i]
            _df = library_table[library_table["index_kit"] == raw_index_kit_label]
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore

            if (index_kit_id := index_kit_search_field.selected.data) is None:
                if (pd.isnull(_df["index_1"]) & pd.isnull(_df["index_1"])).any():
                    index_kit_search_field.selected.errors = ("You must specify either an index kit or indices manually",)
                    return False
                continue
            
            if db.get_index_kit(index_kit_id) is None:
                index_kit_search_field.selected.errors = ("Not valid index kit selected",)
                return False
            
            for _, row in _df.iterrows():
                adapter_name = str(row["adapter"])
                if (_ := db.get_adapter_from_index_kit(index_kit_id=index_kit_id, adapter=adapter_name)) is None:
                    index_kit_search_field.selected.errors = (f"Unknown adapter '{adapter_name}' does not belong to this index kit.",)
                    return False

        return True
    
    def prepare(self):
        library_table = self.tables["library_table"]

        index_kits = library_table["index_kit"].unique().tolist()
        index_kits = [index_kit if index_kit and not pd.isna(index_kit) else None for index_kit in index_kits]

        selected: list[Optional[models.IndexKit]] = []

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

            selected.append(selected_kit)

        # TODO: these can be removed, right?
        self._context["categories"] = index_kits
        self._context["selected"] = selected
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        library_table = self.tables["library_table"]

        library_table["index_kit_name"] = None
        library_table["index_kit_id"] = None

        index_kits = library_table["index_kit"].unique().tolist()
        index_kits = [index_kit if index_kit and not pd.isna(index_kit) else "Index Kit" for index_kit in index_kits]

        for i, index_kit in enumerate(index_kits):
            entry = self.input_fields[i]
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore

            if (selected_id := index_kit_search_field.selected.data) is not None:
                if (selected_kit := db.get_index_kit(selected_id)) is None:
                    raise Exception(f"Index kit with id '{selected_id}' does not exist.")
                
                library_table.loc[library_table["index_kit"] == index_kit, "index_kit_id"] = selected_id
                library_table.loc[library_table["index_kit"] == index_kit, "index_kit_name"] = selected_kit.name
                
        if "index_1" not in library_table.columns:
            library_table["index_1"] = None

        if "index_2" not in library_table.columns:
            library_table["index_2"] = None
            
        if "index_3" not in library_table.columns:
            library_table["index_3"] = None

        if "index_4" not in library_table.columns:
            library_table["index_4"] = None

        library_table["index_1"] = library_table["index_1"].astype(str)
        library_table["index_2"] = library_table["index_2"].astype(str)
        library_table["index_3"] = library_table["index_3"].astype(str)
        library_table["index_4"] = library_table["index_4"].astype(str)

        for i, row in library_table.iterrows():
            if pd.isnull(row["index_kit_id"]):
                continue
            index_kit_id = int(row["index_kit_id"])
            adapter_name = str(row["adapter"])
            adapter = db.get_adapter_from_index_kit(index_kit_id=index_kit_id, adapter=adapter_name)
            library_table.at[i, "index_1"] = adapter.barcode_1.sequence if adapter.barcode_1 else None
            library_table.at[i, "index_2"] = adapter.barcode_2.sequence if adapter.barcode_2 else None
            library_table.at[i, "index_3"] = adapter.barcode_3.sequence if adapter.barcode_3 else None
            library_table.at[i, "index_4"] = adapter.barcode_4.sequence if adapter.barcode_4 else None
            
        self.update_table("library_table", library_table)
        self.update_data()

        if library_table["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (library_table["library_type_id"].isin([
            LibraryType.ANTIBODY_CAPTURE.id,
        ])).any():
            feature_reference_input_form = FeatureReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return feature_reference_input_form.make_response()
        
        if (library_table["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if LibraryType.TENX_FLEX.id in library_table["library_type_id"].values and "pool" in library_table.columns:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            frp_annotation_form.prepare()
            return frp_annotation_form.make_response()

        if "pool" in library_table.columns:
            pool_mapping_form = PoolMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            pool_mapping_form.prepare()
            return pool_mapping_form.make_response()

        complete_sas_form = CompleteSASForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        complete_sas_form.prepare()
        return complete_sas_form.make_response()