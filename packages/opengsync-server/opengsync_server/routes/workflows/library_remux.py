from flask import Blueprint, request

from opengsync_db import models
from opengsync_db.categories import LibraryType, LibraryStatus, AccessType, MUXType

from ... import db, logger
from ...forms.workflows import remux as forms
from ...core import wrappers, exceptions

library_remux_workflow = Blueprint("library_remux_workflow", __name__, url_prefix="/workflows/reseq/")


@wrappers.htmx_route(library_remux_workflow, db=db)
def begin(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    match library.mux_type:
        case MUXType.TENX_FLEX_PROBE:
            return forms.FlexReMuxForm(library=library).make_response()
        case MUXType.TENX_OLIGO:
            return forms.OligoReMuxForm(library=library).make_response()
        case MUXType.TENX_ABC_HASH:
            return forms.OligoReMuxForm(library=library).make_response()
        case _:
            raise exceptions.BadRequestException()
    

@wrappers.htmx_route(library_remux_workflow, db=db, methods=["POST"])
def parse_flex_annotation(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
        
    return forms.FlexReMuxForm(library=library, formdata=request.form).process_request()


@wrappers.htmx_route(library_remux_workflow, db=db, methods=["POST"])
def parse_oligo_mux_reference(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    return forms.OligoReMuxForm(library=library, formdata=request.form).process_request()