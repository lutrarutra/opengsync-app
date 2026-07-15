import json

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db, logger
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context


class DataPathTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Path", label="path", col_size=4, searchable=True, sortable=True),
        TableCol(title="Type", label="type", col_size=2, choices=C.DataPathType.as_selectable(), sortable=True, sort_by="type_id"),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = DataPathTable(route="render_data_path_table", page=request.args.get("page", 0, type=int))
    stmt = sa.select(models.DataPath)

    if (path := request.args.get("path")):
        stmt = Q.data_path.select(path=path, statement=stmt)
        table.active_search_var = "path"
        table.active_query_value = path
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            stmt = Q.data_path.select(id=int("".join(filter(str.isdigit, id_))), statement=stmt)
        except ValueError:
            pass
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.DataPath, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [C.DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    context = parse_context(current_user, request) | kwargs

    if (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-data_path.html"        
        stmt = Q.data_path.select(experiment_id=experiment.id, type_in=type_in, statement=stmt)
        table.url_params["experiment_id"] = experiment.id
    elif (library := context.get("library")) is not None:
        template = "components/tables/library-data_path.html"        
        stmt = Q.data_path.select(library_id=library.id, type_in=type_in, statement=stmt)
        table.url_params["library_id"] = library.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-data_path.html"        
        stmt = Q.data_path.select(seq_request_id=seq_request.id, type_in=type_in, statement=stmt)
        table.url_params["seq_request_id"] = seq_request.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-data_path.html"        
        stmt = Q.data_path.select(project_id=project.id, type_in=type_in, statement=stmt)
        table.url_params["project_id"] = project.id
    else:
        raise exceptions.BadRequestException("Experiment context is required to view sequencers.")

    data_paths, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)

    context.update({
        "data_paths": data_paths,
        "template_name_or_list": template,
        "table": table,
    })
    return context