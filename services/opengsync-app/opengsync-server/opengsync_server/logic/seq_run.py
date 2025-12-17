import json

from flask import Request

from opengsync_db import models, categories as cats

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class SeqRunTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, search_type="number", sortable=True),
        TableCol(title="Experiment", label="experiment", col_size=2, search_type="text", sortable=True, sort_by="experiment_name"),
        TableCol(title="Status", label="status", col_size=1, choices=cats.RunStatus.as_list(), sortable=True, sort_by="status_id"),
        TableCol(title="Cycles", label="cycles", col_size=1),
        TableCol(title="Flow Cell ID", label="flow_cell_id", search_type="text", col_size=1),
        TableCol(title="Run Folder", label="run_folder", col_size=4, search_type="text"),
        TableCol(title="Started", label="started", col_size=2),
        TableCol(title="Completed", label="completed", col_size=2),
    ]

def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    table = SeqRunTable(route="seq_runs_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [cats.RunStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (experiment := request.args.get("experiment")):
        fnc_context["experiment"] = experiment
        table.active_search_var = "experiment"
        table.active_query_value = experiment
    elif (run_folder := request.args.get("run_folder")):
        fnc_context["run_folder"] = run_folder
        table.active_search_var = "run_folder"
        table.active_query_value = run_folder
    elif (flow_cell_id := request.args.get("flow_cell_id")):
        fnc_context["flow_cell_id"] = flow_cell_id
        table.active_search_var = "flow_cell_id"
        table.active_query_value = flow_cell_id
    elif (id_ := request.args.get("id")):
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.SeqRun.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    seq_runs, table.num_pages = db.seq_runs.find(page=table.active_page, **fnc_context)

    context.update({
        "seq_runs": seq_runs,
        "template_name_or_list": "components/tables/seq_run.html",
        "table": table,
    })
    return context