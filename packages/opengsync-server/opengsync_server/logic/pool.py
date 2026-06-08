import json
from typing import cast

from flask import Request
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ..import db
from .HTMXTable import HTMXTable
from .TableCol import TableCol
from ..core import exceptions
from .context import parse_context

class PoolTable(HTMXTable):
    columns = [
        TableCol(title="ID", label="id", col_size=1, searchable=True, sortable=True),
        TableCol(title="Name", label="name", col_size=3, searchable=True, sortable=True),
        TableCol(title="Library Types", label="library_types", col_size=2, choices=C.LibraryType.as_selectable()),
        TableCol(title="Status", label="status", col_size=2, sortable=True, sort_by="status_id", choices=C.PoolStatus.as_selectable()),
        TableCol(title="Type", label="type", col_size=1, sortable=True, sort_by="type_id", choices=C.PoolType.as_selectable()),
        TableCol(title="Owner", label="owner", col_size=2, searchable=True),
        TableCol(title="# Libraries", label="num_libraries", col_size=1, sortable=True),
    ]


def get_table_context(current_user: models.User, request: Request, **kwargs) -> dict:
    table = PoolTable(route="pools_htmx.get", page=request.args.get("page", 0, type=int))
    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Pool)
    
    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.PoolStatus.get(int(status)) for status in status_in]
            if status_in:
                # fnc_context["status_in"] = status_in
                stmt = Q.pool.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.PoolType.get(int(type)) for type in type_in]
            if type_in:
                stmt = Q.pool.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")):
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [C.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                stmt = Q.pool.select(library_types_in=library_types_in, statement=stmt)
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")):
        stmt = Q.pool.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            id_ = int("".join(filter(str.isdigit, id_)))
            stmt = Q.pool.select(id=id_, statement=stmt)
        except ValueError:
            pass
    elif (owner := request.args.get("owner")):
        stmt = Q.pool.select(search_owner_name=owner, statement=stmt)
        table.active_search_var = "owner"
        table.active_query_value = owner

    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        stmt = stmt.order_by(getattr(getattr(models.Pool, sort_by), "desc" if descending else "asc")())
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-pool.html"        
        stmt = Q.pool.select(seq_request_id=seq_request.id, statement=stmt)
        table.url_params["seq_request_id"] = seq_request.id
    elif (experiment := context.get("experiment")) is not None:   
        experiment = cast(models.Experiment, experiment)
        template = "components/tables/experiment-pool.html" 
        stmt = Q.pool.select(experiment_id=experiment.id, statement=stmt)
        table.url_params["experiment_id"] = experiment.id
        table.active_page = None
        context["can_edit_pooling"] = (
            (
                current_user.is_insider() and
                experiment.status == C.ExperimentStatus.DRAFT and 
                not experiment.workflow.combined_lanes
            ) or 
            (
                current_user.is_admin() and not experiment.workflow.combined_lanes
            )
        )
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-pool.html"
        stmt = Q.pool.select(lab_prep_id=lab_prep.id, statement=stmt)
        table.url_params["lab_prep_id"] = lab_prep.id
    else:
        template = "components/tables/pool.html"
        if not current_user.is_insider():
            stmt = Q.pool.select(user_id=current_user.id, statement=stmt)

    pools, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
        
    context.update({
        "pools": pools,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def get_search_context(current_user: models.User, request: Request, **kwargs) -> dict:
    context = parse_context(current_user, request) | kwargs
    page = request.args.get("page", 0, type=int)
    stmt = sa.select(models.Pool)
    
    if (name := request.args.get("name")) is not None:
        if (name := name.strip()):
            stmt = Q.pool.select(search_name=name, statement=stmt)
        else:
            stmt = stmt.order_by(sa.nulls_last(models.Pool.name.asc()))
    else:
        raise exceptions.BadRequestException("No valid search parameters provided.")

    if (seq_request := context.get("seq_request")) is not None:
        stmt = Q.pool.select(seq_request_id=seq_request.id, statement=stmt)
    elif (experiment := context.get("experiment")) is not None:   
        experiment = cast(models.Experiment, experiment)
        stmt = Q.pool.select(experiment_id=experiment.id, statement=stmt)
    elif (lab_prep := context.get("lab_prep")) is not None:
        stmt = Q.pool.select(lab_prep_id=lab_prep.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.pool.select(user_id=current_user.id, statement=stmt)
    
    # pools, num_pages = db.pools.find(page=page, **fnc_context)
    pools, count = db.session.page(stmt, page=page)

    context.update({
        "pools": pools,
        "template_name_or_list": "components/search/pool.html",
    })
    return context


def get_browse_context(current_user: models.User, request: Request, **kwargs) -> dict:    
    table = PoolTable(route="pools_htmx.browse", page=request.args.get("page", 0, type=int))
    table.url_params["workflow"] = kwargs["workflow"]
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    context = parse_context(current_user, request) | kwargs
    stmt = sa.select(models.Pool)

    if (status_in := request.args.get("status_in")):
        status_in = json.loads(status_in)
        try:
            status_in = [C.PoolStatus.get(int(status)) for status in status_in]
            if status_in:
                stmt = Q.pool.select(status_in=status_in, statement=stmt)
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")):
        type_in = json.loads(type_in)
        try:
            type_in = [C.PoolType.get(int(type)) for type in type_in]
            if type_in:
                stmt = Q.pool.select(type_in=type_in, statement=stmt)
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")):
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [C.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                stmt = Q.pool.select(library_types_in=library_types_in, statement=stmt)
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (experiment := context.get("experiment")) is not None:
        stmt = Q.pool.select(experiment_id=experiment.id, statement=stmt)
    if (seq_request := context.get("seq_request")) is not None:
        stmt = Q.pool.select(seq_request_id=seq_request.id, statement=stmt)

    if (name := request.args.get("name")):
        stmt = Q.pool.select(search_name=name, statement=stmt)
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")):
        table.active_search_var = "id"
        table.active_query_value = str(id_)
        try:
            id_ = int("".join(filter(str.isdigit, id_)))
            stmt = Q.pool.select(id=id_, statement=stmt)
        except ValueError:
            pass
    elif (owner := request.args.get("owner")):
        stmt = Q.pool.select(search_owner_name=owner, statement=stmt)
        table.active_search_var = "owner"
        table.active_query_value = owner

    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        try:
            stmt = stmt.order_by(getattr(getattr(models.Pool, sort_by), "desc" if descending else "asc")())
        except AttributeError:
            raise exceptions.BadRequestException()
        table.active_sort_var = sort_by
        table.active_sort_descending = descending


    if (seq_request := context.get("seq_request")) is not None:
        stmt = Q.pool.select(seq_request_id=seq_request.id, statement=stmt)
    elif (experiment := context.get("experiment")) is not None:   
        experiment = cast(models.Experiment, experiment)
        stmt = Q.pool.select(experiment_id=experiment.id, statement=stmt)
    elif (lab_prep := context.get("lab_prep")) is not None:
        stmt = Q.pool.select(lab_prep_id=lab_prep.id, statement=stmt)
    else:
        if not current_user.is_insider():
            stmt = Q.pool.select(user_id=current_user.id, statement=stmt)

    if kwargs["workflow"] == "select_experiment_pools":
        stmt = Q.pool.select(experiment_id=None, statement=stmt)

    pools, count = db.session.page(stmt, page=table.active_page or 0)
    table.set_num_pages(count)
    
    context.update({
        "pools": pools,
        "template_name_or_list": "components/tables/select-pools.html",
        "table": table,
    })
    return context