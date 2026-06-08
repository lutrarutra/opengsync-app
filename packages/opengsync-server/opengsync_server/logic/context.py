from flask import Request

from opengsync_db import models, queries as Q
from opengsync_db.categories import AccessLevel

from ..import db
from ..core import exceptions

def parse_context(current_user: models.User, request: Request) -> dict:
    context = {}
    if (group_id := request.args.get("group_id", None)) is not None:
        try:
            group_id = int(group_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (group := db.session.first(Q.group.select(id=group_id))) is None:
            raise exceptions.NotFoundException()
        
        if not current_user.is_insider():
            if db.session.first(Q.affiliation.select(group_id=group.id, user_id=current_user.id)) is None:
                raise exceptions.NoPermissionsException()
        
        context["group"] = group
    
    if (project_id := request.args.get("project_id", None)) is not None:
        try:
            project_id = int(project_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (project := db.session.first(Q.project.select(id=project_id))) is None:
            raise exceptions.NotFoundException()
        
        access_level = db.session.get_access_level(Q.project.permissions(project_id=project_id, user_id=current_user.id))
        if access_level < AccessLevel.READ:
            raise exceptions.NoPermissionsException()
        
        context["project"] = project

    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (seq_request := db.session.first(Q.seq_request.select(id=seq_request_id))) is None:
            raise exceptions.NotFoundException()
        
        access_level = db.session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id))
        if access_level < AccessLevel.READ:
            raise exceptions.NoPermissionsException()
        
        context["seq_request"] = seq_request

    if (experiment_id := request.args.get("experiment_id", None)) is not None:
        if not current_user.is_insider():
            raise exceptions.NoPermissionsException()
        try:
            experiment_id = int(experiment_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (experiment := db.session.first(Q.experiment.select(id=experiment_id))) is None:
            raise exceptions.NotFoundException()
        
        context["experiment"] = experiment

    if (lab_prep_id := request.args.get("lab_prep_id", None)) is not None:
        if not current_user.is_insider():   
            raise exceptions.NoPermissionsException()
        try:
            lab_prep_id = int(lab_prep_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (lab_prep := db.session.first(Q.lab_prep.select(id=lab_prep_id))) is None:
            raise exceptions.NotFoundException()
        
        context["lab_prep"] = lab_prep

    if (user_id := request.args.get("user_id", None)) is not None:
        try:
            user_id = int(user_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if not current_user.is_insider() and user_id != current_user.id:
            raise exceptions.NoPermissionsException()
        
        if (user := db.session.first(Q.user.select(id=user_id))) is None:
            raise exceptions.NotFoundException()
        
        context["user"] = user

    if (pool_id := request.args.get("pool_id", None)) is not None:
        try:
            pool_id = int(pool_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (pool := db.session.first(Q.pool.select(id=pool_id))) is None:
            raise exceptions.NotFoundException()
        
        access_level = db.session.get_access_level(Q.pool.permissions(pool_id=pool_id, user_id=current_user.id))
        if access_level < AccessLevel.READ:
            raise exceptions.NoPermissionsException()
        
        context["pool"] = pool

    if (library_id := request.args.get("library_id", None)) is not None:
        try:
            library_id = int(library_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (library := db.session.first(Q.library.select(id=library_id))) is None:
            raise exceptions.NotFoundException()
        
        access_level = db.session.get_access_level(Q.library.permissions(library_id=library_id, user_id=current_user.id))
        if access_level < AccessLevel.READ:
            raise exceptions.NoPermissionsException()
        
        context["library"] = library

    if (sample_id := request.args.get("sample_id", None)) is not None:
        try:
            sample_id = int(sample_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (sample := db.session.first(Q.sample.select(id=sample_id))) is None:
            raise exceptions.NotFoundException()
        
        access_level = db.session.get_access_level(Q.sample.permissions(sample_id=sample_id, user_id=current_user.id))
        if access_level < AccessLevel.READ:
            raise exceptions.NoPermissionsException()
        
        context["sample"] = sample

    if (index_kit_id := request.args.get("index_kit_id", None)) is not None:
        try:
            index_kit_id = int(index_kit_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (index_kit := db.session.first(Q.index_kit.select(id=index_kit_id))) is None:
            raise exceptions.NotFoundException()
        
        context["index_kit"] = index_kit

    if (feature_kit_id := request.args.get("feature_kit_id", None)) is not None:
        try:
            feature_kit_id = int(feature_kit_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (feature_kit := db.session.first(Q.feature_kit.select(id=feature_kit_id))) is None:
            raise exceptions.NotFoundException()
        
        context["feature_kit"] = feature_kit

    if (protocol_id := request.args.get("protocol_id", None)) is not None:
        try:
            protocol_id = int(protocol_id)
        except ValueError:
            raise exceptions.BadRequestException()
        
        if (protocol := db.session.first(Q.protocol.select(id=protocol_id))) is None:
            raise exceptions.NotFoundException()
        
        context["protocol"] = protocol
    
    return context