import json

from flask import Request

from opengsync_db import models, categories, PAGE_LIMIT

from ..import db, logger
from ..core import exceptions
from .context import parse_context

def render_project_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}
    page = request.args.get("page", 0, type=int)
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.Project.sortable_fields:
        raise exceptions.BadRequestException()

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.ProjectStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
        else:
            context["status_in"] = status_in

    context |= parse_context(current_user, request) | kwargs

    if (user := context.get("user")) is not None:
        template = "components/tables/user-project.html"
        projects, n_pages = db.projects.find(offset=offset, user_id=user.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["user"] = user

    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-project.html"        
        projects, n_pages = db.projects.find(offset=offset, experiment_id=experiment.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["experiment"] = experiment

    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-project.html"
        projects, n_pages = db.projects.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["seq_request"] = seq_request

    elif (group := context.get("group")) is not None:
        template = "components/tables/group-project.html"
        projects, n_pages = db.projects.find(offset=offset, group_id=group.id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["group"] = group
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        projects, n_pages = db.projects.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)

    context.update({
        "projects": projects,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "status_in": status_in,
        "template_name_or_list": template,
    })

    return context


def render_seq_request_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}
    page = request.args.get("page", 0, type=int)
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.SeqRequest.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.SeqRequestStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(status_in) == 0:
            status_in = None
        else:
            context["status_in"] = status_in

    if (submission_type_in := request.args.get("submission_type_id_in")) is not None:
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [categories.SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(submission_type_in) == 0:
            submission_type_in = None
        else:
            context["submission_type_in"] = submission_type_in

    context |= parse_context(current_user, request) | kwargs

    if (user := context.get("user")) is not None:
        template = "components/tables/user-seq_request.html"
        seq_requests, n_pages = db.seq_requests.find(offset=offset, user_id=user.id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
        context["user"] = user
    elif (group := context.get("group")) is not None:
        template = "components/tables/group-seq_request.html"
        seq_requests, n_pages = db.seq_requests.find(offset=offset, group_id=group.id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
        context["group"] = group
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-seq_request.html"        
        seq_requests, n_pages = db.seq_requests.find(offset=offset, project_id=project.id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
        context["project"] = project
    else:
        template = "components/tables/seq_request.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        seq_requests, n_pages = db.seq_requests.find(offset=offset, user_id=user_id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)


    context.update({
        "seq_requests": seq_requests,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "template_name_or_list": template,
    })

    return context

def render_pool_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}
    page = request.args.get("page", 0, type=int)
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.Pool.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.PoolStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
        else:
            context["status_in"] = status_in
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.PoolType.get(int(type)) for type in type_in]
        except ValueError:
            raise exceptions.BadRequestException()

        if len(type_in) == 0:
            type_in = None
        else:
            context["type_in"] = type_in

    context |= parse_context(current_user, request) | kwargs

    if (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-pool.html"        
        pools, n_pages = db.pools.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, page=None, limit=None)
        context["seq_request"] = seq_request

    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-pool.html"  
        pools, n_pages = db.pools.find(offset=offset, experiment_id=experiment.id, sort_by=sort_by, descending=descending, page=None, limit=None)
        context["experiment"] = experiment

    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-pool.html"
        pools, n_pages = db.pools.find(offset=offset, lab_prep_id=lab_prep.id, sort_by=sort_by, descending=descending, page=None, limit=None)
        context["lab_prep"] = lab_prep

    else:
        template = "components/tables/pool.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        pools, n_pages = db.pools.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, page=page)
        
    context.update({
        "pools": pools,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "template_name_or_list": template,
    })

    return context

def render_library_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}
    page = request.args.get("page", 0, type=int)
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    logger.debug(page)
    logger.debug(offset)

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
        else:
            context["status_in"] = status_in

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None
        else:
            context["type_in"] = type_in

    if sort_by not in models.Library.sortable_fields:
        raise exceptions.BadRequestException()
    
    context |= parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-library.html"        
        libraries, n_pages = db.libraries.find(offset=offset, pool_id=pool.id, sort_by=sort_by, descending=descending, page=page)
        context["pool"] = pool
    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-library.html"  
        libraries, n_pages = db.libraries.find(offset=offset, experiment_id=experiment.id, sort_by=sort_by, descending=descending, page=page)
        context["experiment"] = experiment
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-library.html"
        libraries, n_pages = db.libraries.find(offset=offset, lab_prep_id=lab_prep.id, sort_by=sort_by, descending=descending, page=page)
        context["lab_prep"] = lab_prep
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-library.html"        
        libraries, n_pages = db.libraries.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, page=page)
        context["seq_request"] = seq_request
    elif (sample := context.get("sample")) is not None:
        template = "components/tables/sample-library.html"        
        libraries, n_pages = db.libraries.find(offset=offset, sample_id=sample.id, sort_by=sort_by, descending=descending, page=page)
        context["sample"] = sample
    else:
        template = "components/tables/library.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        libraries, n_pages = db.libraries.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, page=page)
        
    context.update({
        "libraries": libraries,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "template_name_or_list": template,
    })
    logger.debug(n_pages)
    logger.debug(page)
    return context


def render_sample_table(current_user: models.User, request: Request, **kwargs) -> dict:
    context = {}
    page = request.args.get("page", 0, type=int)
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if sort_by not in models.Sample.sortable_fields:
        raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
        else:
            context["status_in"] = status_in
    
    context |= parse_context(current_user, request) | kwargs

    if (library := context.get("library")) is not None:
        template = "components/tables/library-sample.html"        
        samples, n_pages = db.samples.find(offset=offset, library_id=library.id, sort_by=sort_by, descending=descending, page=page)
        context["library"] = library
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-sample.html"        
        samples, n_pages = db.samples.find(offset=offset, project_id=project.id, sort_by=sort_by, descending=descending, page=page)
        context["project"] = project
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-sample.html"        
        samples, n_pages = db.samples.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, page=page)
        context["seq_request"] = seq_request
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-sample.html"
        samples, n_pages = db.samples.find(offset=offset, lab_prep_id=lab_prep.id, sort_by=sort_by, descending=descending, page=page)
        context["lab_prep"] = lab_prep
    else:
        template = "components/tables/sample.html"
        if not current_user.is_insider():
            user_id = current_user.id
        else:
            user_id = None
        samples, n_pages = db.samples.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, page=page)
        
    context.update({
        "samples": samples,
        "n_pages": n_pages,
        "active_page": page,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "template_name_or_list": template,
    })
    return context