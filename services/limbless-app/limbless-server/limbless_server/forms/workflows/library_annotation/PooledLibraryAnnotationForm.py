from typing import Literal

import pandas as pd

from flask import Response, url_for

from limbless_db import models
from limbless_db.categories import LibraryType, GenomeRef, BarcodeType, IndexType

from .... import logger, db
from ....tools import SpreadSheetColumn, tools
from ...HTMXFlaskForm import HTMXFlaskForm
from ...TableDataForm import TableDataForm
from ...SpreadsheetInput import SpreadsheetInput
from .CMOReferenceInputForm import CMOReferenceInputForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .GenomeRefMappingForm import GenomeRefMappingForm
from .FRPAnnotationForm import FRPAnnotationForm
from .LibraryMappingForm import LibraryMappingForm
from .SampleAnnotationForm import SampleAnnotationForm
from .FeatureReferenceInputForm import FeatureReferenceInputForm


class PooledLibraryAnnotationForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_annotation/sas-2.pooled.html"

    kit_columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
        "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
        "index_well": SpreadSheetColumn("D", "index_well", "Index Well", "text", 150, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "index_i7": SpreadSheetColumn("E", "index_i7", "Index i7 Name", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "index_i5": SpreadSheetColumn("F", "index_i5", "Index i5 Name", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    }

    manual_columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 200, str, clean_up_fnc=lambda x: tools.make_alpha_numeric(x)),
        "genome": SpreadSheetColumn("B", "genome", "Genome", "dropdown", 200, str, GenomeRef.names()),
        "library_type": SpreadSheetColumn("C", "library_type", "Library Type", "dropdown", 200, str, LibraryType.names()),
        "index_i7": SpreadSheetColumn("D", "index_i7", "Index i7 Sequence", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        "index_i5": SpreadSheetColumn("E", "index_i5", "Index i5 Sequence", "text", 250, str, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
    }

    def __init__(
        self, seq_request: models.SeqRequest, uuid: str, index_specification_type: Literal["manual", "kit"],
        formdata: dict = {}
    ):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid, dirname="library_annotation")
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.index_specification_type = index_specification_type

        self.index_1_kit_id = self.metadata.get("index_1_kit_id")
        self.index_2_kit_id = self.metadata.get("index_2_kit_id")

        self._context["index_1_kit_id"] = self.index_1_kit_id
        self._context["index_2_kit_id"] = self.index_2_kit_id

        logger.debug(self.index_1_kit_id)
        logger.debug(self.index_2_kit_id)

        if self.index_specification_type == "manual":
            columns = PooledLibraryAnnotationForm.manual_columns
        elif self.index_specification_type == "kit":
            columns = PooledLibraryAnnotationForm.kit_columns
        else:
            logger.error(f"Invalid index specification type: {index_specification_type}")
            raise ValueError(f"Invalid index specification type: {index_specification_type}")
        
        if (csrf_token := formdata.get("csrf_token")) is None:
            csrf_token = self.csrf_token._value()  # type: ignore
        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=columns, csrf_token=csrf_token,
            post_url=url_for('library_annotation_workflow.parse_table', seq_request_id=seq_request.id, form_type='pooled', index_spec=self.index_specification_type, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True
        )

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
        df["index_i7_sequences"] = None
        df["index_i5_sequences"] = None
        df["index_i7_name"] = None
        df["index_i5_name"] = None

        if self.index_specification_type == "kit":
            if self.index_1_kit_id is None:
                logger.error(f"{self.uuid}: Index kit ID is not set.")
                raise ValueError("Index kit ID is not set.")
            if self.index_2_kit_id is None:
                self.index_2_kit_id = self.index_1_kit_id
            if (kit_1 := db.get_index_kit(self.index_1_kit_id)) is None:
                logger.error(f"{self.uuid}: Index kit with ID {self.index_1_kit_id} does not exist.")
                raise ValueError(f"Index kit with ID {self.index_1_kit_id} does not exist.")
            
            if len(kit_1_df := db.get_index_kit_barcodes_df(self.metadata["index_1_kit_id"], per_adapter=False)) == 0:
                logger.error(f"{self.uuid}: Index kit with ID {self.metadata['index_1_kit_id']} does not exist.")

            if self.metadata["index_2_kit_id"] is None or self.metadata["index_2_kit_id"] == self.metadata["index_1_kit_id"]:
                kit_2_df = kit_1_df
                kit_2 = kit_1
            else:
                if (kit_2 := db.get_index_kit(self.metadata["index_2_kit_id"])) is None:
                    logger.error(f"{self.uuid}: Index kit with ID {self.index_2_kit_id} does not exist.")
                    raise ValueError(f"Index kit with ID {self.index_2_kit_id} does not exist.")
                if len(kit_2_df := db.get_index_kit_barcodes_df(self.metadata["index_2_kit_id"], per_adapter=False)) == 0:
                    logger.error(f"{self.uuid}: Index kit with ID {self.index_2_kit_id} does not exist.")
                    raise ValueError(f"Index kit with ID {self.index_2_kit_id} does not exist.")
                
        def base_filter(x: str) -> list[str]:
            return list(set([c for c in x if c not in "ACGT"]))

        duplicate_sample_libraries = df.duplicated(subset=["sample_name", "library_type"])
        
        seq_request_samples = db.get_seq_request_samples_df(self.seq_request.id)

        if "index_well" not in df.columns:
            df["index_well"] = None

        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        for i, (idx, row) in enumerate(df.iterrows()):
            if pd.isna(row["sample_name"]):
                self.spreadsheet.add_error(i + 1, "sample_name", "missing 'Sample Name'", "missing_value")

            if duplicate_sample_libraries.at[idx]:
                self.spreadsheet.add_error(i + 1, "sample_name", "Duplicate 'Sample Name' and 'Library Type'", "duplicate_value")

            if ((seq_request_samples["sample_name"] == row["sample_name"]) & (seq_request_samples["library_type"].apply(lambda x: x.name) == row["library_type"])).any():
                self.spreadsheet.add_error(i + 1, "library_type", f"You already have '{row['library_type']}'-library from sample {row['sample_name']} in the request", "duplicate_value")

            if pd.isna(row["library_type"]):
                self.spreadsheet.add_error(i + 1, "library_type", "missing 'Library Type'", "missing_value")

            if pd.isna(row["genome"]):
                self.spreadsheet.add_error(i + 1, "genome", "missing 'Genome'", "missing_value")

            if self.index_specification_type == "kit":
                if pd.notna(row["index_i7"]) and pd.notna(row["index_well"]):
                    self.spreadsheet.add_error(i + 1, "index_i7", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    self.spreadsheet.add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    continue
                
                if pd.notna(row["index_well"]) and pd.notna(row["index_i5"]):
                    self.spreadsheet.add_error(i + 1, "index_i5", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    self.spreadsheet.add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name', not both", "invalid_value")
                    continue
            
                if pd.isna(row["index_i7"]) and pd.isna(row["index_well"]):
                    self.spreadsheet.add_error(i + 1, "index_i7", "You must specify 'Index Well' or 'Index Name'", "missing_value")
                    self.spreadsheet.add_error(i + 1, "index_well", "You must specify 'Index Well' or 'Index Name'", "missing_value")
                    continue
                
                assert kit_1_df is not None and kit_2_df is not None
                assert kit_1 is not None and kit_2 is not None

                if pd.isna(row["index_i7"]):
                    if len(index_i7_sequences := kit_1_df.loc[(kit_1_df["well"] == row["index_well"]) & (kit_1_df["type"] == BarcodeType.INDEX_I7), "sequence"].tolist()) == 0:  # type: ignore
                        self.spreadsheet.add_error(i + 1, "index_well", f"Well '{row['index_well']}' not found in specified index-kit for i7.", "invalid_value")
                        continue
                    
                    df.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                    df.at[idx, "index_i7_name"] = kit_1_df.loc[(kit_1_df["well"] == row["index_well"]) & (kit_1_df["type"] == BarcodeType.INDEX_I7)].iloc[0]["name"]
                    
                    if kit_2.type == IndexType.DUAL_INDEX:
                        if len(index_i5_sequences := kit_2_df.loc[(kit_2_df["well"] == row["index_well"]) & (kit_2_df["type"] == BarcodeType.INDEX_I5), "sequence"].tolist()) == 0:  # type: ignore
                            self.spreadsheet.add_error(i + 1, "index_well", f"Well '{row['index_well']}' not found in specified index-kit for i5.", "invalid_value")
                            continue
                        
                        df.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)
                        df.at[idx, "index_i5_name"] = kit_2_df.loc[(kit_2_df["well"] == row["index_well"]) & (kit_2_df["type"] == BarcodeType.INDEX_I5)].iloc[0]["name"]
                else:
                    if len(index_i7_sequences := kit_1_df.loc[(kit_1_df["name"] == row["index_i7"]) & (kit_1_df["type"] == BarcodeType.INDEX_I7), "sequence"].tolist()) == 0:  # type: ignore
                        self.spreadsheet.add_error(i + 1, "index_i7", f"Index i7 '{row['index_i7']}' not found in specified index-kit.", "invalid_value")
                        continue
                    
                    df.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                    df.at[idx, "index_i7_name"] = row["index_i7"]

                    if kit_2.type == IndexType.DUAL_INDEX:
                        if pd.isna(row["index_i5"]):
                            df.at[idx, "index_i5"] = row["index_i7"]
                            row["index_i5"] = row["index_i7"]
                            
                        if len(index_i5_sequences := kit_2_df.loc[(kit_2_df["name"] == row["index_i5"]) & (kit_2_df["type"] == BarcodeType.INDEX_I5), "sequence"].tolist()) == 0:  # type: ignore
                            self.spreadsheet.add_error(i + 1, "index_i5", f"Index i5 '{row['index_i5']}' not found in specified index-kit.", "invalid_value")
                            continue
                        
                        df.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)
                        df.at[idx, "index_i5_name"] = row["index_i5"]
            else:
                if pd.isna(row["index_i7"]):
                    self.spreadsheet.add_error(i + 1, "index_i7", "missing 'Index i7'", "missing_value")
                    continue
                
                index_i7_sequences = row["index_i7"].split(";")
                
                for index_i7_sequence in index_i7_sequences:
                    if len(unknown_bases := base_filter(index_i7_sequence)) > 0:
                        self.spreadsheet.add_error(i + 1, "index_i7", f"Invalid base(s) in 'Index i7': {', '.join(unknown_bases)}", "invalid_value")

                df.at[idx, "index_i7_sequences"] = ";".join(index_i7_sequences)
                
                if pd.notna(row["index_i5"]):
                    index_i5_sequences = row["index_i5"].split(";")
                    if len(index_i5_sequences) != len(index_i7_sequences):
                        self.spreadsheet.add_error(i + 1, "index_i5", "Number of 'Index i5'-barcodes sequences should match 'Index i7'-barcodes", "invalid_value")
                    for index_i5_sequence in index_i5_sequences:
                        if len(unknown_bases := base_filter(index_i5_sequence)) > 0:
                            self.spreadsheet.add_error(i + 1, "index_i5", f"Invalid base(s) in 'Index i5': {', '.join(unknown_bases)}", "invalid_value")

                    df.at[idx, "index_i5_sequences"] = ";".join(index_i5_sequences)

        if len(self.spreadsheet._errors) > 0:
            return False
        
        self.df = df
        return True
    
    def __map_library_types(self):
        library_type_map = {}
        for id, e in LibraryType.as_tuples():
            library_type_map[e.display_name] = id
        
        self.df["library_type_id"] = self.df["library_type"].map(library_type_map)
        self.df["library_name"] = self.df["sample_name"] + self.df["library_type_id"].apply(lambda x: f"_{LibraryType.get(x).identifier}")

    def __map_genome_ref(self):
        organism_map = {}
        for id, e in GenomeRef.as_tuples():
            organism_map[e.display_name] = id
        
        self.df["genome_id"] = self.df["genome"].map(organism_map)

    def __map_existing_samples(self):
        self.df["sample_id"] = None
        if self.metadata["project_id"] is None:
            return
        if (project := db.get_project(self.metadata["project_id"])) is None:
            logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
            raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
        
        for sample in project.samples:
            self.df.loc[self.df["sample_name"] == sample.name, "sample_id"] = sample.id

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.__map_library_types()
        self.__map_genome_ref()
        self.__map_existing_samples()

        sample_table_data = {
            "sample_name": [],
        }

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "genome": [],
            "genome_id": [],
            "library_type": [],
            "library_type_id": [],
            "index_well": [],
            "index_i7_sequences": [],
            "index_i7_name": [],
            "index_i5_sequences": [],
            "index_i5_name": [],
        }

        pooling_table = {
            "sample_name": [],
            "library_name": [],
        }

        for (sample_name), _df in self.df.groupby("sample_name"):
            sample_table_data["sample_name"].append(sample_name)

            for _, row in _df.iterrows():
                genome = GenomeRef.get(int(row["genome_id"]))
                library_type = LibraryType.get(int(row["library_type_id"]))
                library_name = f"{sample_name}_{library_type.identifier}"

                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(sample_name)
                library_table_data["genome"].append(genome.name)
                library_table_data["genome_id"].append(genome.id)
                library_table_data["library_type"].append(row["library_type"])
                library_table_data["library_type_id"].append(row["library_type_id"])
                library_table_data["index_well"].append(row["index_well"])
                library_table_data["index_i7_sequences"].append(row["index_i7_sequences"])
                library_table_data["index_i7_name"].append(row["index_i7_name"])
                library_table_data["index_i5_sequences"].append(row["index_i5_sequences"])
                library_table_data["index_i5_name"].append(row["index_i5_name"])

                pooling_table["sample_name"].append(sample_name)
                pooling_table["library_name"].append(library_name)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None

        sample_table = pd.DataFrame(sample_table_data)
        sample_table["sample_id"] = None
        sample_table["cmo_sequence"] = None
        sample_table["cmo_pattern"] = None
        sample_table["cmo_read"] = None
        sample_table["flex_barcode"] = None

        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.get_project(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        pooling_table = pd.DataFrame(pooling_table)

        self.add_table("library_table", library_table)
        self.add_table("sample_table", sample_table)
        self.add_table("pooling_table", pooling_table)
        self.update_data()

        if self.df["genome_id"].isna().any():
            organism_mapping_form = GenomeRefMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            organism_mapping_form.prepare()
            return organism_mapping_form.make_response()
        
        if self.df["library_type_id"].isna().any():
            library_mapping_form = LibraryMappingForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            library_mapping_form.prepare()
            return library_mapping_form.make_response()
        
        if self.df["library_type_id"].isin([
            LibraryType.TENX_MULTIPLEXING_CAPTURE.id,
        ]).any():
            cmo_reference_input_form = CMOReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return cmo_reference_input_form.make_response()
        
        if (self.df["library_type_id"].isin([LibraryType.TENX_VISIUM.id, LibraryType.TENX_VISIUM_FFPE.id, LibraryType.TENX_VISIUM_HD.id])).any():
            visium_annotation_form = VisiumAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            visium_annotation_form.prepare()
            return visium_annotation_form.make_response()
        
        if (self.df["library_type_id"] == LibraryType.TENX_ANTIBODY_CAPTURE.id).any():
            feature_reference_input_form = FeatureReferenceInputForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return feature_reference_input_form.make_response()
        
        if LibraryType.TENX_SC_GEX_FLEX.id in self.df["library_type_id"].values:
            frp_annotation_form = FRPAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
            return frp_annotation_form.make_response()
    
        sample_annotation_form = SampleAnnotationForm(seq_request=self.seq_request, previous_form=self, uuid=self.uuid)
        return sample_annotation_form.make_response()

        