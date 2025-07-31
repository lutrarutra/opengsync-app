import pandas as pd

from flask import url_for

from opengsync_db import models
from wtforms import StringField, FieldList, FormField, IntegerField
from wtforms.validators import DataRequired, Optional as OptionalValidator
from flask_wtf import FlaskForm

from opengsync_db.categories import IndexType, BarcodeType
from opengsync_db import exceptions as dbe

from .... import logger, db  # noqa F401
from ....tools import exceptions
from ...MultiStepForm import StepFile
from ...MultiStepForm import MultiStepForm
from ...SearchBar import SearchBar


class IndexKitSubForm(FlaskForm):
    raw_label = StringField("Raw Label", validators=[DataRequired()])
    index_type_id = IntegerField(validators=[OptionalValidator()])
    index_kit = FormField(SearchBar, label="Select Index Kit")
    query_url: str


class CommonIndexKitMappingForm(MultiStepForm):
    _workflow_name: str
    _step_name = "index_kit_mapping"
    barcode_table: pd.DataFrame
    df: pd.DataFrame
    index_col: str

    input_fields = FieldList(FormField(IndexKitSubForm), min_entries=1)

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        if current_step.tables["barcode_table"]["kit_i7"].notna().any():
            return True
        
        if (tenx_atac_barcode_table := current_step.tables.get("tenx_atac_barcode_table")) is not None:
            if tenx_atac_barcode_table["kit"].notna().any():
                return True
        return False
    
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

        self.url_context = {}
        if seq_request is not None:
            self._context["seq_request"] = seq_request
            self.url_context["seq_request_id"] = seq_request.id
        if lab_prep is not None:
            self._context["lab_prep"] = lab_prep
            self.url_context["lab_prep_id"] = lab_prep.id
        if pool is not None:
            self._context["pool"] = pool
            self.url_context["pool_id"] = pool.id

        self.post_url = url_for("reindex_workflow.map_index_kits", uuid=self.uuid, **self.url_context)
        self.barcode_table = self.tables["barcode_table"]
        self.tenx_atac_barcode_table = self.tables.get("tenx_atac_barcode_table", pd.DataFrame(columns=["kit", "index_type_id"]))

        index_kits = self.barcode_table[["kit_i7", "index_type_id"]].drop_duplicates().values.tolist() + self.barcode_table[["kit_i5", "index_type_id"]].drop_duplicates().values.tolist() + self.tenx_atac_barcode_table[["kit", "index_type_id"]].drop_duplicates().values.tolist()
        index_kits = [(name, index_type_id) for name, index_type_id in index_kits if pd.notna(name)]

        data = {
            "label": [],
            "index_type_id": [],
        }

        for name, index_type_id in index_kits:
            data["label"].append(name)
            data["index_type_id"].append(index_type_id)

        self.kit_table = pd.DataFrame(data).drop_duplicates().reset_index(drop=True)
        self.kit_table["kit_id"] = None

        if workflow == "library_annotation":
            self.index_col = "library_name"
        else:
            self.index_col = "library_id"

        if self.index_col not in self.barcode_table.columns:
            logger.error(f"Index column '{self.index_col}' not found in columns")
            raise exceptions.InternalServerErrorException(f"Index column '{self.index_col}' not found in columns")
        
    def prepare(self) -> None:
        for i, (_, row) in enumerate(self.kit_table.iterrows()):
            if i > len(self.input_fields) - 1:
                self.input_fields.append_entry()

            entry: IndexKitSubForm = self.input_fields[i]  # type: ignore
            entry.index_type_id.data = int(row["index_type_id"]) if pd.notna(row["index_type_id"]) else None
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            entry.raw_label.data = row["label"]
            if pd.isna(row["index_type_id"]):
                index_type_in = [IndexType.DUAL_INDEX, IndexType.SINGLE_INDEX]
            else:
                try:
                    index_type_in = [IndexType.get(int(row["index_type_id"]))]
                except ValueError:
                    logger.warning(f"Invalid index type ID {row['index_type_id']} for index kit {row['label']}, defaulting to dual and single index types.")
                    index_type_in = [IndexType.DUAL_INDEX, IndexType.SINGLE_INDEX]

                entry.query_url = url_for("barcodes_htmx.query_index_kits", index_type_id_in=",".join([str(t.id) for t in index_type_in]))

            if pd.notna(row["kit_id"]):
                index_kit_search_field.selected.data = int(row["kit_id"])

            if index_kit_search_field.selected.data is None:
                selected_kit = next(iter(db.query_index_kits(str(row["label"]), limit=1, index_type_in=index_type_in)), None)
                index_kit_search_field.selected.data = selected_kit.id if selected_kit else None
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None
            else:
                selected_kit = db.get_index_kit(index_kit_search_field.selected.data)
                index_kit_search_field.search_bar.data = selected_kit.search_name() if selected_kit else None

    def fill_previous_form(self, previous_form: StepFile):
        kit_table = previous_form.tables["index_kit_table"]
        self.kit_table = kit_table
        logger.debug(self.kit_table)
    
    def validate(self) -> bool:
        if not super().validate():
            return False
        
        barcode_table = self.barcode_table
        self.kit_table["kit_id"] = None
        self.kit_table["kit_name"] = None

        for i, entry in enumerate(self.input_fields):
            index_kit_search_field: SearchBar = entry.index_kit  # type: ignore
            if (kit_id := index_kit_search_field.selected.data) is None:
                logger.error(f"Index kit not found for {entry.raw_label.data}")
                raise dbe.ElementDoesNotExist()
            
            if (kit := db.get_index_kit(kit_id)) is None:
                index_kit_search_field.selected.errors = (f"Index kit {kit_id} not found",)
                return False
            
            if len(kit_df := db.get_index_kit_barcodes_df(kit_id, per_adapter=False)) == 0:
                logger.error(f"No barcodes found for index kit {kit_id}")
                raise dbe.LinkDoesNotExist()
            
            self.kit_table.at[i, "kit_id"] = kit_id
            self.kit_table.at[i, "kit_name"] = kit.search_name()
            self.kit_table.at[i, "kit_type_id"] = kit.type.id

            for _, row in barcode_table[barcode_table["kit_i7_id"] == kit_id].iterrows():
                if pd.notna(row["name_i7"]):
                    if row["name_i7"] not in kit_df["kit_name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i7']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False
                    
            for _, row in barcode_table[barcode_table["kit_i5_id"] == kit_id].iterrows():
                if pd.notna(row["name_i5"]):
                    if row["name_i5"] not in kit_df["kit_name"].values:
                        index_kit_search_field.selected.errors = (f"Index {row['name_i5']} not found in index kit {kit_id}",)
                        return False
                
                elif pd.notna(row["index_well"]):
                    if row["index_well"] not in kit_df["well"].values:
                        index_kit_search_field.selected.errors = (f"Well {row['index_well']} not found in index kit {kit_id}",)
                        return False

        return True
    
    def fill_barcode_table(self) -> pd.DataFrame:
        barcode_table = self.barcode_table
        barcode_table["kit_i7_id"] = None
        barcode_table["kit_i5_id"] = None
        tenx_atac_barcode_table = self.tenx_atac_barcode_table
        tenx_atac_barcode_table["kit_id"] = None

        for _, kit_row in self.kit_table.iterrows():
            kit_label = kit_row["label"]
            kit_id = int(kit_row["kit_id"])

            if (kit := db.get_index_kit(kit_id)) is None:
                logger.error(f"Index kit {kit_id} not found")
                raise dbe.ElementDoesNotExist(f"Index kit {kit_id} not found")

            if len(kit_df := db.get_index_kit_barcodes_df(kit_id, per_adapter=False, per_index=True)) == 0:
                logger.error(f"No barcodes found for index kit {kit_id}")
                raise dbe.LinkDoesNotExist()
            
            if kit.type == IndexType.TENX_ATAC_INDEX:
                tenx_atac_barcode_table.loc[tenx_atac_barcode_table["kit"] == kit_label, "kit_id"] = kit_id
            else:
                barcode_table.loc[barcode_table["kit_i7"] == kit_label, "kit_i7_id"] = kit_id
                barcode_table.loc[barcode_table["kit_i5"] == kit_label, "kit_i5_id"] = kit_id
                barcode_table.loc[barcode_table["kit_i7"] == kit_label, "index_type_id"] = kit.type_id
                barcode_table.loc[barcode_table["kit_i5"] == kit_label, "index_type_id"] = kit.type_id

            for _, kit_row in kit_df.iterrows():
                if kit.type == IndexType.TENX_ATAC_INDEX:
                    tenx_atac_barcode_table.loc[
                        (tenx_atac_barcode_table["kit"] == kit_label) &
                        (tenx_atac_barcode_table["index_well"] == kit_row["well"]), "name"
                    ] = kit_row["name"]

                    for col in ["sequence_1", "sequence_2", "sequence_3", "sequence_4"]:
                        tenx_atac_barcode_table.loc[
                            (tenx_atac_barcode_table["kit"] == kit_label) &
                            (tenx_atac_barcode_table["index_well"] == kit_row["well"]), col
                        ] = kit_row[col]

                        tenx_atac_barcode_table.loc[
                            (tenx_atac_barcode_table["kit"] == kit_label) &
                            (tenx_atac_barcode_table["name"] == kit_row["name"]), col
                        ] = kit_row[col]

                else:
                    barcode_table.loc[
                        (barcode_table["kit_i7"] == kit_label) &
                        (barcode_table["index_well"] == kit_row["well"]), "name_i7"
                    ] = kit_row["name_i7"]

                    barcode_table.loc[
                        (barcode_table["kit_i7"] == kit_label) &
                        (barcode_table["index_well"] == kit_row["well"]), "sequence_i7"
                    ] = kit_row["sequence_i7"]

                    barcode_table.loc[
                        (barcode_table["kit_i7"] == kit_label) &
                        (barcode_table["name_i7"] == kit_row["name_i7"]), "sequence_i7"
                    ] = kit_row["sequence_i7"]

                    if kit.type == IndexType.DUAL_INDEX:
                        barcode_table.loc[
                            (barcode_table["kit_i5"] == kit_label) &
                            (barcode_table["index_well"] == kit_row["well"]), "name_i5"
                        ] = kit_row["name_i5"]

                        barcode_table.loc[
                            (barcode_table["kit_i5"] == kit_label) &
                            (barcode_table["index_well"] == kit_row["well"]), "sequence_i5"
                        ] = kit_row["sequence_i5"]

                        barcode_table.loc[
                            (barcode_table["kit_i5"] == kit_label) &
                            (barcode_table["name_i5"] == kit_row["name_i5"]), "sequence_i5"
                        ] = kit_row["sequence_i5"]
        
        data = {
            self.index_col: [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i7_id": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
            "kit_i5_id": [],
            "index_type_id": [],
        }

        for _, row in barcode_table.iterrows():
            data[self.index_col].append(row[self.index_col])
            data["index_well"].append(row["index_well"])
            data["kit_i7"].append(row["kit_i7"])
            data["name_i7"].append(row["name_i7"])
            data["sequence_i7"].append(row["sequence_i7"])
            data["kit_i7_id"].append(row["kit_i7_id"])
            data["kit_i5"].append(row["kit_i5"])
            data["name_i5"].append(row["name_i5"])
            data["sequence_i5"].append(row["sequence_i5"])
            data["kit_i5_id"].append(row["kit_i5_id"])
            data["index_type_id"].append(row["index_type_id"])

        for _, row in tenx_atac_barcode_table.iterrows():
            for col in ["sequence_1", "sequence_2", "sequence_3", "sequence_4"]:
                data[self.index_col].append(row[self.index_col])
                data["index_well"].append(row["index_well"])
                data["kit_i7"].append(row["kit"])
                data["name_i7"].append(row["name"])
                data["sequence_i7"].append(row[col])
                data["kit_i7_id"].append(row["kit_id"])
                data["kit_i5"].append(None)
                data["name_i5"].append(None)
                data["sequence_i5"].append(None)
                data["kit_i5_id"].append(None)
                data["index_type_id"].append(IndexType.TENX_ATAC_INDEX.id)

        df = barcode_table.set_index(self.index_col)
        barcode_table = pd.DataFrame(data)

        for col in df.columns:
            if col not in barcode_table.columns:
                barcode_table[col] = df.loc[barcode_table[self.index_col], col].values
        
        if self._workflow_name == "library_pooling":
            missing = (barcode_table["sequence_i7"].isna() & ~barcode_table["pool"].astype(str).str.strip().str.lower().isin(["x", "t"])).any()
        else:
            missing = barcode_table["sequence_i7"].isna().any()
        
        if missing:
            logger.error("Missing i7 sequences in barcode table after index kit mapping")
            logger.error(barcode_table)
            raise exceptions.InternalServerErrorException("Missing i7 sequences in barcode table after index kit mapping")
        
        return barcode_table