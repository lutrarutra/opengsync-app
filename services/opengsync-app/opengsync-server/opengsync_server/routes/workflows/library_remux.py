from flask import Blueprint, request

from opengsync_db import models
from opengsync_db.categories import LibraryType, LibraryStatus, AccessType

from ... import db, logger  # noqa
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

    if library.type == LibraryType.TENX_SC_GEX_FLEX:
        return forms.LibraryReMuxForm(library=library).make_response()
    
    if library.type == LibraryType.TENX_SC_ABC_FLEX:
        return forms.LibraryReFlexABCForm(library=library).make_response()
    
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
        
    return forms.LibraryReMuxForm(library=library, formdata=request.form).process_request()


@wrappers.htmx_route(library_remux_workflow, db=db, methods=["POST"])
def parse_flex_abc_annotation(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
        
    return forms.LibraryReFlexABCForm(library=library, formdata=request.form).process_request()