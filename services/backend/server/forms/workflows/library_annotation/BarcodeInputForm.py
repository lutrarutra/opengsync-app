import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown, MissingCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


class BarcodeInputForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
        TextColumn("index_well", "Index Well", 100, max_length=8),
        CategoricalDropDown("kit_i7", "i7 Kit", 200, categories={}, required=False),
        TextColumn("name_i7", "i7 Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_i7", "i7 Sequence", 180),
        CategoricalDropDown("kit_i5", "i5 Kit", 200, categories={}, required=False),
        TextColumn("name_i5", "i5 Name", 150, max_length=models.LibraryIndex.name_i5.type.length),
        TextColumn("sequence_i5", "i5 Sequence", 180),
    ])

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return bool((workflow.tables["library_table"]["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id).any())

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        from ....core.context import ctx
        i7_kit_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in ctx.session.get_all(
                Q.index_kit.select(type_in=[
                    C.IndexType.DUAL_INDEX,
                    C.IndexType.SINGLE_INDEX_I7,
                    C.IndexType.COMBINATORIAL_DUAL_INDEX,
                ]),
                order_by=models.IndexKit.name.desc(),
                limit=None,
            )
        }
        i5_kit_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in ctx.session.get_all(
                Q.index_kit.select(type_in=[
                    C.IndexType.DUAL_INDEX,
                    C.IndexType.COMBINATORIAL_DUAL_INDEX,
                ]),
                order_by=models.IndexKit.name.desc(),
                limit=None,
            )
        }
        self.spreadsheet.columns["kit_i7"].set_categories(i7_kit_mapping)
        self.spreadsheet.columns["kit_i5"].set_categories(i5_kit_mapping)

        barcode_table = self.library_table[
            self.library_table["library_type_id"] != C.LibraryType.TENX_SC_ATAC.id
        ].copy()
        self.spreadsheet.set_data(barcode_table)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["barcode_table"]
            barcode_table = barcode_table[barcode_table["index_type_id"] != C.IndexType.TENX_ATAC_INDEX.id].copy()
            form.spreadsheet.set_data(barcode_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: BarcodeInputForm = Depends(BarcodeInputForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data

            df.loc[df["name_i7"].notna(), "name_i7"] = df.loc[df["name_i7"].notna(), "name_i7"].astype(str).str.strip()
            df.loc[df["name_i5"].notna(), "name_i5"] = df.loc[df["name_i5"].notna(), "name_i5"].astype(str).str.strip()
            df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].astype(str).str.strip()

            df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

            kit_defined = df["kit_i7"].notna() & (df["index_well"].notna() | df["name_i7"].notna())
            manual_defined = df["sequence_i7"].notna()

            # self.df.loc[self.df["kit_i5"].isna(), "kit_i5"] = self.df.loc[self.df["kit_i5"].isna(), "kit_i7"]
            # self.df.loc[self.df["name_i5"].isna(), "name_i5"] = self.df.loc[self.df["name_i5"].isna(), "name_i7"]

            kit_identifiers = list(set(df["kit_i7"].dropna().unique().tolist() + df["kit_i5"].dropna().unique().tolist()))
            kits: dict[str, tuple[models.IndexKit, pd.DataFrame]] = dict()

            df["kit_i7_id"] = None
            df["kit_i5_id"] = None

            for identifier in kit_identifiers:
                kit = session.get_one(Q.index_kit.select(identifier=identifier))
                
                if kit.type in [C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX]:
                    idx = (df["kit_i5"].isna() & (df["kit_i7"] == identifier))
                    df.loc[idx, "kit_i5"] = df.loc[idx, "kit_i7"]
                    
                if kit.type == C.IndexType.DUAL_INDEX:
                    idx = (df["name_i5"].isna() & (df["kit_i7"] == identifier))
                    df.loc[idx, "name_i5"] = df.loc[idx, "name_i7"]
                
                _df = session.pd.get_index_kit_barcodes(kit.id, per_adapter=False, per_index=True)
                kits[identifier] = (kit, _df)
                df.loc[df["kit_i7"] == identifier, "kit_i7_id"] = kit.id
                df.loc[df["kit_i5"] == identifier, "kit_i5_id"] = kit.id

            for kit_identifier, (kit, kit_df) in kits.items():
                view = df[(df["kit_i7"] == kit_identifier) | (df["kit_i5"] == kit_identifier)]
                
                match kit.type:
                    case C.IndexType.DUAL_INDEX:
                        mask = (
                            (kit_df["well"].isin(view["index_well"].values)) |
                            (kit_df["name_i7"].isin(view["name_i7"].values)) |
                            (kit_df["name_i5"].isin(view["name_i5"].values))
                        )
                    case C.IndexType.COMBINATORIAL_DUAL_INDEX:
                        mask = (
                            (kit_df["name_i7"].isin(view["name_i7"].values)) |
                            (kit_df["name_i5"].isin(view["name_i5"].values))
                        )
                    case C.IndexType.SINGLE_INDEX_I7:
                        mask = (
                            (kit_df["well"].isin(view["index_well"].values)) |
                            (kit_df["name_i7"].isin(view["name_i7"].values))
                        )
                    case _:
                        raise exc.OpeNGSyncServerException(f"Only Dual and Single index kits are supported, but kit '{kit.identifier}' is of type '{kit.type.name}'")
                
                for _, kit_row in kit_df[mask].iterrows():
                    if "well" in kit_row:
                        df.loc[
                            (df["kit_i7"] == kit_identifier) &
                            (df["index_well"] == kit_row["well"]), "name_i7"
                        ] = kit_row["name_i7"]

                        df.loc[
                            (df["kit_i7"] == kit_identifier) &
                            (df["index_well"] == kit_row["well"]), "sequence_i7"
                        ] = kit_row["sequence_i7"]

                    df.loc[
                        (df["kit_i7"] == kit_identifier) &
                        (df["name_i7"] == kit_row["name_i7"]), "sequence_i7"
                    ] = kit_row["sequence_i7"]

                    if kit.type in {C.IndexType.DUAL_INDEX, C.IndexType.COMBINATORIAL_DUAL_INDEX}:
                        if "well" in kit_row:
                            df.loc[
                                (df["kit_i5"] == kit_identifier) &
                                (df["index_well"] == kit_row["well"]), "name_i5"
                            ] = kit_row["name_i5"]

                            df.loc[
                                (df["kit_i5"] == kit_identifier) &
                                (df["index_well"] == kit_row["well"]), "sequence_i5"
                            ] = kit_row["sequence_i5"]

                        df.loc[
                            (df["kit_i5"] == kit_identifier) &
                            (df["name_i5"] == kit_row["name_i5"]), "sequence_i5"
                        ] = kit_row["sequence_i5"]

            for idx, row in df.iterrows():
                if pd.notna(row["index_well"]) and row["index_well"] == "del":
                    continue
                    
                if pd.notna(row["kit_i7"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                        form.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                        continue
                
                if pd.notna(row["kit_i5"]) and pd.notna(row["sequence_i5"]):
                    if pd.isna(row["index_well"]) and pd.isna(row["name_i5"]):
                        form.spreadsheet.add_error(idx, ["index_well", "name_i5"], MissingCellValue("'index_well' or 'name_i5' must be defined when kit is defined"))
                        continue
                
                if row["library_name"] not in form.library_table["library_name"].values:
                    form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

                if kit_defined.at[idx]:
                    kit_i7_label = row["kit_i7"]
                    kit_i7, kit_i7_df = kits[row["kit_i7"]]
                    
                    if pd.notna(row["name_i7"]):
                        if row["name_i7"] not in kit_i7_df["name_i7"].values:
                            form.spreadsheet.add_error(idx, "name_i7", InvalidCellValue(f"i7 name '{row['name_i7']}' not found in kit '{kit_i7_label}'"))
                            continue
                    elif pd.notna(row["index_well"]):
                        if "well" not in kit_i7_df.columns or row["index_well"] not in kit_i7_df["well"].values:
                            form.spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i7 well '{row['index_well']}' not found in kit '{kit_i7_label}'"))
                            continue
                    
                    if pd.notna(row["kit_i5"]):
                        kit_i5, kit_i5_df = kits[row["kit_i5"]]
                        if kit_i5.type == C.IndexType.DUAL_INDEX:
                            kit_i5_label = row["kit_i5"]
                            if pd.notna(row["name_i5"]):
                                if row["name_i5"] not in kit_i5_df["name_i5"].values:
                                    form.spreadsheet.add_error(idx, "name_i5", InvalidCellValue(f"i5 name '{row['name_i5']}' not found in kit '{kit_i5_label}'"))
                                    continue
                            elif pd.notna(row["index_well"]) and "well" in kit_i5_df.columns:
                                if row["index_well"] not in kit_i5_df["well"].values:
                                    form.spreadsheet.add_error(idx, "index_well", InvalidCellValue(f"i5 well '{row['index_well']}' not found in kit '{kit_i5_label}'"))
                                    continue

                elif manual_defined.at[idx]:
                    if pd.notna(row["sequence_i7"]) and len(row["sequence_i7"]) > models.LibraryIndex.sequence_i7.type.length:
                        form.spreadsheet.add_error(idx, "sequence_i7", InvalidCellValue(f"i7 sequence too long ({len(row['sequence_i7'])} > {models.LibraryIndex.sequence_i7.type.length})"))
                        continue
                    
                    if pd.notna(row["sequence_i5"]) and len(row["sequence_i5"]) > models.LibraryIndex.sequence_i5.type.length:
                        form.spreadsheet.add_error(idx, "sequence_i5", InvalidCellValue(f"i5 sequence too long ({len(row['sequence_i5'])} > {models.LibraryIndex.sequence_i5.type.length})"))
                        continue

                else:
                    if pd.notna(row["kit_i7"]):
                        if pd.isna(row["index_well"]) and pd.isna(row["name_i7"]):
                            form.spreadsheet.add_error(idx, ["index_well", "name_i7"], MissingCellValue("'index_well' or 'name_i7' must be defined when kit is defined"))
                            continue
                    elif pd.notna(row["index_well"]) or pd.notna(row["name_i7"]):
                        form.spreadsheet.add_error(idx, ["kit_i7", "name_i7"], MissingCellValue("missing 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well' or 'sequence_i7'"))
                        continue
                    elif pd.isna(row["sequence_i7"]):
                        form.spreadsheet.add_error(idx, ["kit_i7", "name_i7"], MissingCellValue("missing 'kit_i7' + 'name_i7' or 'kit_i7' + 'index_well' or 'sequence_i7'"))
                        continue
                    
                if pd.isna(row["sequence_i7"]):
                    form.spreadsheet.add_error(idx, "sequence_i7", MissingCellValue("missing 'sequence_i7'"))
                    continue

            form.assert_valid()

            df["index_type_id"] = None
            df.loc[(df["sequence_i7"].notna() & df["sequence_i5"].notna()), "index_type_id"] = C.IndexType.DUAL_INDEX.id
            df.loc[(df["sequence_i7"].notna() & df["sequence_i5"].isna()), "index_type_id"] = C.IndexType.SINGLE_INDEX_I7.id
            
            df["orientation_i7_id"] = None
            df["orientation_i5_id"] = None
            df.loc[(df["kit_i7_id"].notna()), "orientation_i7_id"] = C.BarcodeOrientation.FORWARD.id
            df.loc[df["kit_i5_id"].notna() & (df["index_type_id"] == C.IndexType.DUAL_INDEX.id), "orientation_i5_id"] = C.BarcodeOrientation.FORWARD.id
            
            form.spreadsheet.set_data(df)

            df["index_well"] = df["index_well"].astype(pd.StringDtype())
            df["name_i7"] = df["name_i7"].astype(pd.StringDtype())
            df["name_i5"] = df["name_i5"].astype(pd.StringDtype())
            form.workflow.tables["barcode_table"] = df
            return form.workflow.get_next_step(form).make_response()
        return route
