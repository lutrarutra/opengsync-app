from flask import Blueprint, request, abort

from opengsync_db import models
from opengsync_db.categories import LibraryType
from opengsync_db.categories import HTTPResponse

from .... import db, logger  # noqa
from ....forms.workflows import remux as forms
from ....core import wrappers

library_remux_workflow = Blueprint("library_remux_workflow", __name__, url_prefix="/api/workflows/reseq/")


@wrappers.htmx_route(library_remux_workflow, db=db)
def begin(current_user: models.User, library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    if library.type == LibraryType.TENX_SC_GEX_FLEX:
        return forms.LibraryReMuxForm(library=library).make_response()
    
    if library.type == LibraryType.TENX_SC_ABC_FLEX:
        return forms.LibraryReFlexABCForm(library=library).make_response()
    
    return abort(HTTPResponse.BAD_REQUEST.id)
    

@wrappers.htmx_route(library_remux_workflow, db=db, methods=["POST"])
def parse_flex_annotation(current_user: models.User, library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return forms.LibraryReMuxForm(library=library, formdata=request.form).process_request()


@wrappers.htmx_route(library_remux_workflow, db=db, methods=["POST"])
def parse_flex_abc_annotation(current_user: models.User, library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    return forms.LibraryReFlexABCForm(library=library, formdata=request.form).process_request()