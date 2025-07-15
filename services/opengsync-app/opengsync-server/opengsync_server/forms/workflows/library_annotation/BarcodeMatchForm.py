import os
from typing import Optional

import pandas as pd

from flask import Response, current_app
from wtforms import SelectField, RadioField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import IndexType, IndexTypeEnum

from .... import logger, tools, db  # noqa F401
from ...MultiStepForm import MultiStepForm

from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class BarcodeMatchForm(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-barcode-match.html"
    _workflow_name = "library_annotation"
    _step_name = "barcode_match"

    i7_kit = SelectField(label="i7 Kit", coerce=int)
    i5_kit = SelectField(label="i5 Kit", coerce=int)
    i7_option = RadioField(
        "Index i7 was not found in the database. Please select how to proceed:",
        choices=[
            ("forward", "I have provided i7 barcodes in forward orientation"),
            ("rc", "I have provided i7 barcodes in reverse complement orientation"),
            ("idk", "I don't know in which orientation the i7 barcodes are provided"),
        ],
        validators=[OptionalValidator()],
    )
    i5_option = RadioField(
        "Index i5 was not found in the database. Please select how to proceed:",
        choices=[
            ("forward", "I have provided i5 barcodes in forward orientation"),
            ("rc", "I have provided i5 barcodes in reverse complement orientation"),
            ("idk", "I don't know in which orientation the i5 barcodes are provided"),
        ],
        validators=[OptionalValidator()],
    )

    @staticmethod
    def is_applicable(current_step: MultiStepForm) -> bool:
        return (
            current_step.tables["barcode_table"]["kit_i7"].isna().all() or
            current_step.tables["barcode_table"]["kit_i5"].isna().all()
        )
        
    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict = {}, previous_form: Optional[MultiStepForm] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeMatchForm._workflow_name,
            step_name=BarcodeMatchForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request

        self.barcode_table = self.tables["barcode_table"]
        self.index_type = BarcodeMatchForm.check_index_type(self.barcode_table)
        self._context["index_type"] = self.index_type
        if self.index_type == IndexType.DUAL_INDEX:
            self.dual_index_prepare()
        elif self.index_type == IndexType.SINGLE_INDEX:
            self.single_index_prepare()
        elif self.index_type == IndexType.TENX_ATAC_INDEX:
            self.tenx_atac_index_prepare()
        else:
            logger.warning("Index type could not be determined")
        
    @staticmethod
    def check_index_type(barcode_table: pd.DataFrame) -> IndexTypeEnum | None:
        if (barcode_table["index_type_id"] == IndexType.DUAL_INDEX.id).all():
            return IndexType.DUAL_INDEX
        elif (barcode_table["index_type_id"] == IndexType.SINGLE_INDEX.id).all():
            return IndexType.SINGLE_INDEX
        elif (barcode_table["index_type_id"] == IndexType.TENX_ATAC_INDEX.id).all():
            return IndexType.TENX_ATAC_INDEX
        
        return None
    
    def tenx_atac_index_prepare(self):
        logger.warning("TenX ATAC index type is not yet implemented in the barcode match form.")
        self.i7_kit.choices = [(0, "Custom")]  # type: ignore
        self.i5_kit.choices = [(0, "Custom")]  # type: ignore
        self.i5_kit.data = 0
        self.i7_kit.data = 0
        self._context["barcodes"] = pd.DataFrame(columns=["kit_id", "kit"])

    def single_index_prepare(self):
        path = os.path.join(current_app.config["APP_DATA_FOLDER"], "kits", f"{IndexType.SINGLE_INDEX.id}.pkl")
        if not os.path.exists(path):
            logger.warning(f"Singe-index barcode file not found: {path}")
            barcodes = pd.DataFrame(columns=["kit_id", "kit", "sequence_i7"])
        else:
            barcodes = pd.read_pickle(path)

        df = self.barcode_table.copy()
        df["rc_sequence_i7"] = df["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        
        barcodes["fc_i7"] = barcodes["sequence_i7"].isin(df["sequence_i7"])
        barcodes["rc_i7"] = barcodes["sequence_i7"].isin(df["rc_sequence_i7"])
        
        groupby = barcodes.groupby(["kit_id", "kit"])
        groupby = groupby[["fc_i7", "rc_i7"]].sum()

        i7_kit_choices = [(0, "Custom")]

        kits = set()

        for kit_id, kit in groupby.index:
            if groupby.loc[(kit_id, kit), "fc_i7"] == df.shape[0]:
                i7_kit_choices.append((kit_id, kit))
                kits.add(kit_id)
            elif groupby.loc[(kit_id, kit), "rc_i7"] == df.shape[0]:
                i7_kit_choices.append((kit_id, kit + " (Reverse Complement)"))
                kits.add(kit_id)

        self.i7_kit.choices = i7_kit_choices  # type: ignore
        self.i5_kit.choices = [(0, "Custom")]  # type: ignore

        if self.i7_kit.data is None:
            self.i7_kit.data = i7_kit_choices[-1][0]
        self.i5_kit.data = 0

        barcodes = barcodes[barcodes["kit_id"].isin(kits)].reset_index(drop=True)
        self._context["barcodes"] = barcodes
        
    def dual_index_prepare(self):
        path = os.path.join(current_app.config["APP_DATA_FOLDER"], "kits", f"{IndexType.DUAL_INDEX.id}.pkl")
        if not os.path.exists(path):
            logger.warning(f"Dual index barcode file not found: {path}")
            barcodes = pd.DataFrame(columns=["kit_id", "kit", "sequence_i7", "sequence_i5"])
        else:
            barcodes = pd.read_pickle(path)

        df = self.barcode_table.copy()
        df["rc_sequence_i7"] = df["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        df["rc_sequence_i5"] = df["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        
        barcodes["fc_i7"] = barcodes["sequence_i7"].isin(df["sequence_i7"])
        barcodes["fc_i5"] = barcodes["sequence_i5"].isin(df["sequence_i5"])
        barcodes["rc_i7"] = barcodes["sequence_i7"].isin(df["rc_sequence_i7"])
        barcodes["rc_i5"] = barcodes["sequence_i5"].isin(df["rc_sequence_i5"])
        
        groupby = barcodes.groupby(["kit_id", "kit"])
        groupby = groupby[["fc_i7", "fc_i5", "rc_i7", "rc_i5"]].sum()

        i7_kit_choices = [(0, "Custom")]
        i5_kit_choices = [(0, "Custom")]

        kits = set()

        for kit_id, kit in groupby.index:
            if groupby.loc[(kit_id, kit), "fc_i7"] == df.shape[0]:
                i7_kit_choices.append((kit_id, kit))
                kits.add(kit_id)
            elif groupby.loc[(kit_id, kit), "rc_i7"] == df.shape[0]:
                i7_kit_choices.append((kit_id, kit + " (Reverse Complement)"))
                kits.add(kit_id)
            if groupby.loc[(kit_id, kit), "fc_i5"] == df.shape[0]:
                i5_kit_choices.append((kit_id, kit))
                kits.add(kit_id)
            elif groupby.loc[(kit_id, kit), "rc_i5"] == df.shape[0]:
                i5_kit_choices.append((kit_id, kit + " (Reverse Complement)"))
                kits.add(kit_id)

        self.i7_kit.choices = i7_kit_choices  # type: ignore
        self.i5_kit.choices = i5_kit_choices  # type: ignore

        if self.i7_kit.data is None:
            self.i7_kit.data = i7_kit_choices[-1][0]
        if self.i5_kit.data is None:
            self.i5_kit.data = i5_kit_choices[-1][0]

        barcodes = barcodes[barcodes["kit_id"].isin(kits)].reset_index(drop=True)
        self._context["barcodes"] = barcodes

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
            logger.debug(f"Selected i7 kit: {selected_i7}")
            rc_i7 = selected_i7.endswith(" (Reverse Complement)") if selected_i7 else False

            if (kit_i7 := db.get_index_kit(kit_i7_id)) is None:
                logger.error(f"Invalid i7 kit ID: {kit_i7_id}")
                raise Exception(f"Invalid i7 kit ID: {kit_i7_id}")
            
            if len(kit_i7_df := db.get_index_kit_barcodes_df(kit_i7.id, per_index=True)) == 0:
                logger.error(f"No barcodes found for i7 kit ID: {kit_i7_id}")
                raise Exception(f"No barcodes found for i7 kit ID: {kit_i7_id}")
            
            mapping = dict(kit_i7_df[["sequence_i7", "name_i7"]].values.tolist())
            if rc_i7:
                self.barcode_table["sequence_i7"] = self.barcode_table["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            try:
                self.barcode_table["name_i7"] = self.barcode_table["sequence_i7"].apply(lambda x: mapping[x])
            except KeyError as e:
                logger.error(f"Invalid i7 sequence in library table: {e}")
                raise KeyError(f"Invalid i7 sequence in library table: {e}")
        elif self.i7_option.data == "rc":
            self.barcode_table["sequence_i7"] = self.barcode_table["sequence_i7"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
        
        if kit_i5_id := self.i5_kit.data:
            selected_i5 = next((name for kit_id, name in self.i5_kit.choices if kit_id == kit_i5_id), None)  # type: ignore
            rc_i5 = selected_i5.endswith(" (Reverse Complement)") if selected_i5 else False
            if kit_i5_id == kit_i7_id:
                kit_i5 = kit_i7
                kit_i5_df = kit_i7_df
            else:
                if (kit_i5 := db.get_index_kit(kit_i5_id)) is None:
                    logger.error(f"Invalid i5 kit ID: {kit_i5_id}")
                    raise Exception(f"Invalid i5 kit ID: {kit_i5_id}")
                if len(kit_i5_df := db.get_index_kit_barcodes_df(kit_i5.id, per_index=True)) == 0:
                    logger.error(f"No barcodes found for i5 kit ID: {kit_i5_id}")
                    raise Exception(f"No barcodes found for i5 kit ID: {kit_i5_id}")
                
            mapping = dict(kit_i5_df[["sequence_i5", "name_i5"]].values.tolist())
            
            if rc_i5:
                self.barcode_table["sequence_i5"] = self.barcode_table["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)

            try:
                self.barcode_table["name_i5"] = self.barcode_table["sequence_i5"].apply(lambda x: mapping[x])
            except KeyError as e:
                logger.error(f"Invalid i5 sequence in library table: {e}")
                raise KeyError(f"Invalid i5 sequence in library table: {e}")
            
        elif self.i5_option.data == "rc":
            self.barcode_table["sequence_i5"] = self.barcode_table["sequence_i5"].apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        if self.i7_option.data is not None:
            self.add_comment(
                context="i7_option",
                text=f"{dict(self.i7_option.choices)[self.i7_option.data]}: {', '.join(self.barcode_table['library_name'].unique().tolist())}",  # type: ignore
            )

        if self.i5_option.data is not None:
            self.add_comment(
                context="i5_option",
                text=f"{dict(self.i5_option.choices)[self.i5_option.data]}: {', '.join(self.barcode_table['library_name'].unique().tolist())}",  # type: ignore
            )

        self.update_table("barcode_table", self.barcode_table)
        if OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return next_form.make_response()