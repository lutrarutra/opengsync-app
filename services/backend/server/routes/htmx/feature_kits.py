from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, models

from ...core import dependencies, responses, query_options
from ...components.tables import (
    Table, TableState, Col, Text, Exact, Enum, Variant, TextColumn, StaticSpreadsheet,
)

router = APIRouter(prefix="/feature_kits", tags=["feature-kits"])

FK = models.FeatureKit


class FeatureKitTable(Table):
    key = "fkit"
    model = models.FeatureKit
    noun = "feature kits"
    columns = [
        Col("id", "ID", sort=True, search=Exact(FK.id), hideable=False, size=1),
        Col("identifier", "Identifier", sort=True, search=Text(FK.identifier, compact=True), size=2),
        Col("name", "Name", sort=True, search=Text(FK.name), hideable=False, size=3),
        Col("type", "Feature Type", sort=True, filter=Enum(C.FeatureType), size=2),
    ]
    variants = {
        "default": Variant(
            ["id", "identifier", "name", "type"], "components/tables/rows/feature_kit.html", dom_id="feature_kit-table",
        ),
    }


@router.get("/render-table-page")
def render_feature_kit_table(
    state: TableState = Depends(FeatureKitTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = FeatureKitTable(state, route="render_feature_kit_table", user=current_user)
    return table.render(session, Q.feature_kit.select())


@router.get("/query")
def query_feature_kits(
    word: str | None = Query(None, description="Search word for kit name or identifier"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    type_in: list[C.FeatureType] | None = Depends(dependencies.parse_enum_ids(C.FeatureType, "type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn. Feature kits are visible to every user."""
    return query_options.options_response(
        session, Q.feature_kit.select(type_in=type_in), columns=query_options.KIT_SEARCH_COLUMNS,
        word=word, page=page, order_column=models.FeatureKit.name, label=query_options.kit_label,
    )


@router.get("/{feature_kit_id}/export-features")
def export_feature_kit_features(
    feature_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))

    features_df = session.get_pandas(
        Q.pd.feature_kit_features(feature_kit_id),
        limit=None,
    )
    features_df["feature_type"] = features_df["type"].apply(lambda x: x.modality)

    return responses.bytes_response(
        data=features_df.to_csv(index=False).encode("utf-8"), filename=f"{feature_kit.name.replace(' ', '_').lower()}.csv",
        content_type="text/csv",
    )


@router.get("/{feature_kit_id}/render-spreadsheet")
def render_feature_kit_spreadsheet(
    feature_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))
    df = session.get_pandas(
        Q.pd.feature_kit_features(feature_kit.id),
        limit=None,
    )
    df = df.drop(columns=["type"])

    columns = []
    for col in df.columns:
        if col == "feature_id" or col == "target_id":
            width = 50
        else:
            width = 200
        columns.append(TextColumn(col, col.replace("_", " ").title(), width))

    spreadsheet = StaticSpreadsheet(df, columns=columns)
    return responses.htmx_response(content=spreadsheet.render())