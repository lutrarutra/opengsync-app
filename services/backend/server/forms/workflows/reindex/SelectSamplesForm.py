import os

from fastapi import Depends, Response
from loguru import logger
from sqlalchemy import orm
import pandas as pd

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ....core import dependencies, config
from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .ReindexWorkflow import ReindexWorkflowStep, ReindexWorkflow


def _append_barcode_row(
    data: dict[str, list],
    library: models.Library,
    index: models.LibraryIndex | None = None,
) -> None:
    data["library_id"].append(library.id)
    data["library_name"].append(library.name)
    data["library_type"].append(library.type)
    data["index_well"].append(None)
    if index is None:
        data["kit_i7"].append(None)
        data["kit_i5"].append(None)
        data["name_i7"].append(None)
        data["name_i5"].append(None)
        data["sequence_i7"].append(None)
        data["sequence_i5"].append(None)
        return
    data["kit_i7"].append(index.index_kit_i7.identifier if index.index_kit_i7 else None)
    data["kit_i5"].append(index.index_kit_i5.identifier if index.index_kit_i5 else None)
    data["name_i7"].append(index.name_i7)
    data["name_i5"].append(index.name_i5)
    data["sequence_i7"].append(index.sequence_i7)
    data["sequence_i5"].append(index.sequence_i5)


PREP_TABLE_BARCODE_COLUMNS = ["index_well", "kit_i7", "kit_i5", "name_i7", "name_i5"]


def _clean_kit_identifier(identifier) -> str | None:
    """Same as legacy ``CommonBarcodeInputForm.kit_identifier_clean_up``."""
    if pd.isna(identifier):
        return None
    identifier = str(identifier).strip().removeprefix("#")
    if not identifier:
        return None
    try:
        float(identifier)
        identifier = identifier.replace(",", ".")  # regional Excel may use a comma as decimal separator
    except ValueError:
        pass
    return identifier


def _clean_text(value) -> str | None:
    if pd.isna(value):
        return None
    return str(value).strip() or None


def _split_prep_cell(value, clean) -> list[str | None]:
    """Prep table cells hold one value per index, separated by ';'."""
    if pd.isna(value):
        return []
    return [clean(part) for part in str(value).split(";")]


def _prep_table_index_rows(prep_row: pd.Series) -> list[dict[str, str | None]]:
    """Unaggregate one prep-table row into one row per index.

    A column with a single value (e.g. one kit for all indices) applies to every index.
    """
    values = {
        col: _split_prep_cell(prep_row.get(col), _clean_kit_identifier if col.startswith("kit_") else _clean_text)
        for col in PREP_TABLE_BARCODE_COLUMNS
    }
    num_indices = max((len(v) for v in values.values()), default=0)
    rows = []
    for i in range(num_indices):
        row = {}
        for col, parts in values.items():
            if len(parts) == 1:
                row[col] = parts[0]
            else:
                row[col] = parts[i] if i < len(parts) else None
        if any(v is not None for v in row.values()):
            rows.append(row)
    return rows


def _fill_from_prep_table(df: pd.DataFrame, lab_prep: models.LabPrep) -> pd.DataFrame:
    """Fill well, kit and name of libraries without a stored barcode from the lab prep's
    uploaded prep table, as legacy ``CommonBarcodeInputForm`` did for reindex, one row per index."""
    if lab_prep.prep_file is None:
        return df
    path = os.path.join(config.settings.app_config.media_folder, lab_prep.prep_file.path)
    if not os.path.exists(path):
        logger.warning(f"Lab prep file not found at {path}")
        return df

    prep_table = pd.read_excel(path, "prep_table")
    prep_table = prep_table.dropna(subset=["library_id", "library_name"])
    prep_table["library_id"] = prep_table["library_id"].astype(pd.Int64Dtype())
    prep_rows = prep_table.drop_duplicates(subset="library_id", keep="first").set_index("library_id")

    unindexed = df["sequence_i7"].isna() & (df["library_type"] != C.LibraryType.TENX_SC_ATAC)
    rows: list[dict] = []
    for idx, row in df.iterrows():
        library_id = row["library_id"]
        if not unindexed[idx] or library_id not in prep_rows.index:
            rows.append(row.to_dict())
            continue
        index_rows = _prep_table_index_rows(prep_rows.loc[library_id])
        if not index_rows:
            rows.append(row.to_dict())
            continue
        for index_row in index_rows:
            rows.append({**row.to_dict(), **{col: row[col] if pd.notna(row[col]) else index_row[col] for col in PREP_TABLE_BARCODE_COLUMNS}})
    return pd.DataFrame(rows, columns=df.columns)


class SelectSamplesForm(ReindexWorkflowStep):
    template_path = "workflows/reindex/select-samples.html"
    selected_library_ids = inputs.tables.LibrarySelectTableField(
        "Libraries", "reindex", select_all=True, required=True,
    )

    def __init__(self, workflow: ReindexWorkflow) -> None:
        super().__init__(workflow=workflow)
        if self.workflow.seq_request_id is not None:
            self.selected_library_ids.query_params["seq_request_id"] = self.workflow.seq_request_id
        if self.workflow.lab_prep_id is not None:
            self.selected_library_ids.query_params["lab_prep_id"] = self.workflow.lab_prep_id
        if self.workflow.pool_id is not None:
            self.selected_library_ids.query_params["pool_id"] = self.workflow.pool_id

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Init()),
        ) -> Response:
            barcode_table = form.workflow.tables["library_table"]
            form.selected_library_ids.data = barcode_table["library_id"].unique().tolist()
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(SelectSamplesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            barcode_table_data: dict[str, list] = {
                "library_id": [],
                "library_name": [],
                "index_well": [],
                "kit_i7": [],
                "kit_i5": [],
                "name_i7": [],
                "name_i5": [],
                "sequence_i7": [],
                "sequence_i5": [],
                "library_type": [],
            }

            library_table_data: dict[str, list] = {
                "library_id": [],
                "library_name": [],
                "library_type": [],
            }

            for library in form.selected_library_ids.get_selected_libraries(
                session,
                seq_request_id=form.workflow.seq_request_id,
                lab_prep_id=form.workflow.lab_prep_id,
                pool_id=form.workflow.pool_id,
                options=[
                    orm.selectinload(models.Library.indices).selectinload(models.LibraryIndex.index_kit_i7),
                    orm.selectinload(models.Library.indices).selectinload(models.LibraryIndex.index_kit_i5),
                ],
            ):
                library_table_data["library_id"].append(library.id)
                library_table_data["library_name"].append(library.name)
                library_table_data["library_type"].append(library.type)
                if library.indices:
                    for index in library.indices:
                        _append_barcode_row(barcode_table_data, library, index)
                else:
                    _append_barcode_row(barcode_table_data, library)

            df = pd.DataFrame(barcode_table_data).astype({col: object for col in PREP_TABLE_BARCODE_COLUMNS})
            if form.workflow.lab_prep_id is not None:
                lab_prep = session.get_one(
                    Q.lab_prep.select(id=form.workflow.lab_prep_id),
                    options=[orm.selectinload(models.LabPrep.prep_file)],
                )
                df = _fill_from_prep_table(df, lab_prep)
            form.workflow.tables["library_table"] = pd.DataFrame(library_table_data)
            form.workflow.tables["barcode_table"] = df[df["library_type"] != C.LibraryType.TENX_SC_ATAC].copy()
            form.workflow.tables["tenx_atac_barcode_table"] = df[df["library_type"] == C.LibraryType.TENX_SC_ATAC].copy()
            return form.workflow.get_next_step(form).make_response()
        return route