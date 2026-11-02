from typing import Any, Literal, Protocol

import pandas as pd

from opengsync_db import models, queries as Q, categories as C

from opengsync_db.core.blueprints import pd_transforms as T

from ...components import inputs
from ...core import context
from ...utils import barcodes

RC_SUFFIX = " (Reverse Complement)"
# Kit options are "<kit_id>" or "<kit_id>:rc" so a kit matching in both orientations gets distinct values
CUSTOM = "0"
UNSELECTED = "-1"
DUAL_INDEX_TYPES = [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]


class _BarcodeMatchForm(Protocol):
    barcode_table: pd.DataFrame
    matched_rows: pd.Series
    index_type: C.IndexType | None
    i7_kit: inputs.selectable.SelectableInputField[str | None]
    i5_kit: inputs.selectable.SelectableInputField[str | None]
    i7_option: inputs.selectable.SelectableInputField[str | None]
    i5_option: inputs.selectable.SelectableInputField[str | None]
    i7_primer: inputs.string.TextAreaInputField[str | None]
    i5_primer: inputs.string.TextAreaInputField[str | None]
    _context: dict[str, Any]


class BarcodeMatchMixin:
    """Shared kit matching and orientation logic for the barcode match step of the
    library annotation and reindex workflows.

    Kits are matched per index: a kit is offered for i7 (i5) only if it contains every i7 (i5)
    sequence of the table, otherwise the only option is Custom. i7 and i5 may use different kits.

    Orientation rules: a kit selection sets FORWARD, the "forward" and "rc" options set
    FORWARD_NOT_VALIDATED ("rc" reverse-complements the sequences first), "idk" leaves it unset.
    """

    @staticmethod
    def make_kit_field(index: Literal["i7", "i5"]) -> inputs.selectable.SelectableInputField[str | None]:
        return inputs.selectable.SelectableInputField(f"{index} Kit", [(CUSTOM, "Custom")], required=False, default=UNSELECTED)

    @staticmethod
    def make_option_field(index: Literal["i7", "i5"]) -> inputs.selectable.SelectableInputField[str | None]:
        return inputs.selectable.SelectableInputField(
            f"Index {index} was not found in the database. Please select how to proceed:",
            [
                ("forward", f"I have provided {index} barcode sequences in forward orientation"),
                ("rc", f"I have provided {index} barcode sequences in reverse complement orientation"),
                ("idk", f"I don't know in which orientation the {index} barcodes are provided"),
            ],
            required=False,
            placeholder="Select an option",
        )

    @staticmethod
    def make_primer_field(index: Literal["i7", "i5"]) -> inputs.string.TextAreaInputField[str | None]:
        return inputs.string.TextAreaInputField(f"{index} Primer Sequence", required=False, placeholder="Required if using custom kit")

    def init_barcode_match(self: _BarcodeMatchForm, barcode_table: pd.DataFrame) -> None:
        self.barcode_table = barcode_table.copy()
        # 10X ATAC indices are not matched/re-oriented here
        self.matched_rows = self.barcode_table["index_type_id"] != C.IndexType.TENX_ATAC_INDEX.id
        self.index_type = barcodes.check_index_type(self.barcode_table[self.matched_rows])
        self._context["index_type"] = self.index_type
        # Kit options are needed for both rendering and resolving the submitted kit on POST
        BarcodeMatchMixin._set_kit_options(self)

    def _set_kit_options(self: _BarcodeMatchForm) -> None:
        session = context.ctx.session
        df = self.barcode_table[self.matched_rows]

        def match_kits(sequences: pd.Series, barcode_type: C.BarcodeType) -> pd.DataFrame:
            unique_sequences = list(set(s for s in sequences.tolist() if pd.notna(s)))
            if not unique_sequences:
                return pd.DataFrame()
            return session.get_pandas(
                Q.pd.match_barcodes_to_kit(unique_sequences, len(unique_sequences), barcode_type.id),
                limit=None,
            )

        kits: dict[int, str] = {}

        def kit_options(index: Literal["i7", "i5"], barcode_type: C.BarcodeType) -> list[tuple[str, str]]:
            sequences = df[f"sequence_{index}"]
            rc_sequences = sequences.apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            options: list[tuple[str, str]] = []
            for seqs, value, suffix in ((sequences, "{}", ""), (rc_sequences, "{}:rc", RC_SUFFIX)):
                for _, row in match_kits(seqs, barcode_type).iterrows():
                    kits[row["kit_id"]] = f'[{row["kit_identifier"]}] {row["kit_name"]}'
                    options.append((value.format(row["kit_id"]), kits[row["kit_id"]] + suffix))
            return options

        self.i7_kit.set_options([(CUSTOM, "Custom")] + kit_options("i7", C.BarcodeType.INDEX_I7))
        self.i5_kit.set_options([(CUSTOM, "Custom")] + kit_options("i5", C.BarcodeType.INDEX_I5))

        self._context["kits"] = list(kits.items())

    @staticmethod
    def _parse_kit(data: str | None) -> tuple[int, bool] | None:
        """(kit_id, reverse_complement) of a kit selection, None for Custom/unselected."""
        if data is None or data in (CUSTOM, UNSELECTED):
            return None
        kit_id, _, rc = data.partition(":")
        return int(kit_id), rc == "rc"

    def validate_barcode_match(self: _BarcodeMatchForm) -> None:
        dual_index = self.index_type in DUAL_INDEX_TYPES

        for index, kit_field, required in (("i7", self.i7_kit, True), ("i5", self.i5_kit, dual_index)):
            if kit_field.data in (None, UNSELECTED):
                if required:
                    kit_field.errors.append(f"Please select an {index} kit or choose Custom.")
                else:
                    kit_field.data = UNSELECTED
            elif kit_field.data not in kit_field._mapping:
                # Only kits containing all of the index's sequences are offered
                kit_field.errors.append(f"The selected kit does not contain all {index} sequences. Please choose one of the offered kits or Custom.")

        if self.i7_kit.data == CUSTOM and not self.i7_option.data:
            self.i7_option.errors.append("Please select how to proceed with the i7 index.")
        if self.i7_kit.data == CUSTOM and not self.i7_primer.data:
            self.i7_primer.errors.append("Please provide the i7 primer sequence.")

        if self.i5_kit.data == CUSTOM and not self.i5_primer.data and dual_index:
            self.i5_primer.errors.append("Please provide the i5 primer sequence.")
        if self.i5_kit.data == CUSTOM and not self.i5_option.data and dual_index:
            self.i5_option.errors.append("Please select how to proceed with the i5 index.")

    def apply_barcode_match(self: _BarcodeMatchForm) -> pd.DataFrame:
        """Returns the barcode table with the selected kits or orientation options applied."""
        session = context.ctx.session
        barcode_table = self.barcode_table.copy()
        rows = self.matched_rows
        kits: dict[int, tuple[models.IndexKit, pd.DataFrame]] = {}

        def reverse_complement(col: str) -> None:
            barcode_table.loc[rows, col] = barcode_table.loc[rows, col].apply(
                lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None
            )

        for index, kit_field, option_field in (
            ("i7", self.i7_kit, self.i7_option),
            ("i5", self.i5_kit, self.i5_option),
        ):
            sequence_col = f"sequence_{index}"
            if (selection := BarcodeMatchMixin._parse_kit(kit_field.data)) is not None:
                kit_id, rc = selection
                if kit_id not in kits:
                    kit = session.get_one(Q.index_kit.select(id=kit_id))
                    kit_df = T.index_kit_barcodes(
                        session.get_pandas(Q.pd.index_kit_barcodes(kit.id), limit=None),
                        per_adapter=False,
                        per_index=True,
                    )
                    kits[kit_id] = (kit, T.index_kit_barcodes_per_index(kit_df, kit.type))
                kit, kit_df = kits[kit_id]

                if rc:
                    reverse_complement(sequence_col)

                # A sequence can occur in several adapters (e.g. shared i5) and combinatorial kits
                # have no sequence for the other index, so the lookup needs a unique, non-null index
                names = kit_df.dropna(subset=[sequence_col]).drop_duplicates(sequence_col).set_index(sequence_col)[f"name_{index}"]
                barcode_table.loc[rows, f"name_{index}"] = barcode_table.loc[rows, sequence_col].map(names)
                barcode_table.loc[rows, f"kit_{index}_id"] = kit.id
                barcode_table.loc[rows, f"kit_{index}"] = kit.identifier
                barcode_table.loc[rows, f"orientation_{index}_id"] = C.BarcodeOrientation.FORWARD.id
            elif option_field.data == "rc":
                reverse_complement(sequence_col)
                barcode_table.loc[rows, f"orientation_{index}_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id
            elif option_field.data == "forward":
                barcode_table.loc[rows, f"orientation_{index}_id"] = C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id

        return barcode_table

    def barcode_match_metadata(self: _BarcodeMatchForm) -> dict[str, Any]:
        return {
            "i7_kit": self.i7_kit.data,
            "i5_kit": self.i5_kit.data,
            "i7_option": self.i7_option.data,
            "i5_option": self.i5_option.data,
            "i7_primer": self.i7_primer.data,
            "i5_primer": self.i5_primer.data,
        }

    def fill_barcode_match(self: _BarcodeMatchForm, metadata: dict[str, Any]) -> None:
        # str(): workflows started before kit options became strings stored the kit id as int
        for kit_field, key in ((self.i7_kit, "i7_kit"), (self.i5_kit, "i5_kit")):
            kit_field.data = UNSELECTED if (data := metadata.get(key)) is None else str(data)
        self.i7_option.data = metadata.get("i7_option")
        self.i5_option.data = metadata.get("i5_option")
        self.i7_primer.data = metadata.get("i7_primer")
        self.i5_primer.data = metadata.get("i5_primer")
