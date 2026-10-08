from typing import Any, Literal, Protocol

import pandas as pd

from opengsync_db import models, queries as Q, categories as C

from opengsync_db.core.blueprints import pd_transforms as T

from ...components import inputs
from ...core import context
from ...utils import barcodes

RC_SUFFIX = " (Reverse Complement)"
DUAL_INDEX_TYPES = [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]


class _BarcodeMatchForm(Protocol):
    barcode_table: pd.DataFrame
    matched_rows: pd.Series
    index_type: C.IndexType | None
    i7_kit: inputs.selectable.SelectableInputField[int | None]
    i5_kit: inputs.selectable.SelectableInputField[int | None]
    i7_option: inputs.selectable.SelectableInputField[str | None]
    i5_option: inputs.selectable.SelectableInputField[str | None]
    i7_primer: inputs.string.TextAreaInputField[str | None]
    i5_primer: inputs.string.TextAreaInputField[str | None]
    _context: dict[str, Any]


class BarcodeMatchMixin:
    """Shared kit matching and orientation logic for the barcode match step of the
    library annotation and reindex workflows.

    Orientation rules: a kit selection sets FORWARD, the "forward" and "rc" options set
    FORWARD_NOT_VALIDATED ("rc" reverse-complements the sequences first), "idk" leaves it unset.
    """

    @staticmethod
    def make_kit_field(index: Literal["i7", "i5"]) -> inputs.selectable.SelectableInputField[int | None]:
        return inputs.selectable.SelectableInputField(f"{index} Kit", [(0, "Custom")], required=False, default=-1)

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

        def kit_options(index: Literal["i7", "i5"], barcode_type: C.BarcodeType) -> list[tuple[int, str]]:
            sequences = df[f"sequence_{index}"]
            rc_sequences = sequences.apply(lambda x: models.Barcode.reverse_complement(x) if pd.notna(x) else None)
            options: list[tuple[int, str]] = []
            for _, row in match_kits(sequences, barcode_type).iterrows():
                options.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}'))
            for _, row in match_kits(rc_sequences, barcode_type).iterrows():
                options.append((row["kit_id"], f'[{row["kit_identifier"]}] {row["kit_name"]}' + RC_SUFFIX))
            return options

        kit_i7s = kit_options("i7", C.BarcodeType.INDEX_I7)
        kit_i5s = kit_options("i5", C.BarcodeType.INDEX_I5)

        self.i7_kit.set_options([(0, "Custom")] + kit_i7s)
        self.i5_kit.set_options([(0, "Custom")] + kit_i5s)

        self._context["kits"] = list(set(kit_i7s + kit_i5s))

    def validate_barcode_match(self: _BarcodeMatchForm) -> None:
        dual_index = self.index_type in DUAL_INDEX_TYPES

        if self.i7_kit.data == -1:
            self.i7_kit.errors.append("Please select an i7 kit or choose Custom.")
        if self.i5_kit.data == -1 and dual_index:
            self.i5_kit.errors.append("Please select an i5 kit or choose Custom.")

        if self.i7_kit.data == 0 and not self.i7_option.data:
            self.i7_option.errors.append("Please select how to proceed with the i7 index.")
        if self.i7_kit.data == 0 and not self.i7_primer.data:
            self.i7_primer.errors.append("Please provide the i7 primer sequence.")

        if self.i5_kit.data == 0 and not self.i5_primer.data and dual_index:
            self.i5_primer.errors.append("Please provide the i5 primer sequence.")
        if self.i5_kit.data == 0 and not self.i5_option.data and dual_index:
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
            if (kit_id := kit_field.data) is not None and kit_id > 0:
                if kit_id not in kits:
                    kit = session.get_one(Q.index_kit.select(id=kit_id))
                    kit_df = T.index_kit_barcodes(
                        session.get_pandas(Q.pd.index_kit_barcodes(kit.id), limit=None),
                        per_adapter=False,
                        per_index=True,
                    )
                    kits[kit_id] = (kit, T.index_kit_barcodes_per_index(kit_df, kit.type))
                kit, kit_df = kits[kit_id]

                if (kit_field.value or "").endswith(RC_SUFFIX):
                    reverse_complement(sequence_col)

                barcode_table.loc[rows, f"name_{index}"] = barcode_table.loc[rows, sequence_col].map(
                    kit_df.set_index(sequence_col)[f"name_{index}"]
                )
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
        self.i7_kit.data = metadata.get("i7_kit", -1)
        self.i5_kit.data = metadata.get("i5_kit", -1)
        self.i7_option.data = metadata.get("i7_option")
        self.i5_option.data = metadata.get("i5_option")
        self.i7_primer.data = metadata.get("i7_primer")
        self.i5_primer.data = metadata.get("i5_primer")
