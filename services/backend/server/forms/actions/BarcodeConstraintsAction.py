import pandas as pd
from fastapi import Depends

from opengsync_db import queries as Q, SyncSession, categories as C

from ...core import dependencies, responses
from ...utils import barcodes
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class BarcodeConstraintsAction(HTMXForm):
    template_path = "workflows/barcode_constraints.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            TextColumn("sequence_i7", "Sequence i7", 300),
            TextColumn("sequence_i5", "Sequence i5", 300),
        ],
        allow_new_rows=True,
        can_be_empty=True,
    )
    kit = inputs.searchable.SearchableInputField("Select Kit", route="search_index_kits", required=False)
    min_samples = inputs.numeric.IntInputField("Minimum Number of Samples", required=False, ge=1)

    def __init__(self) -> None:
        super().__init__()
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")
        self.needed_additions_i7: list[list] = []
        self.needed_additions_i5: list[list] = []
        self.needed_additions: list[list] = []
        self.additional_sequences: list[tuple[str | None, str | None]] = []
        self.needed_bases = ["T", "C"]
        self.active_tab = "form-tab-form"

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency() -> "BarcodeConstraintsAction":
            return BarcodeConstraintsAction()
        return dependency

    @htmx_route("GET", "/check-barcode-constraints")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "BarcodeConstraintsAction" = Depends(BarcodeConstraintsAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/check-barcode-constraints")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "BarcodeConstraintsAction" = Depends(BarcodeConstraintsAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> responses.Response:
            kit_sequences_i7: list[str] = []
            kit_sequences_i5: list[str] = []
            additional_sequences: list[str] = []
            kit = None
            kit_i7_len = 0
            kit_i5_len = 0
            barcodes_df = None

            if form.kit.data is not None:
                kit = session.get_one(Q.index_kit.select(id=int(form.kit.data)))
                if kit.type == C.IndexType.TENX_ATAC_INDEX:
                    form.spreadsheet.add_general_error("10x ATAC index kits are not supported. 10X ATAC kits should be safe!")
                    form.assert_valid()

                barcodes_df = session.pd.get_index_kit_barcodes(kit.id, per_index=True)
                if len(barcodes_df["sequence_i7"].str.len().unique()) != 1:
                    form.spreadsheet.add_general_error(f"The selected kit '{kit.name}' has i7 index sequences of different lengths and cannot be used.")
                    form.assert_valid()

                if len(barcodes_df["sequence_i5"].str.len().unique()) != 1:
                    form.spreadsheet.add_general_error(f"The selected kit '{kit.name}' has i5 index sequences of different lengths and cannot be used.")
                    form.assert_valid()

                kit_i7_len = len(barcodes_df["sequence_i7"].values[0])
                kit_i5_len = len(barcodes_df["sequence_i5"].values[0])
                kit_sequences_i7 = barcodes_df["sequence_i7"].to_list()
                kit_sequences_i5 = barcodes_df["sequence_i5"].to_list()
                additional_sequences = [s1 + s2 for s1, s2 in zip(kit_sequences_i7, kit_sequences_i5)]

            df = form.spreadsheet.data

            if not df.empty and len(df["sequence_i7"].str.len().unique()) > 1:
                form.spreadsheet.add_general_error("All i7 index sequences must be the same length")
                form.assert_valid()

            if not df.empty and len(df["sequence_i5"].str.len().unique()) > 1:
                form.spreadsheet.add_general_error("All i5 index sequences must be the same length")
                form.assert_valid()

            sequences_i7 = [s for s in df["sequence_i7"] if pd.notna(s) and s]
            sequences_i5 = [s for s in df["sequence_i5"] if pd.notna(s) and s]

            form.additional_sequences = []
            for i in range(max(len(sequences_i7), len(sequences_i5))):
                seq_i7 = sequences_i7[i] if i < len(sequences_i7) else None
                seq_i5 = sequences_i5[i] if i < len(sequences_i5) else None
                form.additional_sequences.append((seq_i7, seq_i5))

            form.active_tab = "sequences-tab-form"

            # No additional sequences provided
            if not sequences_i7 and not sequences_i5:
                if not additional_sequences:
                    form.spreadsheet.add_general_error("Select an index kit or provide some barcodes")
                    return form.make_response()

                needed = barcodes.generate_valid_combinations(
                    indices=[], additional_indices=additional_sequences, min_samples=form.min_samples.data,
                )
                if barcodes_df is not None:
                    mapping = barcodes_df.set_index("sequence_i7")
                    for combo in needed:
                        res = []
                        for s in combo:
                            seq7 = s[:kit_i7_len]
                            seq5 = s[kit_i7_len:]
                            res.append({
                                "name_i7": mapping.at[seq7, "name_i7"],
                                "name_i5": mapping.at[seq7, "name_i5"],
                                "well": mapping.at[seq7, "well"],
                                "sequence_i7": seq7,
                                "sequence_i5": seq5,
                            })
                        form.needed_additions.append(res)

            # Dual Index
            elif sequences_i7 and sequences_i5:
                if kit is not None and kit.type != C.IndexType.DUAL_INDEX:
                    form.spreadsheet.add_general_error(f"The selected kit '{kit.name}' is not a dual index kit.")
                    return form.make_response()

                if len(sequences_i7) != len(sequences_i5):
                    form.spreadsheet.add_general_error("The number of i7 and i5 sequences must be the same")
                    return form.make_response()

                sequences = [s1 + s2 for s1, s2 in zip(sequences_i7, sequences_i5)]
                if not barcodes.check_index_constraints(sequences):
                    if not additional_sequences:
                        form.spreadsheet.add_general_error("Index constraints not met. Select another kit.")
                        form.kit.errors.append("Index constraints not met. Select another kit.")
                    else:
                        needed = barcodes.generate_valid_combinations(sequences, additional_indices=additional_sequences, min_samples=form.min_samples.data)
                        if barcodes_df is not None:
                            mapping = barcodes_df.set_index("sequence_i7")
                            for combo in needed:
                                res = []
                                for s in combo:
                                    seq7 = s[:kit_i7_len]
                                    seq5 = s[kit_i7_len:]
                                    res.append({
                                        "name_i7": mapping.at[seq7, "name_i7"],
                                        "name_i5": mapping.at[seq7, "name_i5"],
                                        "well": mapping.at[seq7, "well"],
                                        "sequence_i7": seq7,
                                        "sequence_i5": seq5,
                                    })
                                form.needed_additions.append(res)

            # Single Index (i7 or i5)
            else:
                if sequences_i7 and not barcodes.check_index_constraints(sequences_i7):
                    if not kit_sequences_i7:
                        form.spreadsheet.add_general_error("i7 index constraints not met. Select another kit.")
                    else:
                        needed_i7 = barcodes.generate_valid_combinations(sequences_i7, additional_indices=kit_sequences_i7)
                        if barcodes_df is not None:
                            mapping = barcodes_df.set_index("sequence_i7")
                            for combo in needed_i7:
                                res = []
                                for s in combo:
                                    res.append({
                                        "name": mapping.at[s, "name_i7"],
                                        "well": mapping.at[s, "well"],
                                        "sequence": s,
                                    })
                                form.needed_additions_i7.append(res)

                if sequences_i5 and not barcodes.check_index_constraints(sequences_i5):
                    if not kit_sequences_i5:
                        form.spreadsheet.add_general_error("i5 index constraints not met. Select another kit.")
                    else:
                        needed_i5 = barcodes.generate_valid_combinations(sequences_i5, additional_indices=kit_sequences_i5)
                        if barcodes_df is not None:
                            mapping = barcodes_df.set_index("sequence_i5")
                            for combo in needed_i5:
                                res = []
                                for s in combo:
                                    res.append({
                                        "name": mapping.at[s, "name_i5"],
                                        "well": mapping.at[s, "well"],
                                        "sequence": s,
                                    })
                                form.needed_additions_i5.append(res)

            return form.make_response()
        return route