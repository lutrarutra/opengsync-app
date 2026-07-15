from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol


router = APIRouter(prefix="/dilutions", tags=["dilutions"])


class DilutionTable(HTMXTable):
    columns = [
        TableCol(title="Identifier", label="identifier", col_size=1, sortable=True),
        TableCol(title="Operator", label="operator_id", col_size=2),
        TableCol(title="Time", label="timestamp_utc", col_size=2),
        TableCol(title="Pool", label="pool_id", col_size=3, sortable=True),
        TableCol(title="Qubit Concentration", label="qubit_concentration", col_size=2),
        TableCol(title="Molarity", label="molarity", col_size=2),
        TableCol(title="Volume (uL)", label="volume_ul", col_size=2),
    ]


@router.get("/render-table-page")
def render_dilution_table(
    pool_id: int | None = Query(None, description="Optional pool ID to filter dilutions"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter dilutions"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.PoolDilution, default=models.PoolDilution.pool_id.desc())),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = DilutionTable(route="render_dilution_table", page=page, order_by=order_by)
    stmt = Q.pool_dilution.select()

    if pool_id is not None:
        if session.get_access_level(Q.pool.permissions(pool_id=pool_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view dilutions for this pool.")
        pool = session.get_one(Q.pool.select(id=pool_id))
        stmt = Q.pool_dilution.select(pool_id=pool_id, statement=stmt)
        table.template = "components/tables/pool-dilution.html"
        table.url_params["pool_id"] = pool_id
        table.context["pool"] = pool
    elif experiment_id is not None:
        if not current_user.is_insider:
            raise exc.NoPermissionsException("You do not have permission to view dilutions for this experiment.")
        experiment = session.get_one(Q.experiment.select(id=experiment_id))
        stmt = Q.pool_dilution.select(experiment_id=experiment_id, statement=stmt)
        table.template = "components/tables/experiment-pool-dilution.html"
        table.url_params["experiment_id"] = experiment_id
        table.context["experiment"] = experiment
    else:
        raise exc.BadRequestException("No pool or experiment context provided for dilution table.")

    dilutions, count = session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.PoolDilution.operator),
            orm.selectinload(models.PoolDilution.pool),
        ]
    )
    table.set_num_pages(count)

    return table.make_response(dilutions=dilutions)