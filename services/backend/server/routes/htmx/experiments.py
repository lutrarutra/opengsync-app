from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C, utils, units

from ...core import dependencies, responses, exceptions as exc
from ...components.tables import HTMXTable, TableCol
from ...components.tables import StaticSpreadsheet, TextColumn
from ...forms.models import ExperimentForm

router = APIRouter(prefix="/experiments", tags=["experiments"])
router.include_router(ExperimentForm.Router())

class ExperimentTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=2, searchable=True, sortable=True),
        TableCol(title="Workflow", label="workflow", col_size=2, choices=C.ExperimentWorkFlow.as_selectable(), sortable=True, sort_by="workflow_id"),
        TableCol(title="Status", label="status", col_size=2, choices=C.ExperimentStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="# Seq Requests", label="num_seq_requests", col_size=1, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=3, choices=C.LibraryType.as_selectable()),
        TableCol(title="Operator", label="operator", col_size=2, searchable=True),
        TableCol(title="Created", label="timestamp_created", col_size=2, sortable=True, sort_by="timestamp_created_utc"),
        TableCol(title="Completed", label="timestamp_completed", col_size=2, sortable=True, sort_by="timestamp_finished_utc"),
    ]


@router.get("/render-table-page", dependencies=[Depends(dependencies.require_insider)])
def render_experiment_table(
    project_id: int | None = Query(None, description="Optional project ID to filter experiments"),
    status_in: list[C.ExperimentStatus] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentStatus, query_param="status_in")),
    workflow_in: list[C.ExperimentWorkFlow] | None = Depends(dependencies.parse_enum_ids(enum_type=C.ExperimentWorkFlow, query_param="workflow_in")),
    browse: str | None = Query(None, description="Optional browse context for experiment selection component"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.Experiment, default=models.Experiment.id.desc())),
    session: SyncSession = Depends(dependencies.db_session),
):
    table = ExperimentTable(route="render_experiment_table", page=page, order_by=order_by)

    if status_in:
        table.filter_values["status"] = status_in
    if workflow_in:
        table.filter_values["workflow"] = workflow_in

    stmt = Q.experiment.select(
        project_id=project_id,
        status_in=status_in,
        workflow_in=workflow_in,
    )

    if project_id is not None:
        table.template = "components/tables/project-experiment.html"
        table.url_params["project_id"] = project_id
    elif browse is not None:
        table.template = "components/tables/browse-experiment.html"
        table.context["browse_context"] = browse
        table.url_params["browse"] = browse
    else:
        table.template = "components/tables/experiment.html"

    experiments, count = session.page(
        stmt, page=page, order_by=order_by,
        options=[
            orm.selectinload(models.Experiment.operator),
            orm.selectinload(models.Experiment.libraries),
            orm.selectinload(models.Experiment.sequencer),
        ]
    )
    table.set_num_pages(count)

    return table.make_response(experiments=experiments)

@router.get("/{experiment_id}/delete")
def delete_experiment(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider)
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    if not experiment.is_deleteable() and not current_user.is_admin:
        raise exc.NoPermissionsException()

    session.delete(experiment)
    return responses.htmx_response(
        redirect=responses.url_for("experiments_page"),
        flash=responses.flash(f"Experiment '{experiment.name}' deleted.", "success")
    )

@router.get("/{experiment_id}/checklist")
def experiment_checklist(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    current_user: models.User = Depends(dependencies.require_insider)
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    checklist = experiment.get_checklist()
    can_be_edited = (experiment.status < C.ExperimentStatus.SEQUENCING) or current_user.is_admin
    
    return responses.htmx_response(
        template="components/checklists/experiment.html",
        experiment=experiment,
        can_be_edited=can_be_edited,
        **checklist,
    )

@router.get("/{experiment_id}/overview", dependencies=[Depends(dependencies.require_insider)])
def experiment_overview(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    if not session.exists(Q.experiment.select(id=experiment_id)):
        raise exc.ItemNotFoundException(f"Experiment with ID {experiment_id} not found.")
    
    LINK_WIDTH_UNIT = 1
    df = session.pd.get_experiment_libraries(experiment_id=experiment_id, include_indices=False, include_seq_request=True, collapse_lanes=False)

    if df.empty:
        return responses.htmx_response("components/plots/experiment_overview.html", links=[], nodes=[])
    
    nodes = []
    links = []

    node_idx = 0

    libraries = {}
    pools = {}
    lanes = {}
    lane_widths = {}
    for lane in df["lane"].unique():
        lane_node = {
            "node": node_idx,
            "name": f"Lane {lane}"
        }
        node_idx += 1
        nodes.append(lane_node)
        lanes[lane] = lane_node
        lane_widths[lane] = 0

    for (_, request_name), _df in df.groupby(["seq_request_id", "request_name"]):
        request_node = {
            "node": node_idx,
            "name": request_name
        }
        nodes.append(request_node)
        node_idx += 1
        for (pool_id, pool_name, lane), __df in _df.groupby(["pool_id", "pool_name", "lane"]):
            if pool_id not in pools.keys():
                pool_node = {
                    "node": node_idx,
                    "name": pool_name
                }
                node_idx += 1
                nodes.append(pool_node)
                pools[pool_id] = pool_node
            else:
                pool_node = pools[pool_id]

            width = __df.shape[0] / len(df[df["pool_id"] == pool_id]["lane"].unique())
            links.append({
                "source": pool_node["node"],
                "target": lanes[lane]["node"],
                "value": LINK_WIDTH_UNIT * width
            })
            lane_widths[lane] += width

            for i, row in __df.iterrows():
                if row["library_id"] not in libraries.keys():
                    library_node = {
                        "node": node_idx,
                        "name": row["library_type"].name
                    }
                    node_idx += 1
                    nodes.append(library_node)
                    libraries[row["library_id"]] = library_node
                    links.append({
                        "source": library_node["node"],
                        "target": pool_node["node"],
                        "value": LINK_WIDTH_UNIT
                    })
                    links.append({
                        "source": request_node["node"],
                        "target": library_node["node"],
                        "value": LINK_WIDTH_UNIT
                    })
                else:
                    library_node = libraries[row["library_id"]]
    
    return responses.htmx_response(
        "components/plots/experiment_overview.html",
        links=links, nodes=nodes
    )

@router.get("/{experiment_id}/stats", dependencies=[Depends(dependencies.require_insider)])
def experiment_stats(
    experiment_id: int,
    session: SyncSession = Depends(dependencies.db_session),
):
    experiment = session.get_one(Q.experiment.select(id=experiment_id))
    
    library_stats_df = session.pd.get_experiment_stats(experiment.id, per_lane=False).drop(columns=["library_id"])
    library_stats_df.loc[library_stats_df["library_name"].isna(), "library_name"] = "Undetermined"
    library_stats_df = library_stats_df.drop(columns=["pool_id", "pool_name"])
    library_stats_df = library_stats_df.sort_values(by="num_reads", ascending=False)
    library_stats_df = library_stats_df.rename(columns={
        "num_reads": "Sequenced Reads",
    })
    library_stats_df["% of the Sequenced"] = (library_stats_df["Sequenced Reads"] / library_stats_df["Sequenced Reads"].sum()).apply(lambda x: f"{x:.1%}")

    columns = []
    for col in library_stats_df.columns:
        columns.append(TextColumn(col, col.replace("_", " ").title(), {"library_name": 250}.get(col, 150), max_length=1000))

    library_stats = StaticSpreadsheet(df=library_stats_df, columns=columns, id=f"experiment-{experiment_id}-stats")

    pool_stats_df = session.pd.get_pool_num_reads_stats(experiment.id)
    pool_stats_df.loc[pool_stats_df["pool_id"].isna(), "pool_name"] = "Undetermined"
    pool_stats_df = pool_stats_df[["pool_name", "num_reads", "num_planned_reads", "sequenced_vs_planned", "num_reads_requested"]]
    pool_stats_df = pool_stats_df.sort_values(by="num_reads", ascending=False)
    pool_stats_df = pool_stats_df.rename(columns={
        "num_reads": "Sequenced Reads",
        "num_planned_reads": "Planned Reads",
        "sequenced_vs_planned": "Sequenced vs Planned (%)",
        "num_reads_requested": "Requested Reads"
    })
    pool_stats_df["% of the Sequenced"] = (pool_stats_df["Sequenced Reads"] / pool_stats_df["Sequenced Reads"].sum()).apply(lambda x: f"{x:.1%}")

    columns = []
    for col in pool_stats_df.columns:
        columns.append(TextColumn(col, col.replace("_", " ").title(), {"pool_name": 250}.get(col, 250), max_length=1000))
    pool_stats = StaticSpreadsheet(df=pool_stats_df, columns=columns, id=f"experiment-{experiment_id}-pool-stats")
    
    return responses.htmx_response(
        "components/experiment-stats.html",
        experiment=experiment, library_stats=library_stats, pool_stats=pool_stats,
        num_total_reads=units.Quantity(experiment.get_demultiplexed_reads(), units.read),
        num_library_reads=units.Quantity(experiment.get_demultiplexed_reads(include_undetermined=False), units.read)
    )