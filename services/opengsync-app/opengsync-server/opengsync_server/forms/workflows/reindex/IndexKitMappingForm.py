from typing import Optional
from flask import Response

import pandas as pd

from flask import url_for, flash
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import BarcodeType, KitType, IndexType, LibraryType

from .... import db, logger
from ...MultiStepForm import MultiStepForm
from ...SearchBar import SearchBar


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class IndexKitMappingForm(MultiStepForm):
    _template_path = "workflows/reindex/index_kit-mapping.html"
    _workflow_name = "reindex"
    _step_name = "index_kit_mapping"

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return current_step.tables["library_table"]["kit_i7"].notna().any()
        
    def __init__(self, uuid: str | None, seq_request: models.SeqRequest | None = None, lab_prep: models.LabPrep | None = None, previous_form: Optional[MultiStepForm] = None, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, workflow=IndexKitMappingForm._workflow_name,
            step_name=IndexKitMappingForm._step_name, uuid=uuid,
            formdata=formdata, previous_form=previous_form, step_args={}
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self._context["seq_request"] = seq_request
        self._context["lab_prep"] = lab_prep
        self._context["url_context"] = {}
        self.barcode_table = self.tables["barcode_table"]
        self.index_kits = list(set(self.barcode_table["kit_i7"].unique().tolist() + self.barcode_table["kit_i5"].unique().tolist()))
        self.index_kits = [kit for kit in self.index_kits if pd.notna(kit) and kit]

        if self.seq_request is not None:
            self.post_url = url_for("reindex_workflow.map_index_kits", uuid=self.uuid, seq_request_id=self.seq_request.id)
        elif self.lab_prep is not None:
            self.post_url = url_for("reindex_workflow.map_index_kits", uuid=self.uuid, lab_prep_id=self.lab_prep.id)
        else:
            self.post_url = url_for("reindex_workflow.map_index_kits", uuid=self.uuid)
        
    def prepare(self):
        for i, index_kit in enumerate(self.index_kits):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry = self.input_fields[i]
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            entry.raw_label.data = index_kit

            if index_kit is None:
                selected_kit = None
            elif index_kit_search_field.selected.data is None:
                selected_kit = next(iter(db.query_kits(str(index_kit), limit=1, kit_type=KitType.INDEX_KIT)), None)
                index_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
            else:
                selected_kit = db.get_index_kit(index_kit_search_field.selected.data)
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        barcode_table = self.barcode_table
        barcode_table["kit_i7_name"] = None
        barcode_table["kit_i5_name"] = None
        barcode_table["kit_i7_id"] = None
        barcode_table["kit_i5_id"] = None
        barcode_table.loc[barcode_table["kit_i7"].notna(), "kit_i7"] = barcode_table.loc[barcode_table["kit_i7"].notna(), "kit_i7"].astype(str)
        barcode_table.loc[barcode_table["kit_i5"].notna(), "kit_i5"] = barcode_table.loc[barcode_table["kit_i5"].notna(), "kit_i5"].astype(str)

        kits: dict[int, tuple[models.IndexKit, pd.DataFrame]] = {}

        for i, entry in enumerate(self.input_fields):
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            if (kit_id := index_kit_search_field.selected.data) is None:
                logger.error(f"Index kit not found for {entry.raw_label.data}")
                raise ValueError()
            
            if (kit := db.get_index_kit(kit_id)) is None:
                index_kit_search_field.selected.errors = (f"Index kit {kit_id} not found",)
                return False

            if len(kit_df := db.get_index_kit_barcodes_df(kit_id, per_adapter=False)) == 0:
                logger.error(f"Index kit {kit_id} does not exist")
                raise ValueError()
            
            kits[kit_id] = (kit, kit_df)
            barcode_table.loc[barcode_table["kit_i7"] == entry.raw_label.data, "kit_i7_id"] = kit_id
            barcode_table.loc[barcode_table["kit_i5"] == entry.raw_label.data, "kit_i5_id"] = kit_id
            barcode_table.loc[barcode_table["kit_i7_id"] == kit_id, "kit_i7_name"] = kit.identifier
            barcode_table.loc[barcode_table["kit_i5_id"] == kit_id, "kit_i5_name"] = kit.identifier

            for _, row in barcode_table[barcode_table["kit_i7_id"] == kit_id].iterrows():
                if pd.notna(row["name_i7"]):
                    if row["name_i7"] not in kit_df["name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i7']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False
                    
            for _, row in barcode_table[barcode_table["kit_i5_id"] == kit_id].iterrows():
                if pd.notna(row["name_i5"]):
                    if row["name_i5"] not in kit_df["name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i5']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False

        kit_defined = self.barcode_table["kit_i7"].notna() | self.barcode_table["kit_i5"].notna()

        barcode_table_data = {
            "library_name": [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
            "kit_i7_id": [],
            "kit_i5_id": [],
            "kit_i7_name": [],
            "kit_i5_name": [],
        }

        for idx, row in barcode_table.iterrows():
            if kit_defined.at[idx]:
                kit_i7, kit_i7_df = kits[row["kit_i7_id"]]
                if pd.isna(row["kit_i5_id"]):
                    kit_i5 = kit_i7
                    kit_i5_df = kit_i7_df
                else:
                    kit_i5, kit_i5_df = kits[row["kit_i5_id"]]

                i7_seqs = kit_i7_df.loc[kit_i7_df["type_id"] == BarcodeType.INDEX_I7.id]
                i5_seqs = kit_i5_df.loc[kit_i5_df["type_id"] == BarcodeType.INDEX_I5.id]

                if pd.notna(row["name_i7"]):
                    barcodes_i7 = i7_seqs[i7_seqs["name"] == row["name_i7"]]["sequence"].values
                    names_i7 = i7_seqs[i7_seqs["name"] == row["name_i7"]]["name"].values
                elif pd.notna(row["index_well"]):
                    barcodes_i7 = i7_seqs[i7_seqs["well"] == row["index_well"]]["sequence"].values
                    names_i7 = i7_seqs[i7_seqs["well"] == row["index_well"]]["name"].values
                else:
                    raise ValueError()
                
                if pd.notna(row["name_i5"]):
                    barcodes_i5 = i5_seqs[i5_seqs["name"] == row["name_i5"]]["sequence"].values
                    names_i5 = i5_seqs[i5_seqs["name"] == row["name_i5"]]["name"].values
                elif pd.notna(row["index_well"]):
                    barcodes_i5 = i5_seqs[i5_seqs["well"] == row["index_well"]]["sequence"].values
                    names_i5 = i5_seqs[i5_seqs["well"] == row["index_well"]]["name"].values
                else:
                    raise ValueError()
                
                for i in range(max(len(barcodes_i7), len(barcodes_i5))):
                    barcode_table_data["library_name"].append(row["library_name"])
                    barcode_table_data["index_well"].append(row["index_well"])
                    barcode_table_data["kit_i7"].append(row["kit_i7"])
                    barcode_table_data["kit_i5"].append(row["kit_i5"])
                    barcode_table_data["kit_i7_id"].append(row["kit_i7_id"])
                    barcode_table_data["kit_i5_id"].append(row["kit_i5_id"])
                    barcode_table_data["kit_i7_name"].append(kit_i7.search_name())
                    barcode_table_data["kit_i5_name"].append(kit_i5.search_name())
                    barcode_table_data["sequence_i7"].append(barcodes_i7[i] if len(barcodes_i7) > i else None)
                    barcode_table_data["sequence_i5"].append(barcodes_i5[i] if len(barcodes_i5) > i else None)
                    barcode_table_data["name_i7"].append(names_i7[i] if len(names_i7) > i else None)
                    barcode_table_data["name_i5"].append(names_i5[i] if len(names_i5) > i else None)
            else:
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["index_well"].append(row["index_well"])
                barcode_table_data["kit_i7"].append(None)
                barcode_table_data["kit_i5"].append(None)
                barcode_table_data["kit_i7_id"].append(None)
                barcode_table_data["kit_i5_id"].append(None)
                barcode_table_data["kit_i7_name"].append(None)
                barcode_table_data["kit_i5_name"].append(None)
                barcode_table_data["sequence_i7"].append(row["sequence_i7"])
                barcode_table_data["sequence_i5"].append(row["sequence_i5"])
                barcode_table_data["name_i7"].append(row["name_i7"])
                barcode_table_data["name_i5"].append(row["name_i5"])
 
        self.barcode_table = pd.DataFrame(barcode_table_data)
        return True
        
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        library_table = self.tables["library_table"]
        
        for i, (idx, row) in enumerate(library_table.iterrows()):
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")

            library = db.remove_library_indices(library_id=library.id)
            df = self.barcode_table[self.barcode_table["library_name"] == row["library_name"]].copy()

            seq_i7s = df["sequence_i7"].values
            seq_i5s = df["sequence_i5"].values
            name_i7s = df["name_i7"].values
            name_i5s = df["name_i5"].values
            kit_i7_ids = df["kit_i7_id"].values
            kit_i5_ids = df["kit_i5_id"].values

            if library.type == LibraryType.TENX_SC_ATAC:
                if len(df) != 4:
                    logger.warning(f"{self.uuid}: Expected 4 barcodes (i7) for TENX_SC_ATAC library, found {len(df)}.")
                index_type = IndexType.TENX_ATAC_INDEX
            else:
                if df["sequence_i5"].isna().all():
                    index_type = IndexType.SINGLE_INDEX
                elif df["sequence_i5"].isna().any():
                    logger.warning(f"{self.uuid}: Mixed index types found for library {df['library_name']}.")
                    index_type = IndexType.DUAL_INDEX
                else:
                    index_type = IndexType.DUAL_INDEX

            library.index_type = index_type
            library = db.update_library(library)

            for j in range(max(len(seq_i7s), len(seq_i5s))):
                library = db.add_library_index(
                    library_id=library.id,
                    index_kit_i7_id=kit_i7_ids[j] if len(kit_i7_ids) > j and pd.notna(kit_i7_ids[j]) else None,
                    index_kit_i5_id=kit_i5_ids[j] if len(kit_i5_ids) > j and pd.notna(kit_i5_ids[j]) else None,
                    name_i7=name_i7s[j] if len(name_i7s) > j and pd.notna(name_i7s[j]) else None,
                    name_i5=name_i5s[j] if len(name_i5s) > j and pd.notna(name_i5s[j]) else None,
                    sequence_i7=seq_i7s[j] if len(seq_i7s) > j and pd.notna(seq_i7s[j]) else None,
                    sequence_i5=seq_i5s[j] if len(seq_i5s) > j and pd.notna(seq_i5s[j]) else None,
                )

        self.complete()

        flash("Libraries Re-Indexed!")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))
        
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id))
        
        return make_response(redirect=url_for("dashboard"))