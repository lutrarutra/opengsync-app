from typing import Any, Protocol

import pandas as pd

from opengsync_db import models, queries as Q, categories as C

from ...components import inputs
from ...components.tables import MissingCellValue, InvalidCellValue
from ...components.tables.spreadsheet import CategoricalDropDown, SpreadSheetColumn, TextColumn
from ...core import context


class _BarcodeInputForm(Protocol):
    spreadsheet: inputs.spreadsheet.SpreadsheetInputField[Any]

    def assert_valid(self) -> None:
        ...


class BarcodeInputMixin:    
    @staticmethod
    def make_spreadsheet(
        library_column: SpreadSheetColumn,
    ) -> inputs.spreadsheet.SpreadsheetInputField[pd.DataFrame]:
        return inputs.spreadsheet.SpreadsheetInputField(
            columns=[
                library_column,
                TextColumn("index_well", "Index Well", 100, max_length=8),
                CategoricalDropDown("kit_i7", "i7 Kit", 200, categories=lambda: {
                    kit.identifier: f"[{kit.identifier}] {kit.name}"
                    for kit in context.ctx.session.get_all(
                        Q.index_kit.select(type_in=[
                            C.IndexType.DUAL_INDEX,
                            C.IndexType.SINGLE_INDEX_I7,
                            C.IndexType.COMBINATORIAL_DUAL_INDEX,
                        ]),
                        order_by=models.IndexKit.name.desc(),
                        limit=None,
                    )
                }, required=False),
                TextColumn(
                    "name_i7",
                    "i7 Name",
                    150,
                    max_length=models.LibraryIndex.name_i7.type.length,
                ),
                TextColumn("sequence_i7", "i7 Sequence", 180),
                CategoricalDropDown("kit_i5", "i5 Kit", 200, categories=lambda: {
                    kit.identifier: f"[{kit.identifier}] {kit.name}"
                    for kit in context.ctx.session.get_all(
                        Q.index_kit.select(type_in=[
                            C.IndexType.DUAL_INDEX,
                            C.IndexType.COMBINATORIAL_DUAL_INDEX,
                        ]),
                        order_by=models.IndexKit.name.desc(),
                        limit=None,
                    )
                }, required=False),
                TextColumn(
                    "name_i5",
                    "i5 Name",
                    150,
                    max_length=models.LibraryIndex.name_i5.type.length,
                ),
                TextColumn("sequence_i5", "i5 Sequence", 180),
            ],
            allow_new_rows=True,
        )

    def validate_barcode_input(self: _BarcodeInputForm) -> pd.DataFrame:
        """Validate and populate barcode data for this form."""
        spreadsheet = self.spreadsheet
        session = context.ctx.session
        df = spreadsheet.data.copy()
        
        df.loc[df["name_i7"].notna(), "name_i7"] = df.loc[df["name_i7"].notna(), "name_i7"].astype(str).str.strip()
        df.loc[df["name_i5"].notna(), "name_i5"] = df.loc[df["name_i5"].notna(), "name_i5"].astype(str).str.strip()
        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].astype(str).str.strip()
        df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

        kit_defined = df["kit_i7"].notna() & (df["index_well"].notna() | df["name_i7"].notna())
        manual_defined = df["sequence_i7"].notna()
        kit_identifiers = list(set(df["kit_i7"].dropna().unique().tolist() + df["kit_i5"].dropna().unique().tolist()))
        kits: dict[str, tuple[models.IndexKit, pd.DataFrame]] = {}

        df["kit_i7_id"] = None
        df["kit_i5_id"] = None
        for identifier in kit_identifiers:
            kit = session.get_one(Q.index_kit.select(identifier=identifier))
            if kit.type in [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]:
                df.loc[df["kit_i5"].isna() & (df["kit_i7"] == identifier), "kit_i5"] = identifier
            if kit.type == C.IndexType.DUAL_INDEX:
                df.loc[df["name_i5"].isna() & (df["kit_i7"] == identifier), "name_i5"] = df.loc[df["name_i5"].isna() & (df["kit_i7"] == identifier), "name_i7"]
            kit_df = session.pd.get_index_kit_barcodes(kit.id, per_adapter=False, per_index=True)


            kits[identifier] = (kit, kit_df)
            df.loc[df["kit_i7"] == identifier, "kit_i7_id"] = kit.id
            df.loc[df["kit_i5"] == identifier, "kit_i5_id"] = kit.id

        for kit_identifier, (kit, kit_df) in kits.items():
            view = df[(df["kit_i7"] == kit_identifier) | (df["kit_i5"] == kit_identifier)]
            
            match kit.type:
                case C.IndexType.DUAL_INDEX:
                    mask = (kit_df["well"].isin(view["index_well"].values) | kit_df["name_i7"].isin(view["name_i7"].values) | kit_df["name_i5"].isin(view["name_i5"].values))
                case C.IndexType.COMBINATORIAL_DUAL_INDEX:
                    mask = kit_df["name_i7"].isin(view["name_i7"].values) | kit_df["name_i5"].isin(view["name_i5"].values)
                case C.IndexType.SINGLE_INDEX_I7 | C.IndexType.TENX_ATAC_INDEX:
                    mask = kit_df["well"].isin(view["index_well"].values) | kit_df["name_i7"].isin(view["name_i7"].values)
                case _:
                    raise ValueError(f"Unsupported index kit type: {kit.type.name}")

            for _, kit_row in kit_df[mask].iterrows():
                if "well" in kit_row:
                    row_mask = (df["kit_i7"] == kit_identifier) & (df["index_well"] == kit_row["well"])
                    df.loc[row_mask, "name_i7"] = kit_row["name_i7"]
                    df.loc[row_mask, "sequence_i7"] = kit_row["sequence_i7"]
                df.loc[(df["kit_i7"] == kit_identifier) & (df["name_i7"] == kit_row["name_i7"]), "sequence_i7"] = kit_row["sequence_i7"]
                if kit.type in {C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX}:
                    if "well" in kit_row:
                        row_mask = (df["kit_i5"] == kit_identifier) & (df["index_well"] == kit_row["well"])
                        df.loc[row_mask, "name_i5"] = kit_row["name_i5"]
                        df.loc[row_mask, "sequence_i5"] = kit_row["sequence_i5"]
                    df.loc[(df["kit_i5"] == kit_identifier) & (df["name_i5"] == kit_row["name_i5"]), "sequence_i5"] = kit_row["sequence_i5"]

        for idx, row in df.iterrows():
            if pd.notna(row["index_well"]) and row["index_well"] == "del":
                continue
            if pd.notna(row["kit_i7"]) and pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                continue
            if pd.notna(row["kit_i5"]) and pd.notna(row["sequence_i5"]) and pd.isna(row["index_well"]) and pd.isna(row["name_i5"]):
                spreadsheet.add_error(idx, ["index_well", "name_i5"], MissingCellValue("'index_well' or 'name_i5' must be defined when kit is defined"))
                continue
            if kit_defined.at[idx]:
                kit_i7, kit_i7_df = kits[row["kit_i7"]]
                if pd.notna(row["name_i7"]):
                    if row["name_i7"] not in kit_i7_df["name_i7"].values:
                        spreadsheet.add_error(idx, "name_i7", InvalidCellValue(f"i7 name '{row['name_i7']}' not found in kit '{row['kit_i7']}'"))
                        continue
                elif pd.notna(row["index_well"]) and ("well" not in kit_i7_df.columns or row["index_well"] not in kit_i7_df["well"].values):
                    spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i7 well '{row['index_well']}' not found in kit '{row['kit_i7']}'"))
                    continue
                if pd.notna(row["kit_i5"]):
                    kit_i5, kit_i5_df = kits[row["kit_i5"]]
                    if kit_i5.type == C.IndexType.DUAL_INDEX:
                        if pd.notna(row["name_i5"]) and row["name_i5"] not in kit_i5_df["name_i5"].values:
                            spreadsheet.add_error(idx, "name_i5", InvalidCellValue(f"i5 name '{row['name_i5']}' not found in kit '{row['kit_i5']}'"))
                            continue
                        if pd.isna(row["name_i5"]) and pd.notna(row["index_well"]) and "well" in kit_i5_df.columns and row["index_well"] not in kit_i5_df["well"].values:
                            spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i5 well '{row['index_well']}' not found in kit '{row['kit_i5']}'"))
                            continue
            elif manual_defined.at[idx]:
                if pd.notna(row["sequence_i7"]) and len(row["sequence_i7"]) > models.LibraryIndex.sequence_i7.type.length:
                    spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue("i7 sequence is too long"))
                    continue
                if pd.notna(row["sequence_i5"]) and len(row["sequence_i5"]) > models.LibraryIndex.sequence_i5.type.length:
                    spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue("i5 sequence is too long"))
                    continue
            else:
                if pd.notna(row["kit_i7"]) or pd.notna(row["index_well"]) or pd.notna(row["name_i7"]) or pd.isna(row["sequence_i7"]):
                    spreadsheet.add_error(idx, ["kit_i7", "name_i7"], MissingCellValue("missing kit/name or sequence_i7"))
                    continue
            if pd.isna(row["sequence_i7"]):
                spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7'"))

        df["index_type"] = None
        df.loc[df["sequence_i7"].notna() & df["sequence_i5"].notna(), "index_type"] = C.IndexType.DUAL_INDEX
        df.loc[df["sequence_i7"].notna() & df["sequence_i5"].isna(), "index_type"] = C.IndexType.SINGLE_INDEX_I7
        df["orientation_i7_id"] = None
        df["orientation_i5_id"] = None
        df.loc[df["kit_i7_id"].notna(), "orientation_i7_id"] = C.BarcodeOrientation.FORWARD.id
        df.loc[df["kit_i5_id"].notna() & (df["index_type"] == C.IndexType.DUAL_INDEX), "orientation_i5_id"] = C.BarcodeOrientation.FORWARD.id
        spreadsheet.set_data(df)
        df["index_well"] = df["index_well"].astype(pd.StringDtype())
        df["name_i7"] = df["name_i7"].astype(pd.StringDtype())
        df["name_i5"] = df["name_i5"].astype(pd.StringDtype())
        self.assert_valid()
        return df
