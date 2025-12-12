import json

from flask import Request

from opengsync_db import models, categories, PAGE_LIMIT

from ..import db
from ..core import exceptions

def render_project_table(current_user: models.User, request: Request) -> dict:
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

    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-project.html"
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if user_id != current_user.id and not current_user.is_insider():
            raise exceptions.NoPermissionsException()
        
        if (user := db.users.get(user_id)) is None:
            raise exceptions.NotFoundException()
        
        projects, n_pages = db.projects.find(offset=offset, user_id=user_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["user"] = user
    elif (experiment_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-project.html"
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException()
        
        projects, n_pages = db.projects.find(offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["experiment"] = experiment
    elif (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-project.html"
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException()
        
        projects, n_pages = db.projects.find(offset=offset, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
        context["seq_request"] = seq_request
    elif (group_id := request.args.get("group_id", None)) is not None:
        template = "components/tables/group-project.html"
        try:
            group_id = int(group_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (group := db.groups.get(group_id)) is None:
            raise exceptions.NotFoundException()
        
        projects, n_pages = db.projects.find(offset=offset, group_id=group_id, sort_by=sort_by, descending=descending, count_pages=True, status_in=status_in)
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


def render_seq_request_table(current_user: models.User, request: Request) -> dict:
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

    if (user_id := request.args.get("user_id", None)) is not None:
        template = "components/tables/user-seq_request.html"
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if user_id != current_user.id and not current_user.is_insider():
            raise exceptions.NoPermissionsException()
        
        if (user := db.users.get(user_id)) is None:
            raise exceptions.NotFoundException()
        
        seq_requests, n_pages = db.seq_requests.find(offset=offset, user_id=user_id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
        context["user"] = user
    elif (group_id := request.args.get("group_id", None)) is not None:
        template = "components/tables/group-seq_request.html"
        try:
            group_id = int(group_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (group := db.groups.get(group_id)) is None:
            raise exceptions.NotFoundException()
        
        seq_requests, n_pages = db.seq_requests.find(offset=offset, group_id=group_id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
        context["group"] = group
    elif (project_id := request.args.get("project_id", None)) is not None:
        template = "components/tables/project-seq_request.html"
        try:
            project_id = int(project_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (project := db.projects.get(project_id)) is None:
            raise exceptions.NotFoundException()
        
        seq_requests, n_pages = db.seq_requests.find(offset=offset, project_id=project_id, sort_by=sort_by, status_in=status_in, submission_type_in=submission_type_in, descending=descending, count_pages=True)
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