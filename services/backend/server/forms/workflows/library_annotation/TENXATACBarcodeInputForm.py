import pandas as pd
from fastapi import Depends, Response
from loguru import logger

from opengsync_db import models, categories as C, queries as Q, SyncSession

from ....core import dependencies, exceptions as exc
from ....components import inputs
from ....components.tables import TextColumn, CategoricalDropDown, InvalidCellValue, MissingCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep


class TENXATACBarcodeInputForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-barcode-input.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("library_name", "Library Name", 250, required=True, read_only=True),
        TextColumn("index_well", "Index Well", 100, max_length=8),
        CategoricalDropDown("kit", "Kit", 200, categories={}, required=False),
        TextColumn("name", "Barcode Name", 150, max_length=models.LibraryIndex.name_i7.type.length),
        TextColumn("sequence_1", "Sequence 1", 180),
        TextColumn("sequence_2", "Sequence 2", 180),
        TextColumn("sequence_3", "Sequence 3", 180),
        TextColumn("sequence_4", "Sequence 4", 180),
    ])

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return bool(
            (workflow.tables["library_table"]["library_type_id"] == C.LibraryType.TENX_SC_ATAC.id).any()
        )

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        from ....core.context import ctx
        kit_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in ctx.session.get_all(
                Q.index_kit.select(type=C.IndexType.TENX_ATAC_INDEX).order_by(models.IndexKit.name.asc()),
                limit=None,
            )
        }
        self.spreadsheet.columns["kit"].set_categories(kit_mapping)

        barcode_table = self.library_table[
            self.library_table["library_type_id"] == C.LibraryType.TENX_SC_ATAC.id
        ].copy()

        if "sequence_i7" in barcode_table.columns:
            data = {
                "library_name": [],
                "index_well": [],
                "kit": [],
                "name": [],
                "sequence_1": [],
                "sequence_2": [],
                "sequence_3": [],
                "sequence_4": [],
            }
            for _, row in barcode_table.iterrows():
                data["library_name"].append(row["library_name"])
                data["index_well"].append(row.get("index_well"))
                data["kit"].append(row.get("kit_i7"))
                data["name"].append(row.get("name_i7"))
                seqs = (
                    row["sequence_i7"].split(";")
                    if pd.notna(row.get("sequence_i7")) else [None] * 4
                )
                for i in range(4):
                    data[f"sequence_{i + 1}"].append(seqs[i] if i < len(seqs) else None)

            barcode_table = pd.DataFrame(data)

        self.spreadsheet.set_data(barcode_table)

    def _get_barcode_table(self) -> pd.DataFrame:
        """Merge the TENX ATAC spreadsheet data with any existing barcode_table."""
        data = {
            "library_name": [],
            "index_type_id": [],
            "index_well": [],
            "kit_i7_id": [],
            "kit_i5_id": [],
            "kit_i7": [],
            "kit_i5": [],
            "orientation_i7_id": [],
            "orientation_i5_id": [],
            "name_i7": [],
            "name_i5": [],
            "sequence_i7": [],
            "sequence_i5": [],
        }

        def add_barcode(
            library_name: str, index_type_id: int, index_well: str | None,
            kit_i7_id: int | None, kit_i5_id: int | None,
            kit_i7: str | None, kit_i5: str | None,
            orientation_i7_id: int | None, orientation_i5_id: int | None,
            name_i7: str, name_i5: str | None,
            sequence_i7: str, sequence_i5: str | None,
        ):
            data["library_name"].append(library_name)
            data["index_type_id"].append(index_type_id)
            data["index_well"].append(index_well)
            data["kit_i7_id"].append(kit_i7_id)
            data["kit_i5_id"].append(kit_i5_id)
            data["orientation_i7_id"].append(orientation_i7_id)
            data["orientation_i5_id"].append(orientation_i5_id)
            data["name_i7"].append(name_i7)
            data["name_i5"].append(name_i5)
            data["kit_i7"].append(kit_i7)
            data["kit_i5"].append(kit_i5)
            data["sequence_i7"].append(sequence_i7)
            data["sequence_i5"].append(sequence_i5)

        # Copy existing non-ATAC barcodes if present
        if (barcode_table := self.workflow.tables.get("barcode_table")) is not None:
            for _, row in barcode_table.iterrows():
                add_barcode(
                    library_name=row["library_name"],
                    index_type_id=row["index_type_id"],
                    index_well=row["index_well"],
                    kit_i7_id=row["kit_i7_id"],
                    kit_i5_id=row["kit_i5_id"],
                    kit_i7=row["kit_i7"],
                    kit_i5=row["kit_i5"],
                    orientation_i7_id=row["orientation_i7_id"],
                    orientation_i5_id=row["orientation_i5_id"],
                    name_i7=row["name_i7"],
                    name_i5=row["name_i5"],
                    sequence_i7=row["sequence_i7"],
                    sequence_i5=row["sequence_i5"],
                )

        df = self.spreadsheet.data
        for _, row in df.iterrows():
            for i in range(1, 5):
                add_barcode(
                    library_name=row["library_name"],
                    index_type_id=C.IndexType.TENX_ATAC_INDEX.id,
                    index_well=row.get("index_well"),
                    kit_i7_id=row.get("kit_id") if pd.notna(row.get("kit_id")) else None,
                    kit_i7=row.get("kit"),
                    orientation_i7_id=(
                        C.BarcodeOrientation.FORWARD.id
                        if pd.notna(row.get("kit_id"))
                        else C.BarcodeOrientation.FORWARD_NOT_VALIDATED.id
                    ),
                    name_i7=row["name"],
                    sequence_i7=row[f"sequence_{i}"],
                    kit_i5=None,
                    kit_i5_id=None,
                    sequence_i5=None,
                    orientation_i5_id=None,
                    name_i5=None,
                )

        return pd.DataFrame(data)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: TENXATACBarcodeInputForm = Depends(TENXATACBarcodeInputForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["tenx_atac_barcode_table"]
            form.spreadsheet.set_data(barcode_table)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: TENXATACBarcodeInputForm = Depends(TENXATACBarcodeInputForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data

            df.loc[df["kit"].notna(), "kit"] = df.loc[df["kit"].notna(), "kit"].astype(str)
            df.loc[df["index_well"].notna(), "index_well"] = df.loc[df["index_well"].notna(), "index_well"].str.strip().str.replace(r'(?<=[A-Z])0+(?=\d)', '', regex=True)

            kit_defined = df["kit"].notna() & (df["index_well"].notna() | df["name"].notna())
            manual_defined = (
                df["sequence_1"].notna() &
                df["sequence_2"].notna() &
                df["sequence_3"].notna() &
                df["sequence_4"].notna()
            )

            kit_identifiers = df["kit"].dropna().unique().tolist()
            df["kit_id"] = None
            kits: dict[str, tuple[models.IndexKit, pd.DataFrame]] = {}
            for identifier in kit_identifiers:
                kit = session.get_one(Q.index_kit.select(identifier=identifier))

                if kit.type != C.IndexType.TENX_ATAC_INDEX:
                    logger.error(f"Index kit '{identifier}' is not of type TENX_ATAC_INDEX")
                    raise exc.OpeNGSyncServerException(f"Index kit '{identifier}' is not of type TENX_ATAC_INDEX")
                
                kit_df = session.pd.get_index_kit_barcodes(kit.id, per_adapter=False, per_index=True)
                kits[identifier] = (kit, kit_df)
                df.loc[df["kit"] == identifier, "kit_id"] = kit.id

            df.loc[df["kit_id"].notna(), "kit_id"] = df.loc[df["kit_id"].notna(), "kit_id"].astype(int)

            for kit_identifier, (kit, kit_df) in kits.items():
                view = df[df["kit"] == kit_identifier]
                mask = (
                    kit_df["well"].isin(view["index_well"].values) |
                    kit_df["name"].isin(view["name"].values)
                )

                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        (df["kit"] == kit_identifier) &
                        (df["index_well"] == kit_row["well"]), "name"
                    ] = kit_row["name"]
                    for i in range(1, 5):
                        df.loc[
                            (df["kit"] == kit_identifier) &
                            (df["name"] == kit_row["name"]), f"sequence_{i}"
                        ] = kit_row[f"sequence_{i}"]

            for idx, row in df.iterrows():
                if row["index_well"] == "del":
                    continue
                if row["library_name"] not in form.library_table["library_name"].values:
                    form.spreadsheet.add_error(idx, "library_name", InvalidCellValue("invalid 'library_name'"))

                if (not kit_defined.at[idx]) and (not manual_defined.at[idx]):
                    if pd.notna(row["kit"]):
                        if pd.isna(row["index_well"]) and pd.isna(row["name"]):
                            form.spreadsheet.add_error(idx, ["index_well", "name"], MissingCellValue("'Index Well' or 'Name' must be defined when kit is defined"))
                    elif pd.notna(row["index_well"]) or pd.notna(row["name"]):
                        form.spreadsheet.add_error(idx, "kit", MissingCellValue("missing 'Sequence 1/2/3/4' or 'Kit' + 'Name' or 'Index Well' + 'Kit'"))
                    elif pd.isna(row["sequence_1"]):
                        form.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                    elif pd.isna(row["sequence_2"]):
                        form.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                    elif pd.isna(row["sequence_3"]):
                        form.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))
                    elif pd.isna(row["sequence_4"]):
                        form.spreadsheet.add_error(idx, ["kit", "name", "sequence_1", "sequence_2", "sequence_3", "sequence_4"], MissingCellValue("missing 'Sequence 1/2/3/4' or 'Name' + 'Kit' or 'Index Well' + 'Kit'"))

            form.assert_valid()

            form.spreadsheet.set_data(df)

            form.workflow.metadata["index_col"] = "library_name"
            form.workflow.tables["tenx_atac_barcode_table"] = df
            barcode_table = form._get_barcode_table()
            form.workflow.tables["barcode_table"] = barcode_table
            return form.workflow.get_next_step(form).make_response()
        return route
