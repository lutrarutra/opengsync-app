from fastapi import Depends, Response
import pandas as pd

from opengsync_db import categories as C

from ....components import inputs
from ....components.tables import CategoricalDropDown, DBObjectColumn, InvalidCellValue, TextColumn
from ....utils import barcodes
from ...HTMXForm import RouteFunc, htmx_route
from .IndexCheckWorkflow import IndexCheckWorkflowStep, IndexCheckWorkflow


FORWARD = "forward"
REVERSE_COMPLEMENT = "reverse_complement"
INDEX_COLUMN = "Library [Index ID]"


def _has_value(value) -> bool:
    return pd.notna(value) and value != ""


def _value(value) -> str | None:
    return str(value).strip() if _has_value(value) else None


def _is_kit_barcode(kit, name) -> bool:
    """A single barcode (i7 or i5) comes from a kit if it has both a kit and a name."""
    return _has_value(kit) and _has_value(name)


def _is_kit_index_row(row: pd.Series) -> bool:
    """Same rule as LibraryIndex.is_kit_index(): i7 from a kit, and i5 too if present."""
    if not _is_kit_barcode(row.get("kit_i7"), row.get("name_i7")):
        return False
    if not _has_value(row.get("sequence_i5")):
        return True
    return _is_kit_barcode(row.get("kit_i5"), row.get("name_i5"))


class VerifyOrientationsForm(IndexCheckWorkflowStep):
    template_path = "workflows/index_check/verify-orientations.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            # One row per index: the id in brackets is the library index id, not the library id
            DBObjectColumn(
                columns=("library_index_id", "library_name"),
                types=(int, str),
                label=INDEX_COLUMN,
                width=300,
                categories={},
                required=True,
                read_only=True,
            ),
            CategoricalDropDown(
                "orientation", "Orientation", 200,
                categories={FORWARD: "Forward", REVERSE_COMPLEMENT: "Reverse Complement"},
                required=True,
            ),
            TextColumn("name_i7", "i7 Name", 150, read_only=True),
            TextColumn("sequence_i7", "i7 Sequence", 200, read_only=True),
            TextColumn("name_i5", "i5 Name", 150, read_only=True),
            TextColumn("sequence_i5", "i5 Sequence", 200, read_only=True),
        ],
        allow_new_rows=False,
    )

    def __init__(self, workflow: IndexCheckWorkflow) -> None:
        super().__init__(workflow=workflow)
        barcode_table = workflow.tables["barcode_table"]
        # Libraries without an index have nothing to verify
        self.barcode_table = barcode_table[barcode_table["library_index_id"].notna()].reset_index(drop=True)

        if "orientation" not in self.barcode_table.columns:
            # Suggest reverse complement where the stored orientation already says so
            self.barcode_table["orientation"] = [
                REVERSE_COMPLEMENT if orientation_id == C.BarcodeOrientation.REVERSE_COMPLEMENT_NOT_VALIDATED.id else FORWARD
                for orientation_id in self.barcode_table["orientation_id"]
            ]

        self.spreadsheet.columns[INDEX_COLUMN].set_categories({
            int(row["library_index_id"]): f"{row['library_name']} [{int(row['library_index_id'])}]"
            for _, row in self.barcode_table.iterrows()
        })
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url, df=self.barcode_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "VerifyOrientationsForm" = Depends(VerifyOrientationsForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "VerifyOrientationsForm" = Depends(VerifyOrientationsForm.Validate()),
        ) -> Response:
            barcode_table = form.barcode_table

            # Only the index id and the orientation are read from the spreadsheet. Rows can be sorted, so each row
            # is matched to its stored index by id, and everything else always comes from the stored table.
            unmatched = {int(barcode_table.at[i, "library_index_id"]): i for i in range(len(barcode_table))}

            rows_match = True
            for idx, row in form.spreadsheet.data.iterrows():
                index_id = row["library_index_id"]
                i = unmatched.pop(int(index_id), None) if pd.notna(index_id) else None
                if i is None:
                    rows_match = False
                    form.spreadsheet.add_error(idx, INDEX_COLUMN, InvalidCellValue("Row does not match an index of the selected libraries."))
                    continue
                barcode_table.at[i, "orientation"] = row["orientation"]
                if row["orientation"] == REVERSE_COMPLEMENT and _is_kit_index_row(barcode_table.iloc[i]):
                    form.spreadsheet.add_error(idx, "orientation", InvalidCellValue("Barcodes from a kit are always in forward orientation."))

            if rows_match and unmatched:
                form.spreadsheet.add_general_error("Some indices are missing from the spreadsheet. Go back and select the libraries again.")
            form.assert_valid()

            orientation_results = []
            for _, row in barcode_table.iterrows():
                sequence_i7, sequence_i5 = _value(row["sequence_i7"]), _value(row["sequence_i5"])
                was_rc = row["orientation"] == REVERSE_COMPLEMENT
                if was_rc:
                    # Only custom barcodes are reverse complemented, e.g. a custom i5 next to a kit i7
                    if sequence_i7 is not None and not _is_kit_barcode(row["kit_i7"], row["name_i7"]):
                        sequence_i7 = barcodes.reverse_complement(sequence_i7)
                    if sequence_i5 is not None and not _is_kit_barcode(row["kit_i5"], row["name_i5"]):
                        sequence_i5 = barcodes.reverse_complement(sequence_i5)

                orientation_results.append({
                    "library_id": int(row["library_id"]),
                    "library_index_id": int(row["library_index_id"]),
                    "library_name": row["library_name"],
                    "sequence_i7": sequence_i7,
                    "sequence_i5": sequence_i5,
                    "orientation": C.BarcodeOrientation.FORWARD,
                    "was_reverse_complemented": was_rc,
                })

            # Keep the choices so going back from the summary shows them again
            form.workflow.tables["barcode_table"] = barcode_table
            form.workflow.metadata["orientation_results"] = orientation_results
            return form.workflow.get_next_step(form).make_response()
        return route
