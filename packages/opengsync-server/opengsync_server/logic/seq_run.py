import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SeqRunTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Experiment", label="experiment", col_size=2, searchable=True, sortable=True, sort_by="experiment_name"),
        TableCol(title="Status", label="status", col_size=1, choices=C.RunStatus.as_selectable(), sortable=True, sort_by="status_id"),
        TableCol(title="Cycles", label="cycles", col_size=1),
        TableCol(title="Flow Cell ID", label="flow_cell_id", searchable=True, col_size=1),
        TableCol(title="Run Folder", label="run_folder", col_size=4, searchable=True),
        TableCol(title="Started", label="started", col_size=2),
        TableCol(title="Completed", label="completed", col_size=2),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = SeqRunTable(route="seq_runs_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.SeqRun)
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.RunStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.seq_run.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (experiment := request.args.get("experiment")):
        stmt = Q.seq_run.select(search_experiment_name=experiment, statement=stmt)
        table.active_search_var = "experiment"
        table.active_query_value = experiment
    elif (run_folder := request.args.get("run_folder")):
        stmt = Q.seq_run.select(search_run_folder=run_folder, statement=stmt)
        table.active_search_var = "run_folder"
        table.active_query_value = run_folder
    elif (flow_cell_id := request.args.get("flow_cell_id")):
        stmt = Q.seq_run.select(search_flow_cell_id=flow_cell_id, statement=stmt)
        table.active_search_var = "flow_cell_id"
        table.active_query_value = flow_cell_id
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.seq_run.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.SeqRun, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    seq_runs, count = db.session.page(stmt, page=table.active_page or 0)

    context.update({
        "seq_runs": seq_runs,
        "template_name_or_list": "components/tables/seq_run.html",
        "table": table,
    })
    return context