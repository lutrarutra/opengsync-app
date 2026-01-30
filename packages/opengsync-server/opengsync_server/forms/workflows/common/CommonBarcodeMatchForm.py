import pandas as pd

from flask import url_for
from wtforms import SelectField, RadioField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import IndexType, IndexTypeEnum, BarcodeOrientation, BarcodeType

from .... import logger, db, tools
from ...MultiStepForm import MultiStepForm


class CommonBarcodeMatchForm(MultiStepForm):
    _step_name = "barcode_match"
    df: pd.DataFrame
    index_col: str

    i7_kit = SelectField(label="i7 Kit", coerce=int)
    i5_kit = SelectField(label="i5 Kit", coerce=int)
    i7_option = RadioField(
        "Index i7 was not found in the database. Please select how to proceed:",
        choices=[
            ("forward", "I have provided i7 barcode sequences in forward orientation"),
            ("rc", "I have provided i7 barcode sequneces in reverse complement orientation"),
            ("idk", "I don't know in which orientation the i7 barcodes are provided 🤷‍♂️"),
        ],
        validators=[OptionalValidator()],
    )
    i5_option = RadioField(
        "Index i5 was not found in the database. Please select how to proceed:",
        choices=[
            ("forward", "I have provided i5 barcode sequences in forward orientation"),
            ("rc", "I have provided i5 barcode sequences in reverse complement orientation"),
            ("idk", "I don't know in which orientation the i5 barcodes are provided 🤷‍♂️"),
        ],
        validators=[OptionalValidator()],
    )

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:        
        df = current_step.tables["barcode_table"]
        df = df[(df["index_well"] != "del") | (df["index_well"].isna())]
        return (not df.empty) and bool((
            df["kit_i7"].isna().all() and df["kit_i5"].isna().all()
        ))  # since all of the indices are reverse complemented in case of not forward orientation, we need .all()
    
    @staticmethod
    def check_index_type(barcode_table: pd.DataFrame) -> IndexTypeEnum | None:
        if (barcode_table["index_type_id"] == IndexType.DUAL_INDEX.id).all():
            return IndexType.DUAL_INDEX
        elif (barcode_table["index_type_id"] == IndexType.SINGLE_INDEX_I7.id).all():
            return IndexType.SINGLE_INDEX_I7
        elif (barcode_table["index_type_id"] == IndexType.COMBINATORIAL_DUAL_INDEX.id).all():
            return IndexType.COMBINATORIAL_DUAL_INDEX
        elif (barcode_table["index_type_id"] == IndexType.TENX_ATAC_INDEX.id).all():
            return IndexType.TENX_ATAC_INDEX
        
        return None
    
    def __init__(
        self, workflow: str,
        seq_request: models.SeqRequest | None,
        lab_prep: models.LabPrep | None,
        pool: models.Pool | None,
        uuid: str,
        formdata: dict | None = None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=workflow,
            step_name=CommonBarcodeMatchForm._step_name,
            step_args={}
        )
        self.seq_request = seq_request
        self.pool = pool
        self.lab_prep = lab_prep
        self._context["seq_request"] = seq_request
        self._context["lab_prep"] = lab_prep
        self._context["pool"] = pool

        self.barcode_table = self.tables["barcode_table"]
        self.index_type = CommonBarcodeMatchForm.check_index_type(self.barcode_table)

        self._context["index_type"] = self.index_type

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

        self.post_url = url_for(f"{workflow}_workflow.barcode_match", uuid=self.uuid, **self.url_context)

        df = self.barcode_table.copy()
        df["rc_sequence_i7"] = df["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        df["rc_sequence_i5"] = df["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        
        kits_i7 = db.pd.match_barcodes_to_kit(df["sequence_i7"].tolist(), BarcodeType.INDEX_I7)
        kits_i5 = db.pd.match_barcodes_to_kit(df["sequence_i5"].tolist(), BarcodeType.INDEX_I5)
        kits_rc_i7 = db.pd.match_barcodes_to_kit(df["rc_sequence_i7"].tolist(), BarcodeType.INDEX_I7)
        kits_rc_i5 = db.pd.match_barcodes_to_kit(df["rc_sequence_i5"].tolist(), BarcodeType.INDEX_I5)

        kit_i7s = []
        for _, row in kits_i7.iterrows():
            kit_i7s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}'))
        for _, row in kits_rc_i7.iterrows():
            kit_i7s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}' + " (Reverse Complement)"))

        kit_i5s = []
        for _, row in kits_i5.iterrows():
            kit_i5s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}'))
        for _, row in kits_rc_i5.iterrows():
            kit_i5s.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}' + " (Reverse Complement)"))
        
        self.i7_kit.choices = [(0, "Custom")] + kit_i7s  # type: ignore
        self.i5_kit.choices = [(0, "Custom")] + kit_i5s  # type: ignore

        if self.i7_kit.data is None:
            self.i7_kit.data = self.i7_kit.choices[-1][0]  # type: ignore
        if self.i5_kit.data is None:
            self.i5_kit.data = self.i5_kit.choices[-1][0]  # type: ignore

        self._context["kits"] = list(set(kit_i7s + kit_i5s))

    def fill_previous_form(self):
        d = self.metadata.get("barcode_match_form", {})
        if (input_barcode_table := self.tables.get("barcode_table", self.get_previous_step())) is not None:
            self.tables["barcode_table"] = input_barcode_table
        self.i7_kit.data = d.get("i7_kit", 0)
        self.i5_kit.data = d.get("i5_kit", 0)
        self.i7_option.data = d.get("i7_option", None)
        self.i5_option.data = d.get("i5_option", None)
        
    def tenx_atac_index_prepare(self):
        logger.warning("TenX ATAC index type is not yet implemented in the barcode match form.")
        self.i7_kit.choices = [(0, "Custom")]  # type: ignore
        self.i5_kit.choices = [(0, "Custom")]  # type: ignore
        self.i5_kit.data = 0
        self.i7_kit.data = 0
        self._context["barcodes"] = pd.DataFrame(columns=["kit_id", "kit"])

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.i7_kit.data and self.i7_option.data is None:
            self.i7_option.errors = ("Please select how to proceed with the i7 index.",)
        
        if not self.i5_kit.data and self.i5_option.data is None and self.index_type == IndexType.DUAL_INDEX:
            self.i5_option.errors = ("Please select how to proceed with the i5 index.",)
        
        if self.errors:
            return False
        
        if kit_i7_id := self.i7_kit.data:
            selected_i7 = next((name for kit_id, name in self.i7_kit.choices if kit_id == kit_i7_id), None)  # type: ignore
            rc_i7 = selected_i7.endswith(" (Reverse Complement)") if selected_i7 else False

            if (kit_i7 := db.index_kits.get(kit_i7_id)) is None:
                logger.error(f"Invalid i7 kit ID: {kit_i7_id}")
                raise Exception(f"Invalid i7 kit ID: {kit_i7_id}")
            
            if len(kit_i7_df := db.pd.get_index_kit_barcodes(kit_i7.id, per_index=True)) == 0:
                logger.error(f"No barcodes found for i7 kit ID: {kit_i7_id}")
                raise Exception(f"No barcodes found for i7 kit ID: {kit_i7_id}")
            
            if rc_i7:
                self.barcode_table["sequence_i7"] = self.barcode_table["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            
            self.barcode_table["name_i7"] = tools.utils.map_columns(self.barcode_table, kit_i7_df, idx_columns="sequence_i7", col="name_i7")
            self.barcode_table["kit_i7_id"] = kit_i7.id
            self.barcode_table["kit_i7"] = kit_i7.identifier
            
            self.barcode_table["kit_i7_id"] = kit_i7_id
            self.barcode_table["orientation_i7_id"] = BarcodeOrientation.FORWARD.id
        elif self.i7_option.data == "rc":
            self.barcode_table["sequence_i7"] = self.barcode_table["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            self.barcode_table["orientation_i7_id"] = BarcodeOrientation.FORWARD_NOT_VALIDATED.id
        elif self.i7_option.data == "forward":
            self.barcode_table["orientation_i7_id"] = BarcodeOrientation.FORWARD_NOT_VALIDATED.id
        
        if kit_i5_id := self.i5_kit.data:
            selected_i5 = next((name for kit_id, name in self.i5_kit.choices if kit_id == kit_i5_id), None)  # type: ignore
            rc_i5 = selected_i5.endswith(" (Reverse Complement)") if selected_i5 else False
            if kit_i5_id == kit_i7_id:
                kit_i5 = kit_i7  # type: ignore
                kit_i5_df = kit_i7_df  # type: ignore
            else:
                if (kit_i5 := db.index_kits.get(kit_i5_id)) is None:
                    logger.error(f"Invalid i5 kit ID: {kit_i5_id}")
                    raise Exception(f"Invalid i5 kit ID: {kit_i5_id}")
                if len(kit_i5_df := db.pd.get_index_kit_barcodes(kit_i5.id, per_index=True)) == 0:
                    logger.error(f"No barcodes found for i5 kit ID: {kit_i5_id}")
                    raise Exception(f"No barcodes found for i5 kit ID: {kit_i5_id}")
            
            if rc_i5:
                self.barcode_table["sequence_i5"] = self.barcode_table["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            
            self.barcode_table["name_i5"] = tools.utils.map_columns(self.barcode_table, kit_i5_df, idx_columns="sequence_i5", col="name_i5")
            self.barcode_table["kit_i5_id"] = kit_i5.id
            self.barcode_table["kit_i5"] = kit_i5.identifier
            
            self.barcode_table["kit_i5_id"] = kit_i5_id
            self.barcode_table["orientation_i5_id"] = BarcodeOrientation.FORWARD.id
            
        elif self.i5_option.data == "rc":
            self.barcode_table["sequence_i5"] = self.barcode_table["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            self.barcode_table["orientation_i5_id"] = BarcodeOrientation.FORWARD_NOT_VALIDATED.id
        elif self.i5_option.data == "forward":
            self.barcode_table["orientation_i5_id"] = BarcodeOrientation.FORWARD_NOT_VALIDATED.id

        self.metadata["barcode_match_form"] = {
            "i7_kit": kit_i7_id,
            "i5_kit": kit_i5_id,
            "i7_option": self.i7_option.data,
            "i5_option": self.i5_option.data,
        }

        return True