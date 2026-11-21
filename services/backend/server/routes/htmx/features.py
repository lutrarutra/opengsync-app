from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from opengsync_db import SyncSession, queries as Q, categories as C, models

from ...core import dependencies, exceptions as exc, redis as rds
from ...components.tables import Table, TableState, Col, Text, Exact, Enum, Variant
from ...forms.models import FeatureKitForm

router = APIRouter(prefix="/features", tags=["features"])

F = models.Feature
_FEATURE_COLUMNS = ["id", "name", "identifier", "target_name", "target_id", "sequence", "pattern", "read", "type"]


class FeatureTable(Table):
    key = "feat"
    model = models.Feature
    noun = "features"
    columns = [
        Col("id", "ID", sort=True, search=Exact(F.id), hideable=False, size=1),
        Col("name", "Name", sort=True, search=Text(F.name, compact=True), hideable=False, size=3),
        Col("identifier", "Identifier", sort=True, search=Text(F.identifier, compact=True), size=2),
        Col("target_name", "Target Name", sort=True, search=Text(F.target_name), size=2),
        Col("target_id", "Target ID", sort=True, search=Text(F.target_id), size=2),
        Col("sequence", "Sequence", search=Text(F.sequence), size=2),
        Col("pattern", "Pattern", size=2),
        Col("read", "Read", size=2),
        Col("type", "Feature Type", sort=True, filter=Enum(C.FeatureType), size=2),
    ]
    variants = {
        "default": Variant(_FEATURE_COLUMNS, "components/tables/rows/feature_kit-feature.html", dom_id="feature_kit-feature-table"),
        "library": Variant(
            _FEATURE_COLUMNS, "components/tables/rows/library-feature.html", dom_id="library-feature-table",
            toolbar="components/tables/toolbars/library-feature.html",
        ),
    }


@router.get("/render-table-page")
def render_feature_table(
    feature_kit_id: int | None = Query(None, description="Optional feature kit ID to filter features"),
    library_id: int | None = Query(None, description="Filter features by library ID"),
    state: TableState = Depends(FeatureTable.params),
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_user),
    r: rds.RedisClient = Depends(dependencies.redis),
) -> Response:
    # Kit features are reference data; a library's (custom) features need access to the library.
    if library_id:
        dependencies.library_permissions(library_id=library_id, viewer_id=current_user.id, session=session, r=r)
    elif not feature_kit_id and not current_user.is_insider:
        raise exc.NoPermissionsException()

    stmt = Q.feature.select(library_id=library_id, feature_kit_id=feature_kit_id)
    table = FeatureTable(state, route="render_feature_table", user=current_user)

    if library_id:
        table.use("library", library_id=library_id)
    elif feature_kit_id:
        table.use("default", feature_kit_id=feature_kit_id)

    return table.render(session, stmt)

router.include_router(FeatureKitForm.Router())