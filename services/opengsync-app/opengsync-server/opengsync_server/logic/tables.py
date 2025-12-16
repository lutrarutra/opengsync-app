import json

from flask import Request, url_for

from opengsync_db import models, categories, PAGE_LIMIT

from ..import db, logger
from ..tools.HTMXTable import AffiliationTable, ExperimentTable, GroupTable, LabPrepTable, LibraryTable, PoolTable, ProjectTable, SampleTable, SeqRequestTable, UserTable
from ..core import exceptions
from .context import parse_context

def render_project_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = ProjectTable(route="projects_htmx.get")

    if (identifier := request.args.get("identifier")) is not None:
        fnc_context["identifier"] = identifier
        table.active_search_var = "identifier"
        table.active_query_value = identifier
    elif (title := request.args.get("title")) is not None:
        fnc_context["title"] = title
        table.active_search_var = "title"
        table.active_query_value = title
    elif (project_id := request.args.get("id")) is not None:
        try:
            project_id = int(project_id)
            fnc_context["id"] = project_id
            table.active_search_var = "id"
            table.active_query_value = str(project_id)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner_name := request.args.get("owner_name")) is not None:
        fnc_context["owner_name"] = owner_name
        table.active_search_var = "owner_name"
        table.active_query_value = owner_name
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Project.sortable_fields:
            raise exceptions.BadRequestException()

        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.ProjectStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")) is not None:
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [categories.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                fnc_context["library_types_in"] = library_types_in
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (user := context.get("user")) is not None:
        template = "components/tables/user-project.html"
        fnc_context["user_id"] = user.id
        table.url_params["user_id"] = user.id

    elif (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-project.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id

    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-project.html"
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id

    elif (group := context.get("group")) is not None:
        template = "components/tables/group-project.html"
        fnc_context["group_id"] = group.id
        table.url_params["group_id"] = group.id
    else:
        template = "components/tables/project.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    projects, n_pages = db.projects.find(page=page, **fnc_context)

    context.update({
        "projects": projects,
        "n_pages": n_pages,
        "active_page": page,
        "status_in": status_in,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def render_seq_request_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = SeqRequestTable(route="seq_requests_htmx.get")
    
    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.SeqRequestStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (submission_type_in := request.args.get("submission_type_in")) is not None:
        submission_type_in = json.loads(submission_type_in)
        try:
            submission_type_in = [categories.SubmissionType.get(int(submission_type)) for submission_type in submission_type_in]
            if submission_type_in:
                fnc_context["submission_type_in"] = submission_type_in
                table.filter_values["submission_type"] = submission_type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")) is not None:
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [categories.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                fnc_context["library_types_in"] = library_types_in
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (user := context.get("user")) is not None:
        template = "components/tables/user-seq_request.html"
        fnc_context["user_id"] = user.id
        table.url_params["user_id"] = user.id
    elif (group := context.get("group")) is not None:
        template = "components/tables/group-seq_request.html"
        fnc_context["group_id"] = group.id
        table.url_params["group_id"] = group.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-seq_request.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    else:
        template = "components/tables/seq_request.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (requestor_name := request.args.get("requestor_name")) is not None:
        fnc_context["requestor_name"] = requestor_name
        table.active_search_var = "requestor_name"
        table.active_query_value = requestor_name
    elif (group := request.args.get("group")) is not None:
        fnc_context["group"] = group
        table.active_search_var = "group"
        table.active_query_value = group
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.SeqRequest.sortable_fields:
            raise exceptions.BadRequestException(f"SeqRequest table cannot be sorted by '{sort_by}'.")

        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    seq_requests, n_pages = db.seq_requests.find(page=page, **fnc_context)

    context.update({
        "seq_requests": seq_requests,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })

    return context

def render_pool_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = PoolTable(route="pools_htmx.get")

    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.PoolStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.PoolType.get(int(type)) for type in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (library_types_in := request.args.get("library_types_in")) is not None:
        library_types_in = json.loads(library_types_in)
        try:
            library_types_in = [categories.LibraryType.get(int(library_type)) for library_type in library_types_in]
            if library_types_in:
                fnc_context["library_types_in"] = library_types_in
                table.filter_values["library_types"] = library_types_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")) is not None:
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (owner := request.args.get("owner")) is not None:
        fnc_context["owner"] = owner
        table.active_search_var = "owner"
        table.active_query_value = owner

    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.Pool.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-pool.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id

    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-pool.html"  
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id

    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-pool.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id

    else:
        template = "components/tables/pool.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    pools, n_pages = db.pools.find(page=page, **fnc_context)
        
    context.update({
        "pools": pools,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })

    return context

def render_library_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = LibraryTable(route="libraries_htmx.get")

    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.LibraryStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (type_in := request.args.get("type_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.LibraryType.get(int(type_)) for type_ in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (pool_name := request.args.get("pool_name")) is not None:
        fnc_context["pool_name"] = pool_name
        table.active_search_var = "pool_name"
        table.active_query_value = pool_name
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.Library.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
    
    context = parse_context(current_user, request) | kwargs

    if (pool := context.get("pool")) is not None:
        template = "components/tables/pool-library.html"        
        fnc_context["pool_id"] = pool.id
        table.url_params["pool_id"] = pool.id
    elif (experiment := context.get("experiment")) is not None:      
        template = "components/tables/experiment-library.html"  
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-library.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-library.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (sample := context.get("sample")) is not None:
        template = "components/tables/sample-library.html"        
        fnc_context["sample_id"] = sample.id
        table.url_params["sample_id"] = sample.id
    else:
        template = "components/tables/library.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    libraries, n_pages = db.libraries.find(page=page, **fnc_context)
        
    context.update({
        "libraries": libraries,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def render_sample_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = SampleTable(route="samples_htmx.get")

    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.SampleStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
    

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.Sample.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (library := context.get("library")) is not None:
        template = "components/tables/library-sample.html"        
        fnc_context["library_id"] = library.id
        table.url_params["library_id"] = library.id
    elif (project := context.get("project")) is not None:
        template = "components/tables/project-sample.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-sample.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    elif (lab_prep := context.get("lab_prep")) is not None:
        template = "components/tables/lab_prep-sample.html"
        fnc_context["lab_prep_id"] = lab_prep.id
        table.url_params["lab_prep_id"] = lab_prep.id
    else:
        template = "components/tables/sample.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id

    samples, n_pages = db.samples.find(page=page, **fnc_context)
    
    context.update({
        "samples": samples,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })
    return context


def render_user_table(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = UserTable(route="users_htmx.get")

    users, n_pages = db.users.find(page=page)

    if (role_in := request.args.get("role_in")) is not None:
        role_in = json.loads(role_in)
        try:
            role_in = [categories.UserRole.get(int(role)) for role in role_in]
            if role_in:
                fnc_context["role_in"] = role_in
                table.filter_values["role"] = role_in
        except ValueError:
            raise exceptions.BadRequestException()

    context = parse_context(current_user, request) | kwargs

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.User.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending
        

    template = "components/tables/user.html"
    if not current_user.is_insider():
        fnc_context["user_id"] = current_user.id

    users, n_pages = db.users.find(page=page, **fnc_context)

    context.update({
        "users": users,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def render_affiliation_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = AffiliationTable(route="")

    context = parse_context(current_user, request) | kwargs
    
    if (user_name := request.args.get("user_name")) is not None:
        fnc_context["user_name"] = user_name
        table.active_search_var = "user_name"
        table.active_query_value = user_name
    elif (group_name := request.args.get("group_name")) is not None:
        fnc_context["group_name"] = group_name
        table.active_search_var = "group_name"
        table.active_query_value = group_name
    elif (id_ := request.args.get("id")) is not None:
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    else:
        sort_by = request.args.get("sort_by", "affiliation_type_id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.links.UserAffiliation.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (group := context.get("group")) is not None:
        template = "components/tables/group-user.html"
        table.route = "groups_htmx.get_affiliations"
        affiliation = db.groups.get_user_affiliation(current_user.id, group.id)
        context["can_add_users"] = current_user.is_insider() or affiliation is not None and affiliation.affiliation_type in (categories.AffiliationType.OWNER, categories.AffiliationType.MANAGER)
        table.url_params["group_id"] = group.id
        affiliations, n_pages = db.groups.get_affiliations(group_id=group.id, page=page, **fnc_context)
    elif (user := context.get("user")) is not None:
        template = "components/tables/user-affiliation.html"
        table.route = "users_htmx.get_affiliations"
        table.url_params["user_id"] = user.id
        affiliations, n_pages = db.users.get_affiliations(user_id=user.id, page=page, **fnc_context)
    else:
        raise exceptions.BadRequestException("Group or User context is required to render group affiliation table.")

    context.update({
        "affiliations": affiliations,
        "n_pages": n_pages,
        "active_page": page,
        "group": group,
        "template_name_or_list": template,
        "table": table,
    })

    return context


def render_group_table(current_user: models.User, request: Request, **kwargs) -> dict:
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = GroupTable(route="groups_htmx.get")

    if (type_in := request.args.get("type_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [categories.GroupType.get(int(role)) for role in type_in]
            if type_in:
                fnc_context["type_in"] = type_in
                table.filter_values["type"] = type_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.Group.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if not current_user.is_insider():
        fnc_context["user_id"] = current_user.id

    groups, n_pages = db.groups.find(page=page, **fnc_context)

    context = parse_context(current_user, request) | kwargs
    context.update({
        "groups": groups,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": "components/tables/group.html",
        "table": table,
    })
    return context


def render_experiment_table(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    fnc_context = {}

    table = ExperimentTable(route="experiments_htmx.get", page=request.args.get("page", 0, type=int))

    context = parse_context(current_user, request) | kwargs

    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.ExperimentStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()  
    
    if (workflow_in := request.args.get("workflow_in")) is not None:
        workflow_in = json.loads(workflow_in)
        try:
            workflow_in = [categories.ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_in]
            if workflow_in:
                fnc_context["workflow_in"] = workflow_in
                table.filter_values["workflow"] = workflow_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (operator := request.args.get("operator")) is not None:
        fnc_context["operator"] = operator
        table.active_search_var = "operator"
        table.active_query_value = operator
    elif (id_ := request.args.get("id")) is not None:
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
        if sort_by not in models.Experiment.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (project := context.get("project")) is not None:
        template = "components/tables/project-experiment.html"        
        fnc_context["project_id"] = project.id
        table.url_params["project_id"] = project.id
    elif (seq_request := context.get("seq_request")) is not None:
        template = "components/tables/seq_request-experiment.html"        
        fnc_context["seq_request_id"] = seq_request.id
        table.url_params["seq_request_id"] = seq_request.id
    else:
        template = "components/tables/experiment.html"
        if not current_user.is_insider():
            fnc_context["user_id"] = current_user.id   

    experiments, table.num_pages = db.experiments.find(page=table.active_page, **fnc_context)
    context.update({
        "experiments": experiments,
        "template_name_or_list": template,
        "table": table,
    })
    return context


def render_lab_prep_table(current_user: models.User, request: Request, **kwargs) -> dict:
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException("You do not have permission to view this resource.")
    fnc_context = {}
    page = request.args.get("page", 0, type=int)

    table = LabPrepTable(route="lab_preps_htmx.get")

    context = parse_context(current_user, request) | kwargs
    
    if (status_in := request.args.get("status_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [categories.PrepStatus.get(int(status)) for status in status_in]
            if status_in:
                fnc_context["status_in"] = status_in
                table.filter_values["status"] = status_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (checklist_type_in := request.args.get("checklist_in")) is not None:
        checklist_type_in = json.loads(checklist_type_in)
        try:
            checklist_type_in = [categories.LabChecklistType.get(int(checklist_type)) for checklist_type in checklist_type_in]
            if checklist_type_in:
                fnc_context["checklist_type_in"] = checklist_type_in
                table.filter_values["checklist"] = checklist_type_in
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (service_in := request.args.get("service_in")) is not None:
        service_in = json.loads(service_in)
        try:
            service_in = [categories.ServiceType.get(int(service)) for service in service_in]
            if service_in:
                fnc_context["service_in"] = service_in
                table.filter_values["service"] = service_in
        except ValueError:
            raise exceptions.BadRequestException()

    if (name := request.args.get("name")) is not None:
        fnc_context["name"] = name
        table.active_search_var = "name"
        table.active_query_value = name
    elif (id_ := request.args.get("id")) is not None:
        try:
            id_ = int(id_)
            fnc_context["id"] = id_
            table.active_search_var = "id"
            table.active_query_value = str(id_)
        except ValueError:
            raise exceptions.BadRequestException()
    elif (creator := request.args.get("creator")) is not None:
        fnc_context["creator"] = creator
        table.active_search_var = "creator"
        table.active_query_value = creator
    else:
        sort_by = request.args.get("sort_by", "id")
        sort_order = request.args.get("sort_order", "desc")
        descending = sort_order == "desc"
        if sort_by not in models.LabPrep.sortable_fields:
            raise exceptions.BadRequestException()
        
        fnc_context["sort_by"] = sort_by
        fnc_context["descending"] = descending
        table.active_sort_var = sort_by
        table.active_sort_descending = descending

    if (experiment := context.get("experiment")) is not None:
        template = "components/tables/experiment-lab_prep.html"        
        fnc_context["experiment_id"] = experiment.id
        table.url_params["experiment_id"] = experiment.id
    else:
        template = "components/tables/lab_prep.html"

    lab_preps, n_pages = db.lab_preps.find(page=page, **fnc_context)
        
    context.update({
        "lab_preps": lab_preps,
        "n_pages": n_pages,
        "active_page": page,
        "template_name_or_list": template,
        "table": table,
    })
    return context