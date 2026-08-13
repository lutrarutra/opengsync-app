from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, utils, models

from ...core import dependencies, exceptions as exc, responses
from ...components.tables import HTMXTable, TableCol, TextColumn, StaticSpreadsheet

router = APIRouter(prefix="/feature_kits", tags=["feature-kits"])

class FeatureKitTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Feature Type", label="type", col_size=2, choices=C.FeatureType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


@router.get("/render-table-page")
def render_feature_kit_table(
    id: str | None = Query(None, description="Search by kit ID"),
    name: str | None = Query(None, description="Search by kit name"),
    identifier: str | None = Query(None, description="Search by kit identifier"),
    type_in: list[C.FeatureType] | None = Depends(dependencies.parse_enum_ids(C.FeatureType, "type_in")),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.FeatureKit, default=models.FeatureKit.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = FeatureKitTable(route="render_feature_kit_table", page=page, order_by=order_by)
    table.template = "components/tables/feature_kit.html"
    stmt = Q.feature_kit.select(type_in=type_in)

    if type_in:
        table.filter_values["type"] = type_in

    if name:
        table.active_search_var = "name"
        table.active_query_value = name
        stmt = Q.feature_kit.search(name=name, statement=stmt)
    elif identifier:
        table.active_search_var = "identifier"
        table.active_query_value = identifier
        stmt = Q.feature_kit.search(identifier=identifier, statement=stmt)
    elif id:
        table.active_search_var = "id"
        table.active_query_value = str(id)
        try:
            stmt = Q.feature_kit.select(id=int("".join(filter(str.isdigit, id))), statement=stmt)
        except ValueError:
            raise exc.BadRequestException()
        
    stmt = Q.feature_kit.search(name=name, identifier=identifier, statement=stmt)
    
    feature_kits, count = session.page(stmt, page=page, order_by=order_by)
    table.set_num_pages(count)
    return table.make_response(feature_kits=feature_kits)


@router.get("/{feature_kit_id}/export-features")
def export_feature_kit_features(
    feature_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))

    features_df = session.pd.get_feature_kit_features(feature_kit_id=feature_kit_id)
    features_df["feature_type"] = features_df["type"].apply(lambda x: x.modality)

    return responses.file_response(
        features_df.to_csv(index=False), filename=f"{feature_kit.name.replace(' ', '_').lower()}.csv",
        content_type="text/csv",
    )


@router.get("/{feature_kit_id}/render-spreadsheet")
def render_feature_kit_spreadsheet(
    feature_kit_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    feature_kit = session.get_one(Q.feature_kit.select(id=feature_kit_id))
    df = session.pd.get_feature_kit_features(feature_kit_id=feature_kit.id)
    df = df.drop(columns=["type", "type_id"])

    columns = []
    for col in df.columns:
        if col == "feature_id":
            width = 50
        elif col == "read":
            width = 50
        else:
            width = 200
        columns.append(TextColumn(col, col.replace("_", " ").title().replace("Id", "ID"), width))

    spreadsheet = StaticSpreadsheet(df, columns=columns)
    return responses.htmx_response(content=spreadsheet.render())