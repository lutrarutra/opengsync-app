import sqlalchemy as sa
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
        TableCol(title="Feature Type", label="type", col_size=2, choices=C.FeatureType.as_selectable(), sortable=True, sort_by="type"),
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
    
    feature_kits = table.paginate(session, stmt, page=page, order_by=order_by)
    return table.make_response(feature_kits=feature_kits)


QUERY_PAGE_SIZE = 20


@router.get("/query")
def query_feature_kits(
    word: str | None = Query(None, description="Search word for kit name or identifier"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    type_in: list[C.FeatureType] | None = Depends(dependencies.parse_enum_ids(C.FeatureType, "type_in")),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    """Options for a spreadsheet QueryColumn. Feature kits are visible to every user."""
    stmt = Q.feature_kit.select(type_in=type_in)
    if word:
        # Names or identifiers containing the word first, then similar names (typos)
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        contains = sa.or_(
            models.FeatureKit.name.ilike(f"%{escaped}%", escape="\\"),
            models.FeatureKit.identifier.ilike(f"%{escaped}%", escape="\\"),
        )
        similarity = sa.func.similarity(models.FeatureKit.name, word)
        stmt = stmt.where(sa.or_(contains, utils.safe_trgm_search(models.FeatureKit.name, word))).order_by(
            sa.case((contains, 0), else_=1), similarity.desc(), models.FeatureKit.name.asc(),
        )
    else:
        stmt = stmt.order_by(models.FeatureKit.name.asc())
    kits, count = session.page(stmt, page=page, limit=QUERY_PAGE_SIZE)
    return responses.query_options_response(
        ((kit.id, f"[{kit.identifier}] {kit.name}") for kit in kits),
        has_more=(page + 1) * QUERY_PAGE_SIZE < count,
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