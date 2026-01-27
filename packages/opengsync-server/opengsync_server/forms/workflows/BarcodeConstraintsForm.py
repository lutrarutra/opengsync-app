import pandas as pd

from dataclasses import dataclass

from flask import Response, url_for
from wtforms import FormField, IntegerField
from wtforms.validators import Optional as OptionalValidator

from opengsync_db.categories import IndexType

from ... import logger, db
from ...core import exceptions
from ...tools import utils
from ...tools.spread_sheet_components import TextColumn
from ..HTMXFlaskForm import HTMXFlaskForm
from ..SpreadsheetInput import SpreadsheetInput
from ..SearchBar import OptionalSearchBar

@dataclass
class Index():
    name: str
    well: str
    sequence: str

@dataclass
class DualIndex():
    well: str
    name_i7: str
    sequence_i7: str
    name_i5: str
    sequence_i5: str


class BarcodeConstraintsForm(HTMXFlaskForm):
    _template_path = "workflows/barcode_constraints.html"
    _workflow_name = "check_barcode_constraints"
    _step_name = "barcode_contraints_form"

    kit = FormField(OptionalSearchBar, label="Select Kit")

    min_samples = IntegerField("Minimum Number of Samples", validators=[OptionalValidator()], default=None)

    columns: list = [
        TextColumn("sequence_i7", "Sequence i7", 300),
        TextColumn("sequence_i5", "Sequence i5", 300),
    ]

    def __init__(self, formdata: dict | None):
        HTMXFlaskForm.__init__(self, formdata=formdata)

        self.post_url = url_for("check_barcode_constraints_workflow.check")

        self.spreadsheet = SpreadsheetInput(
            columns=BarcodeConstraintsForm.columns,
            post_url=self.post_url,
            csrf_token=self._csrf_token,
            formdata=formdata,
            allow_new_rows=True,
            can_be_empty=True
        )
        self.needed_additions_i7: list[list[Index]] = []
        self.needed_additions_i5: list[list[Index]] = []
        self.needed_additions: list[list[DualIndex]] = []
        self.additional_sequences: list[tuple[str | None, str | None]] = []
        self.needed_bases = ["T", "C"]
        self.active_tab = "form-tab-form"

    def validate(self) -> bool:
        if not super().validate():
            return False
                
        kit_sequences_i7: list[str] = []
        kit_sequences_i5: list[str] = []
        additional_sequences: list[str] = []
        kit = None
        
        if self.kit.selected.data is not None:
            if (kit := db.index_kits.get(int(self.kit.selected.data))) is None:
                raise exceptions.NotFoundException("Kit not found")
            
            self.kit.search_bar.data = kit.search_name()
            
            if kit.type == IndexType.TENX_ATAC_INDEX:
                self.spreadsheet.add_general_error("10x ATAC index kits are not supported. 10X ATAC kits should be safe!")
                return False

            barcodes_df = db.pd.get_index_kit_barcodes(kit.id, per_index=True)
            if len(barcodes_df["sequence_i7"].str.len().unique()) != 1:
                self.spreadsheet.add_general_error(f"The selected kit '{kit.name}' has i7 index sequences of different lengths and cannot be used.")
                return False
            
            if len(barcodes_df["sequence_i5"].str.len().unique()) != 1:
                self.spreadsheet.add_general_error(f"The selected kit '{kit.name}' has i5 index sequences of different lengths and cannot be used.")
                return False

            kit_i7_len = len(barcodes_df["sequence_i7"].values[0])
            kit_i5_len = len(barcodes_df["sequence_i5"].values[0])
            
            kit_sequences_i7 = barcodes_df["sequence_i7"].to_list()
            kit_sequences_i5 = barcodes_df["sequence_i5"].to_list()
            additional_sequences = [s1 + s2 for s1, s2 in zip(kit_sequences_i7, kit_sequences_i5)]
                        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df

        logger.debug(df)
        logger.debug(df.dtypes)

        if len(df["sequence_i7"].str.len().unique()) > 1:
            self.spreadsheet.add_general_error("All i7 index sequences must be the same length")
            return False
        
        if len(df["sequence_i5"].str.len().unique()) > 1:
            self.spreadsheet.add_general_error("All i5 index sequences must be the same length")
            return False

        sequences_i7 = [s for s in df["sequence_i7"] if pd.notna(s) and s]
        sequences_i5 = [s for s in df["sequence_i5"] if pd.notna(s) and s]
        
        for i in range(max(len(sequences_i7), len(sequences_i5))):
            if i < len(sequences_i7):
                seq_i7 = sequences_i7[i]
            else:
                seq_i7 = None
            if i < len(sequences_i5):
                seq_i5 = sequences_i5[i]
            else:
                seq_i5 = None

            self.additional_sequences.append((seq_i7, seq_i5))

        self.active_tab = "sequences-tab-form"
            
        # No additional sequences provided
        if not sequences_i7 and not sequences_i5:
            if not additional_sequences:
                self.spreadsheet.add_general_error("Select an index kit or provide some barcodes")
            else:
                needed_additions = utils.generate_valid_combinations(
                    indices=[], additional_indices=additional_sequences, min_samples=self.min_samples.data,
                )
                mapping = barcodes_df.set_index("sequence_i7")  # type: ignore
                for a in needed_additions:
                    res = []
                    for s in a:
                        seq_i7 = s[:kit_i7_len]  # type: ignore
                        seq_i5 = s[kit_i7_len:]  # type: ignore
                        res.append(
                            DualIndex(
                                name_i7=mapping.at[seq_i7, "name_i7"],  # type: ignore
                                name_i5=mapping.at[seq_i7, "name_i5"],  # type: ignore
                                well=mapping.at[seq_i7, "well"],  # type: ignore
                                sequence_i7=seq_i7,
                                sequence_i5=seq_i5
                            )
                        )
                    self.needed_additions.append(res)
        # Dual Index
        elif sequences_i7 and sequences_i5:
            if kit is not None:
                if kit.type != IndexType.DUAL_INDEX:
                    self.spreadsheet.add_general_error(f"The selected kit '{kit.name}' is not a dual index kit.")
                    return False
                
                additional_sequences = [s1 + s2 for s1, s2 in zip(kit_sequences_i7, kit_sequences_i5)]
            else:
                additional_sequences = []
                
            if len(sequences_i7) != len(sequences_i5):
                self.spreadsheet.add_general_error("The number of i7 and i5 sequences must be the same")
                return False
            
            sequences = [s1 + s2 for s1, s2 in zip(sequences_i7, sequences_i5)]
            if not utils.check_index_constraints(sequences):
                if not additional_sequences:
                    self.spreadsheet.add_general_error("Index constraints not met. Select another kit.")
                    self.kit.selected.errors = ["Index constraints not met. Select another kit."]
                else:
                    needed_additions = utils.generate_valid_combinations(sequences, additional_indices=additional_sequences, min_samples=self.min_samples.data)
                    mapping = barcodes_df.set_index("sequence_i7")  # type: ignore
                    for a in needed_additions:
                        res = []
                        for s in a:
                            seq_i7 = s[:kit_i7_len]  # type: ignore
                            seq_i5 = s[kit_i7_len:]  # type: ignore
                            res.append(
                                DualIndex(
                                    name_i7=mapping.at[seq_i7, "name_i7"],  # type: ignore
                                    name_i5=mapping.at[seq_i7, "name_i5"],  # type: ignore
                                    well=mapping.at[seq_i7, "well"],  # type: ignore
                                    sequence_i7=seq_i7,
                                    sequence_i5=seq_i5
                                )
                            )
                        self.needed_additions.append(res)
        # Single Index (i7 or i5)
        else:
            if sequences_i7 and not utils.check_index_constraints(sequences_i7):
                if not kit_sequences_i7:
                    self.spreadsheet.add_general_error("i7 index constraints not met. Select kit another kit.")
                else:
                    needed_additions_i7 = utils.generate_valid_combinations(sequences_i7, additional_indices=kit_sequences_i7)
                    for a in needed_additions_i7:
                        res = []
                        for s in a:
                            mapping = barcodes_df.set_index("sequence_i7")  # type: ignore
                            res.append(
                                Index(
                                    name=mapping.at[s, "name_i7"],  # type: ignore
                                    well=mapping.at[s, "well"],  # type: ignore
                                    sequence=s
                                )
                            )
                        self.needed_additions_i7.append(res)
                    
            if sequences_i5 and not utils.check_index_constraints(sequences_i5):
                if not kit_sequences_i5:
                    self.spreadsheet.add_general_error("i5 index constraints not met. Select kit another kit.")
                else:
                    needed_additions_i5 = utils.generate_valid_combinations(sequences_i5, additional_indices=kit_sequences_i5)
                    for a in needed_additions_i5:
                        res = []
                        for s in a:
                            mapping = barcodes_df.set_index("sequence_i5")  # type: ignore
                            res.append(
                                Index(
                                    name=mapping.at[s, "name_i5"],  # type: ignore
                                    well=mapping.at[s, "well"],  # type: ignore
                                    sequence=s
                                )
                            )
                        self.needed_additions_i5.append(res)
        return True

    def process_request(self) -> Response:
        self.validate()
        return self.make_response()