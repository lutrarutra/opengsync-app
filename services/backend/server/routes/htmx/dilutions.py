from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, query_options
from ...components.tables import Table, TableState, Col, Text, Entity, Variant, related


router = APIRouter(prefix="/dilutions", tags=["dilutions"])


PD = models.PoolDilution
_FULL_NAME = Q.search.full_name(models.User)


class DilutionTable(Table):
    key = "dil"
    model = models.PoolDilution
    noun = "dilutions"
    load = (orm.selectinload(PD.operator), orm.selectinload(PD.pool))
    default_sort = ("timestamp_utc", "desc")
    columns = [
        Col("identifier", "Identifier", sort=True, search=Text(PD.identifier), hideable=False, size=1),
        Col(
            "pool", "Pool", size=3,
            sort=related(PD.pool, models.Pool.name),
            search=Text(models.Pool.name, via=PD.pool),
            filter=Entity(models.Pool, via=PD.pool, option=query_options.pool_option, search=(models.Pool.name,)),
        ),
        Col(
            "operator", "Operator", size=2,
            sort=related(PD.operator, _FULL_NAME),
            search=Text(_FULL_NAME, via=PD.operator, weight=0.9),
        ),
        Col("timestamp_utc", "Time", sort=True, size=2),
        Col("qubit_concentration", "Qubit Concentration", sort=True, size=2),
        Col("molarity", "Molarity", size=2),
        Col("volume_ul", "Volume (uL)", sort=True, size=2),
    ]
    variants = {
        "default": Variant(
            ["identifier", "operator", "timestamp_utc", "qubit_concentration", "molarity", "volume_ul"],
            "components/tables/rows/pool-dilution.html", dom_id="pool-dilution-table",
        ),
        "experiment": Variant(
            ["identifier", "pool", "operator", "timestamp_utc", "qubit_concentration", "molarity", "volume_ul"],
            "components/tables/rows/experiment-pool-dilution.html", dom_id="pool-dilution-table",
        ),
    }


@router.get("/render-table-page")
def render_dilution_table(
    pool_id: int | None = Query(None, description="Optional pool ID to filter dilutions"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter dilutions"),
    state: TableState = Depends(DilutionTable.params),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = DilutionTable(state, route="render_dilution_table", user=current_user)

    if pool_id is not None:
        if session.get_access_level(Q.pool.permissions(pool_id=pool_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view dilutions for this pool.")
        stmt = Q.pool_dilution.select(pool_id=pool_id)
        table.use("default", pool_id=pool_id, pool=session.get_one(Q.pool.select(id=pool_id)))
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view dilutions for this experiment.")
        stmt = Q.pool_dilution.select(experiment_id=experiment_id)
        table.use("experiment", experiment_id=experiment_id, experiment=session.get_one(Q.experiment.select(id=experiment_id)))
    else:
        raise exc.BadRequestException("No pool or experiment context provided for dilution table.")

    return table.render(session, stmt)
