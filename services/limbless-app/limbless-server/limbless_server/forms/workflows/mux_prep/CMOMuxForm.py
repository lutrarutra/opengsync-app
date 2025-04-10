from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import FormField

from limbless_db import models
from limbless_db.categories import LibraryType, LibraryStatus

from .... import logger, tools, db  # noqa F401
from ....tools import SpreadSheetColumn
from ...SearchBar import OptionalSearchBar
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput


class CMOMuxForm(MultiStepForm):
    _template_path = "workflows/mux_prep/mux_prep-cmo_annotation.html"
    _workflow_name = "mux_prep"
    _step_name = "cmo_mux"

    kit = FormField(OptionalSearchBar, label="Select Kit")
    
    columns = [
        SpreadSheetColumn("demux_name", "Demultiplexed Name", "text", 170, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("sample_pool", "Sample Pool", "text", 170, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("feature", "Feature", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        SpreadSheetColumn("sequence", "Sequence", "text", 150, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        SpreadSheetColumn("pattern", "Pattern", "text", 200, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        SpreadSheetColumn("read", "Read", "text", 100, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
    ]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict = {}, uuid: Optional[str] = None):
        MultiStepForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=CMOMuxForm._workflow_name,
            step_name=CMOMuxForm._step_name, step_args={"multiplexing_type": "cmo"}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore

        self.sample_table = db.get_lab_prep_samples_df(lab_prep.id)
        mux_pools = self.sample_table[self.sample_table["library_type"] == LibraryType.TENX_MULTIPLEXING_CAPTURE]["sample_pool"]
        self.sample_table = self.sample_table[self.sample_table["sample_pool"].isin(mux_pools)]

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=csrf_token,
            post_url=url_for("mux_prep_workflow.parse_cmo_annotation", lab_prep_id=self.lab_prep.id, uuid=self.uuid),
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

        for _, row in self.sample_table[self.sample_table["library_type"] == LibraryType.TENX_MULTIPLEXING_CAPTURE].iterrows():
            template_data["sample_pool"].append(row["sample_pool"])
            template_data["demux_name"].append(row["sample_name"])
            template_data["kit"].append(None)
            template_data["feature"].append(None)
            template_data["sequence"].append(row["cmo_sequence"])
            template_data["pattern"].append(row["cmo_pattern"])
            template_data["read"].append(row["cmo_read"])

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

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["demux_name"]):
                self.spreadsheet.add_error(idx, "demux_name", "'Demux Name' is missing.", "missing_value")
            elif row["demux_name"] not in self.sample_table["sample_name"].values:
                self.spreadsheet.add_error(idx, "demux_name", f"Unknown sample '{row['demux_name']}'. Must be one of: {', '.join(self.sample_table['sample_name'])}", "invalid_value")
            
            if pd.isna(row["sample_pool"]):
                self.spreadsheet.add_error(idx, "sample_pool", "'Sample Pool' is missing.", "missing_value")

            if kit is not None:
                if pd.notna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", "Specify Kit + Feature or Sequence + Pattern + Read", "invalid_input")
                if pd.notna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", "Specify Kit + Feature or Sequence + Pattern + Read", "invalid_input")
                if pd.notna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", "Specify Kit + Feature or Sequence + Pattern + Read", "invalid_input")
                
                if pd.isna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", "Specify Kit + Feature or Sequence + Pattern + Read", "missing_value")
                elif duplicate_kit_feature.at[idx]:
                    self.spreadsheet.add_error(idx, "feature", f"Row {i+1} has duplicate 'Kit' + 'Feature' specified in same pool.", "duplicate_value")
                else:
                    if len(features := db.get_features_from_kit_by_feature_name(row["feature"], kit.id)) == 0:
                        self.spreadsheet.add_error(idx, "feature", f"Feature '{row['feature']}' not found in '{kit.name}'.", "invalid_value")
                    else:
                        feature = features[0]
                        df.at[idx, "sequence"] = feature.sequence
                        df.at[idx, "pattern"] = feature.pattern
                        df.at[idx, "read"] = feature.read
            else:
                if pd.isna(row["sequence"]):
                    self.spreadsheet.add_error(idx, "sequence", "Specify Kit + Feature or Sequence + Pattern + Read", "missing_value")
                if pd.isna(row["pattern"]):
                    self.spreadsheet.add_error(idx, "pattern", "Specify Kit + Feature or Sequence + Pattern + Read", "missing_value")
                if pd.isna(row["read"]):
                    self.spreadsheet.add_error(idx, "read", "Specify Kit + Feature or Sequence + Pattern + Read", "missing_value")
                if pd.notna(row["feature"]):
                    self.spreadsheet.add_error(idx, "feature", "Specify Kit + Feature or Sequence + Pattern + Read", "invalid_input")
                if duplicate_manual_feature.at[idx]:
                    self.spreadsheet.add_error(idx, "sequence", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same pool.", "duplicate_value")
                    self.spreadsheet.add_error(idx, "pattern", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same pool.", "duplicate_value")
                    self.spreadsheet.add_error(idx, "read", f"Row {i+1} has duplicate 'Sequence + Pattern + Read' combination in same pool.", "duplicate_value")
                
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
        self.sample_table["cmo_sequence"] = self.sample_table["sample_name"].apply(lambda x: sequence_map[x])
        self.sample_table["cmo_pattern"] = self.sample_table["sample_name"].apply(lambda x: pattern_map[x])
        self.sample_table["cmo_read"] = self.sample_table["sample_name"].apply(lambda x: read_map[x])

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
                )
                libraries[lib] = new_library
            else:
                new_library = libraries[lib]

            db.link_sample_library(
                sample_id=sample.id, library_id=new_library.id,
                cmo_sequence=row["cmo_sequence"], cmo_pattern=row["cmo_pattern"], cmo_read=row["cmo_read"]
            )
            new_library.features = old_library.features
            new_library = db.update_library(new_library)

        for old_library_id in old_libraries:
            db.delete_library(old_library_id, delete_orphan_samples=False)

        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep_page", lab_prep_id=self.lab_prep.id)))