from flask import Request

from opengsync_db import models, categories

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

    if (sample_id := request.args.get("sample_id", None)) is not None:
        try:
            sample_id = int(sample_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (sample := db.samples.get(sample_id)) is None:
            raise exceptions.NotFoundException()
        
        access_type = db.samples.get_access_type(sample=sample, user=current_user)
        if access_type < categories.AccessType.VIEW:
            raise exceptions.NoPermissionsException()
        
        context["sample"] = sample
    
    return context