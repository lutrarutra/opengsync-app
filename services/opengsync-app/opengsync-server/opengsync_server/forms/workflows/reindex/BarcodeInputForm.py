from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import LibraryType, IndexType

from .... import logger, tools, db  # noqa F401
from ...MultiStepForm import MultiStepForm, StepFile

from ....tools.spread_sheet_components import TextColumn, DropdownColumn, InvalidCellValue, IntegerColumn
from ...SpreadsheetInput import SpreadsheetInput
from .IndexKitMappingForm import IndexKitMappingForm


class BarcodeInputForm(MultiStepForm):
    _template_path = "workflows/reindex/barcode-input.html"
    _workflow_name = "reindex"
    _step_name = "barcode_input"
    
    columns = [
        DropdownColumn("library_name", "Library Name", 250, choices=[], required=True),
        TextColumn("index_well", "Index Well", 100, max_length=8),
        TextColumn("kit_i7", "i7 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
        TextColumn("kit_i5", "i5 Kit", 200, max_length=models.Kit.name.type.length),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with="")),
    ]

    def __init__(
        self, seq_request: models.SeqRequest | None = None, lab_prep: models.LabPrep | None = None, formdata: dict | None = None, previous_form: Optional[MultiStepForm] = None,
        uuid: Optional[str] = None
    ):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=BarcodeInputForm._workflow_name,
            step_name=BarcodeInputForm._step_name, previous_form=previous_form,
            step_args={}
        )
        self.seq_request = seq_request
        self.lab_prep = lab_prep
        self._context["seq_request"] = seq_request
        self._context["lab_prep"] = lab_prep
        self.library_table = self.tables["library_table"]

        if (csrf_token := self.formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        if self.seq_request is not None:
            self.post_url = url_for("reindex_workflow.reindex", uuid=self.uuid, seq_request_id=self.seq_request.id)
        elif self.lab_prep is not None:
            self.post_url = url_for("reindex_workflow.reindex", uuid=self.uuid, lab_prep_id=self.lab_prep.id)
        else:
            self.post_url = url_for("reindex_workflow.reindex", uuid=self.uuid)

        logger.debug(self.post_url)
            
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=BarcodeInputForm.columns, csrf_token=csrf_token,
            post_url=self.post_url, formdata=formdata, df=self.library_table
        )
        self.spreadsheet.columns["library_name"].source = self.library_table["library_name"].values.tolist() if self.library_table is not None else []

    def validate(self) -> bool:
        validated = super().validate()
            
        if not validated:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        df.loc[df["kit_i7"].notna(), "kit_i7"] = df.loc[df["kit_i7"].notna(), "kit_i7"].astype(str)
        df.loc[df["kit_i5"].notna(), "kit_i5"] = df.loc[df["kit_i5"].notna(), "kit_i5"].astype(str)
            
        df["sequence_i7"] = df["sequence_i7"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))
        df["sequence_i5"] = df["sequence_i5"].apply(lambda x: tools.make_alpha_numeric(x, keep=[";"], replace_white_spaces_with=""))

        seq_i7_max_length = df["sequence_i7"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))
        seq_i5_max_length = df["sequence_i5"].apply(lambda x: max(((len(s) for s in x.split(";") if pd.notna(s)) if pd.notna(x) else ""), default=0))

        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = df["kit_i7"].notna() & (df["index_well"].notna() | df["name_i7"].notna())
        manual_defined = df["sequence_i7"].notna()

        df.loc[df["kit_i5"].isna(), "kit_i5"] = df.loc[df["kit_i5"].isna(), "kit_i7"]
        df.loc[df["name_i5"].isna(), "name_i5"] = df.loc[df["name_i5"].isna(), "name_i7"]

        for i, (idx, row) in enumerate(df.iterrows()):
            if not kit_defined.at[idx] and not manual_defined.at[idx]:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue("missing 'sequence_i7' or 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well'"))

            if seq_i7_max_length.at[idx] > models.LibraryIndex.sequence_i7.type.length:
                self.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({seq_i7_max_length.at[idx]} > {models.LibraryIndex.sequence_i7.type.length})"))
            
            if seq_i5_max_length.at[idx] > models.LibraryIndex.sequence_i5.type.length:
                self.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({seq_i5_max_length.at[idx]} > {models.LibraryIndex.sequence_i5.type.length})"))

        validated = validated and (len(self.spreadsheet._errors) == 0)
        self.df = df

        return validated

    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()
        
        barcode_table_data = {
            "library_name": [],
            "index_well": [],
            "kit_i7": [],
            "name_i7": [],
            "sequence_i7": [],
            "kit_i5": [],
            "name_i5": [],
            "sequence_i5": [],
        }
        
        for idx, row in self.df.iterrows():
            index_i7_seqs = row["sequence_i7"].split(";") if pd.notna(row["sequence_i7"]) else [None]
            index_i5_seqs = row["sequence_i5"].split(";") if pd.notna(row["sequence_i5"]) else [None]

            for i in range(max(len(index_i7_seqs), len(index_i5_seqs))):
                barcode_table_data["library_name"].append(row["library_name"])
                barcode_table_data["index_well"].append(row["index_well"])
                barcode_table_data["kit_i7"].append(row["kit_i7"])
                barcode_table_data["name_i7"].append(row["name_i7"])
                barcode_table_data["sequence_i7"].append(index_i7_seqs[i] if len(index_i7_seqs) > i else None)
                barcode_table_data["kit_i5"].append(row["kit_i5"])
                barcode_table_data["name_i5"].append(row["name_i5"])
                barcode_table_data["sequence_i5"].append(index_i5_seqs[i] if len(index_i5_seqs) > i else None)

        barcode_table = pd.DataFrame(barcode_table_data)
        barcode_table["kit_i7_id"] = None
        barcode_table["kit_i7_name"] = None
        barcode_table["kit_i5_id"] = None
        barcode_table["kit_i5_name"] = None
        barcode_table["index_type_id"] = None

        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].notna()), "index_type_id"] = IndexType.DUAL_INDEX.id
        barcode_table.loc[(barcode_table["sequence_i7"].notna() & barcode_table["sequence_i5"].isna()), "index_type_id"] = IndexType.SINGLE_INDEX.id
        for (library_name, library_type_id), _ in self.library_table.groupby(["library_name", "library_type_id"]):
            if LibraryType.get(library_type_id) == LibraryType.TENX_SC_ATAC:
                barcode_table.loc[barcode_table["library_name"] == library_name, "index_type_id"] = IndexType.TENX_ATAC_INDEX.id

        if IndexKitMappingForm.is_applicable(self):
            if self.seq_request is not None:
                self.metadata["seq_request_id"] = self.seq_request.id
            if self.lab_prep is not None:
                self.metadata["lab_prep_id"] = self.lab_prep.id
            self.add_table("barcode_table", barcode_table)
            self.update_data()
            form = IndexKitMappingForm(uuid=self.uuid, previous_form=self, lab_prep=self.lab_prep, seq_request=self.seq_request)
            form.prepare()
            return form.make_response()
        
        for i, (idx, row) in enumerate(self.library_table.iterrows()):
            if (library := db.get_library(row["library_id"])) is None:
                logger.error(f"{self.uuid}: Library {row['library_id']} not found")
                raise ValueError(f"{self.uuid}: Library {row['library_id']} not found")

            library = db.remove_library_indices(library_id=library.id)
            df = barcode_table[barcode_table["library_id"] == row["library_id"]].copy()

            seq_i7s = df["sequence_i7"].values
            seq_i5s = df["sequence_i5"].values
            name_i7s = df["name_i7"].values
            name_i5s = df["name_i5"].values

            kit_i7_id = row["kit_i7_id"] if pd.notna(row["kit_i7_id"]) else None
            kit_i5_id = row["kit_i5_id"] if pd.notna(row["kit_i5_id"]) else None

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
                    library_id=library.id, index_kit_i7_id=kit_i7_id, index_kit_i5_id=kit_i5_id,
                    name_i7=name_i7s[j] if len(name_i7s) > j and pd.notna(name_i7s[j]) else None,
                    name_i5=name_i5s[j] if len(name_i5s) > j and pd.notna(name_i5s[j]) else None,
                    sequence_i7=seq_i7s[j] if len(seq_i7s) > j and pd.notna(seq_i7s[j]) else None,
                    sequence_i5=seq_i5s[j] if len(seq_i5s) > j and pd.notna(seq_i5s[j]) else None,
                )

        flash("Libraries Re-Indexed!")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))
        
        if self.lab_prep is not None:
            return make_response(redirect=url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id))
        
        return make_response(redirect=url_for("dashboard"))