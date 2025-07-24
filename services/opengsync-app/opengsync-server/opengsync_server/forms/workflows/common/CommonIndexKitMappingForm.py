import pandas as pd

from flask import url_for

from opengsync_db import models
from wtforms import StringField, FieldList, FormField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm

from opengsync_db.categories import KitType, BarcodeType

from .... import logger, db  # noqa F401
from ....tools import exceptions
from ...MultiStepForm import MultiStepForm
from ...SearchBar import SearchBar


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[DataRequired()])
    index_kit = FormField(SearchBar, label="Select Index Kit")


class CommonIndexKitMappingForm(MultiStepForm):
    _workflow_name: str
    _step_name = "index_kit_mapping"
    barcode_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return bool(current_step.tables["library_table"]["kit_i7"].notna().any())
    
    def __init__(
        self,
        workflow: str,
        uuid: str | None,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        formdata: dict | None
    ):
        MultiStepForm.__init__(
            self, workflow=workflow,
            step_name=CommonIndexKitMappingForm._step_name, uuid=uuid,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self.pool = pool

        self._url_context = {}
        if seq_request is not None:
            self._context["seq_request"] = seq_request
            self._url_context["seq_request_id"] = seq_request.id
        if lab_prep is not None:
            self._context["lab_prep"] = lab_prep
            self._url_context["lab_prep_id"] = lab_prep.id
        if pool is not None:
            self._context["pool"] = pool
            self._url_context["pool_id"] = pool.id

        self.post_url = url_for("reindex_workflow.map_index_kits", uuid=self.uuid, **self._url_context)
        self.barcode_table = self.tables["barcode_table"]

        if workflow == "library_annotation":
            self.index_col = "library_name"
        else:
            self.index_col = "library_id"

        if self.index_col not in self.barcode_table.columns:
            logger.error(f"Index column '{self.index_col}' not found in columns")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in columns")
        
        self.index_kits = list(set(self.barcode_table["kit_i7"].unique().tolist() + self.barcode_table["kit_i5"].unique().tolist()))
        self.index_kits = [kit for kit in self.index_kits if pd.notna(kit) and kit]
    
    def prepare(self) -> None:
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
            self.index_col: [],
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
                    barcode_table_data[self.index_col].append(row[self.index_col])
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
                barcode_table_data[self.index_col].append(row[self.index_col])
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