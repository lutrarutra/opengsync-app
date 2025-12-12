import json

from flask import Request

from opengsync_db import models, categories, PAGE_LIMIT

from ..import db
from ..core import exceptions

def parse_context(current_user: models.User, request: Request) -> dict:
    context = {}
    if (group_id := request.args.get("group_id", None)) is not None:
        try:
            group_id = int(group_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (group := db.groups.get(group_id)) is None:
            raise exceptions.NotFoundException()
        
        if not current_user.is_insider():
            if db.groups.get_user_affiliation(group_id=group.id, user_id=current_user.id) is None:
                raise exceptions.NoPermissionsException()
        
        context["group"] = group
    
    if (project_id := request.args.get("project_id", None)) is not None:
        try:
            project_id = int(project_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (project := db.projects.get(project_id)) is None:
            raise exceptions.NotFoundException()
        
        access_type = db.projects.get_access_type(project, current_user)
        if access_type < categories.AccessType.VIEW:
            raise exceptions.NoPermissionsException()
        
        context["project"] = project

    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        
        access_type = db.seq_requests.get_access_type(seq_request, current_user)
        if access_type < categories.AccessType.VIEW:
            raise exceptions.NoPermissionsException()
        
        context["seq_request"] = seq_request

    if (experiment_id := request.args.get("experiment_id", None)) is not None:
        if not current_user.is_insider():
            raise exceptions.NoPermissionsException()
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException()
        
        context["experiment"] = experiment

    if (lab_prep_id := request.args.get("lab_prep_id", None)) is not None:
        if not current_user.is_insider():   
            raise exceptions.NoPermissionsException()
        try:
            lab_prep_id = int(lab_prep_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
            raise exceptions.NotFoundException()
        
        context["lab_prep"] = lab_prep

    if (user_id := request.args.get("user_id", None)) is not None:
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if not current_user.is_insider() and user_id != current_user.id:
            raise exceptions.NoPermissionsException()
        
        if (user := db.users.get(user_id)) is None:
            raise exceptions.NotFoundException()
        
        context["user"] = user

    if (pool_id := request.args.get("pool_id", None)) is not None:
        try:
            pool_id = int(pool_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (pool := db.pools.get(pool_id)) is None:
            raise exceptions.NotFoundException()
        
        access_type = db.pools.get_access_type(pool=pool, user=current_user)
        if access_type < categories.AccessType.VIEW:
            raise exceptions.NoPermissionsException()
        
        context["pool"] = pool

    if (library_id := request.args.get("library_id", None)) is not None:
        try:
            library_id = int(library_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (library := db.libraries.get(library_id)) is None:
            raise exceptions.NotFoundException()
        
        access_type = db.libraries.get_access_type(library=library, user=current_user)
        if access_type < categories.AccessType.VIEW:
            raise exceptions.NoPermissionsException()
        
        context["library"] = library
    
    return context

def render_project_table(current_user: models.User, request: Request, *kwargs) -> dict:
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

    context |= parse_context(current_user, request)

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


def render_seq_request_table(current_user: models.User, request: Request, *kwargs) -> dict:
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

    if (submission_type_in := request.args.get("submission_type_id_in")) is not None:
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [categories.SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
        except ValueError:
            raise exceptions.BadRequestException()
        
        if len(submission_type_in) == 0:
            submission_type_in = None

    context |= parse_context(current_user, request)

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
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.PoolType.get(int(type)) for type in type_in]
        except ValueError:
            raise exceptions.BadRequestException()

        if len(type_in) == 0:
            type_in = None

    context |= parse_context(current_user, request) | kwargs

    if (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-pool.html"        
        pools, n_pages = db.pools.find(offset=offset, seq_request_id=seq_request.id, sort_by=sort_by, descending=descending, page=None)
        context["seq_request"] = seq_request

    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-pool.html"  
        pools, n_pages = db.pools.find(offset=offset, experiment_id=experiment.id, sort_by=sort_by, descending=descending, page=None)
        context["experiment"] = experiment

    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-pool.html"
        pools, n_pages = db.pools.find(offset=offset, lab_prep_id=lab_prep.id, sort_by=sort_by, descending=descending, page=None)
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