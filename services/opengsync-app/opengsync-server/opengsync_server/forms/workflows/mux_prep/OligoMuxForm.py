from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import FormField

from opengsync_db import models
from opengsync_db.categories import LibraryStatus, MUXType

from .... import logger, tools, db  # noqa F401
from ....tools.spread_sheet_components import TextColumn, InvalidCellValue, DropdownColumn, MissingCellValue, DuplicateCellValue
from ...SearchBar import OptionalSearchBar
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class OligoMuxForm(MultiStepForm):
    _template_path = "workflows/mux_prep/mux_prep-oligo_mux_annotation.html"
    _workflow_name = "mux_prep"
    _step_name = "oligo_annotation"

    kit = FormField(OptionalSearchBar, label="Select Kit")
    mux_type = MUXType.TENX_OLIGO
    
    columns = [
        TextColumn("demux_name", "Demultiplexed Name", 170, max_length=models.Sample.name.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        TextColumn("sample_pool", "Sample Pool", 170, max_length=models.Library.sample_name.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        DropdownColumn("read", "Read", 100, choices=["", "R2", "R1"]),
    ]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=OligoMuxForm._workflow_name,
            step_name=OligoMuxForm._step_name, step_args={"mux_type_id": OligoMuxForm.mux_type.id}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        self.sample_table = db.get_lab_prep_samples_df(lab_prep.id)
        self.sample_table = self.sample_table[self.sample_table["mux_type"].isin([MUXType.TENX_OLIGO])]
        self.mux_table = self.sample_table.drop_duplicates(subset=["sample_name", "sample_pool"], keep="first")

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for("mux_prep_workflow.parse_oligo_mux_annotation", lab_prep_id=self.lab_prep.id, uuid=self.uuid),
            formdata=formdata, df=self.__get_template()
        )

    def __get_template(self) -> pd.DataFrame:
        template_data = {
            "demux_name": [],
            "sample_pool": [],
            "kit": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
        }

        for _, row in self.mux_table.iterrows():
            template_data["sample_pool"].append(row["sample_pool"])
            template_data["demux_name"].append(row["sample_name"])
            template_data["kit"].append(None)
            template_data["feature"].append(None)
            if (mux := row.get("mux")) is None:
                template_data["sequence"].append(None)
                template_data["pattern"].append(None)
                template_data["read"].append(None)
            else:
                template_data["sequence"].append(mux.get("barcode"))
                template_data["pattern"].append(mux.get("pattern"))
                template_data["read"].append(mux.get("read"))

        return pd.DataFrame(template_data)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        kit: models.FeatureKit | None = None
        if (kit_id := self.kit.selected.data) is not None:
            if (kit := db.get_feature_kit(kit_id)) is None:
                logger.error(f"Unknown feature kit id {kit_id}")
                self.kit.search_bar.errors = ("Unknown feature kit id",)
                return False

        duplicate_kit_feature = df.duplicated(subset=["sample_pool", "feature"], keep=False)
        duplicate_manual_feature = df.duplicated(subset=["sample_pool", "sequence", "read", "pattern"], keep=False)

        for idx, row in df.iterrows():
            if row["demux_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "demux_name", InvalidCellValue(f"Unknown sample '{row['demux_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}"))

            if kit is not None:
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", InvalidCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", InvalidCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", InvalidCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                
                if pd.isna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", MissingCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                elif duplicate_kit_feature.at[idx]:
                    self.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified in same pool."))
                else:
                    if len(features := db.get_features_from_kit_by_feature_name(row["feature"], kit.id)) == 0:
                        self.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in '{kit.name}'."))
                    else:
                        feature = features[0]
                        df.at[idx, "sequence"] = feature.sequence
                        df.at[idx, "pattern"] = feature.pattern
                        df.at[idx, "read"] = feature.read
            else:
                if pd.isna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", MissingCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if pd.isna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", MissingCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if pd.isna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", MissingCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if pd.notna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", MissingCellValue("Specify Kit + Feature or Sequence + Pattern + Read"))
                if duplicate_manual_feature.at[idx]:
                    self.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same pool."))
                    self.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same pool."))
                    self.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same pool."))
                
        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df

        return True

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_pool_map = self.df.set_index("demux_name")["sample_pool"].to_dict()
        sequence_map = self.df.set_index("demux_name")["sequence"].to_dict()
        pattern_map = self.df.set_index("demux_name")["pattern"].to_dict()
        read_map = self.df.set_index("demux_name")["read"].to_dict()
        
        self.sample_table["new_sample_pool"] = self.sample_table["sample_name"].apply(lambda x: sample_pool_map[x])
        self.sample_table["mux_barcode"] = self.sample_table["sample_name"].apply(lambda x: sequence_map[x])
        self.sample_table["mux_pattern"] = self.sample_table["sample_name"].apply(lambda x: pattern_map[x])
        self.sample_table["mux_read"] = self.sample_table["sample_name"].apply(lambda x: read_map[x])
        self.sample_table["mux_type_id"] = MUXType.TENX_OLIGO.id
                
        libraries: dict[str, models.Library] = dict()
        old_libraries: list[int] = []
        
        for _, row in self.sample_table.iterrows():
            if (old_library := db.get_library(int(row["library_id"]))) is None:
                logger.error(f"Library {row['library_id']} not found.")
                raise Exception(f"Library {row['library_id']} not found.")
            
            if old_library.id not in old_libraries:
                old_libraries.append(old_library.id)
            
            if (sample := db.get_sample(int(row["sample_id"]))) is None:
                logger.error(f"Sample {row['sample_id']} not found.")
                raise Exception(f"Sample {row['sample_id']} not found.")
            
            lib = f"{row['new_sample_pool']}_{old_library.type.identifier}"
            if lib not in libraries.keys():
                new_library = db.create_library(
                    name=lib,
                    sample_name=row["new_sample_pool"],
                    library_type=old_library.type,
                    status=LibraryStatus.PREPARING,
                    owner_id=old_library.owner_id,
                    seq_request_id=old_library.seq_request_id,
                    lab_prep_id=self.lab_prep.id,
                    genome_ref=old_library.genome_ref,
                    assay_type=old_library.assay_type,
                    mux_type=old_library.mux_type,
                    nuclei_isolation=old_library.nuclei_isolation,
                )
                libraries[lib] = new_library
            else:
                new_library = libraries[lib]

            db.link_sample_library(
                sample_id=sample.id, library_id=new_library.id,
                mux={
                    "barcode": row["mux_barcode"],
                    "pattern": row["mux_pattern"],
                    "read": row["mux_read"],
                },
            )
            new_library.features = old_library.features
            new_library = db.update_library(new_library)

        for old_library_id in old_libraries:
            db.delete_library(old_library_id, delete_orphan_samples=False)

        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id)))