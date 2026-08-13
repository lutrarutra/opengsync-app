from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, utils, models

from ...core import dependencies
from ...components.tables import HTMXTable, TableCol

router = APIRouter(prefix="/features", tags=["features"])

class FeatureTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Identifier", label="identifier", col_size=2, searchable=True, sortable=True),
        TableCol(title="Target Name", label="target_name", col_size=2),
        TableCol(title="Target ID", label="target_id", col_size=2),
        TableCol(title="Sequence", label="sequence", col_size=2),
        TableCol(title="Pattern", label="pattern", col_size=2),
        TableCol(title="Read", label="read", col_size=2),
        TableCol(title="Feature Type", label="type", col_size=2, choices=C.FeatureType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


@router.get("/render-table-page")
def render_feature_table(
    feature_kit_id: int,
    library_id: int | None = Query(None, description="Filter features by library ID"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    type_in: list[C.FeatureType] | None = Depends(dependencies.parse_enum_ids(C.FeatureType, "type_in")),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Feature, default=models.Feature.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
) -> Response:
    table = FeatureTable(route="render_feature_table", page=page, order_by=order_by)
    stmt = Q.feature.select(library_id=library_id, feature_kit_id=feature_kit_id, type_in=type_in)

    if type_in:
        table.filter_values["type"] = type_in

    if library_id:
        table.template = "components/tables/library-feature.html"
        table.url_params["library_id"] = library_id
    elif feature_kit_id:
        table.template = "components/tables/feature_kit-feature.html"
        table.url_params["feature_kit_id"] = feature_kit_id
    else:
        table.template = "components/tables/feature.html"

    features, count = session.page(stmt, page=page, order_by=order_by)
    table.set_num_pages(count)
    return table.make_response(features=features)