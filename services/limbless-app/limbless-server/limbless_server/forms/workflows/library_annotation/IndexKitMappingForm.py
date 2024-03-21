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
from .FeatureKitReferenceInputForm import FeatureKitReferenceInputForm
from .PoolMappingForm import PoolMappingForm
from .BarcodeCheckForm import BarcodeCheckForm
from .VisiumAnnotationForm import VisiumAnnotationForm


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-5.html"

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="library_annotation", uuid=uuid)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        df = self.get_data()["library_table"]

        index_kits = df["index_kit"].unique().tolist()
        index_kits = [index_kit if index_kit and not pd.isna(index_kit) else "Index Kit" for index_kit in index_kits]
        
        for i, entry in enumerate(self.input_fields):
            raw_index_kit_label = index_kits[i]
            _df = df[df["index_kit"] == raw_index_kit_label]
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
                if (_ := db.get_adapter_from_index_kit(adapter_name, index_kit_id)) is None:
                    index_kit_search_field.selected.errors = (f"Unknown adapter '{adapter_name}' does not belong to this index kit.",)
                    return False

        return True
    
    def prepare(self, data: Optional[dict[str, pd.DataFrame | dict]] = None) -> dict:
        if data is None:
            data = self.get_data()

        df: pd.DataFrame = data["library_table"]  # type: ignore

        if "index_kit" not in df.columns:
            df["index_kit"] = None

        index_kits = df["index_kit"].unique().tolist()
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

        self.update_data(data)

        return {
            "categories": index_kits,
            "selected": selected
        }
    
    def __parse(self) -> dict[str, pd.DataFrame | dict]:
        data = self.get_data()
        df: pd.DataFrame = data["library_table"]  # type: ignore

        df["index_kit_name"] = None
        df["index_kit_id"] = None

        index_kits = df["index_kit"].unique().tolist()
        index_kits = [index_kit if index_kit and not pd.isna(index_kit) else "Index Kit" for index_kit in index_kits]

        for i, index_kit in enumerate(index_kits):
            entry = self.input_fields[i]
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore

            if (selected_id := index_kit_search_field.selected.data) is not None:
                if (selected_kit := db.get_index_kit(selected_id)) is None:
                    raise Exception(f"Index kit with id '{selected_id}' does not exist.")
                
                df.loc[df["index_kit"] == index_kit, "index_kit_id"] = selected_id
                df.loc[df["index_kit"] == index_kit, "index_kit_name"] = selected_kit.name
                
        if "index_1" not in df.columns:
            df["index_1"] = None

        if "index_2" not in df.columns:
            df["index_2"] = None
            
        if "index_3" not in df.columns:
            df["index_3"] = None

        if "index_4" not in df.columns:
            df["index_4"] = None

        df["index_1"] = df["index_1"].astype(str)
        df["index_2"] = df["index_2"].astype(str)
        df["index_3"] = df["index_3"].astype(str)
        df["index_4"] = df["index_4"].astype(str)

        for i, row in df.iterrows():
            if pd.isnull(row["index_kit_id"]):
                continue
            index_kit_id = int(row["index_kit_id"])
            adapter_name = str(row["adapter"])
            adapter = db.get_adapter_from_index_kit(adapter_name, index_kit_id)
            df.at[i, "index_1"] = adapter.barcode_1.sequence if adapter.barcode_1 else None
            df.at[i, "index_2"] = adapter.barcode_2.sequence if adapter.barcode_2 else None
            df.at[i, "index_3"] = adapter.barcode_3.sequence if adapter.barcode_3 else None
            df.at[i, "index_4"] = adapter.barcode_4.sequence if adapter.barcode_4 else None
            
        data["library_table"] = df
        self.update_data(data)

        return data
        
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        data = self.__parse()

        if data["library_table"]["library_type_id"].isin([
            LibraryType.MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(uuid=self.uuid)
            context = cmo_reference_input_form.prepare(data) | context
            return cmo_reference_input_form.make_response(**context)
        
        if (data["library_table"]["library_type_id"].isin([
            LibraryType.ANTIBODY_CAPTURE.id,
        ])).any():
            feature_kit_reference_input_form = FeatureKitReferenceInputForm(uuid=self.uuid)
            return feature_kit_reference_input_form.make_response(**context)
        
        if (data["library_table"]["library_type_id"] == LibraryType.SPATIAL_TRANSCRIPTOMIC.id).any():
            visium_annotation_form = VisiumAnnotationForm(uuid=self.uuid)
            return visium_annotation_form.make_response(**context)

        if "pool" in data["library_table"].columns:
            pool_mapping_form = PoolMappingForm(uuid=self.uuid)
            context = pool_mapping_form.prepare(data) | context
            return pool_mapping_form.make_response(**context)

        barcode_check_form = BarcodeCheckForm(uuid=self.uuid)
        context = barcode_check_form.prepare(data) | context
        return barcode_check_form.make_response(**context)