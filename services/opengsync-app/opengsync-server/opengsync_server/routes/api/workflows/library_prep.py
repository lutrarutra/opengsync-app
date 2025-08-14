from flask import Blueprint, request, abort, Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import HTTPResponse, LibraryStatus, LibraryType, LabProtocol

from .... import db
from ....core import wrappers
from ....forms.SelectSamplesForm import SelectSamplesForm

library_prep_workflow = Blueprint("library_prep_workflow", __name__, url_prefix="/api/workflows/library_prep/")


args: dict = dict(
    workflow="library_prep",
    select_libraries=True,
    library_status_filter=[LibraryStatus.ACCEPTED],
    select_all_libraries=True,
)


@wrappers.htmx_route(library_prep_workflow, db=db)
def begin(current_user: models.User, lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    _args = args.copy()
    if lab_prep.protocol == LabProtocol.CUSTOM:
        _args["library_type_filter"] = None
    else:
        _args["library_type_filter"] = LibraryType.get_protocol_library_types(lab_prep.protocol)

    form = SelectSamplesForm(**_args, context={"lab_prep": lab_prep})
    return form.make_response()


@wrappers.htmx_route(library_prep_workflow, db=db, methods=["POST"])
def select(current_user: models.User, lab_prep_id: int) -> Response:
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    _args = args.copy()
    if lab_prep.protocol == LabProtocol.CUSTOM:
        _args["library_type_filter"] = None
    else:
        _args["library_type_filter"] = LibraryType.get_protocol_library_types(lab_prep.protocol)
    
    form = SelectSamplesForm(formdata=request.form, context={"lab_prep": lab_prep}, **_args)
    
    if not form.validate():
        return form.make_response()

    for _, row in form.library_table.iterrows():
        lab_prep = db.add_library_to_prep(
            lab_prep_id=lab_prep_id,
            library_id=row["id"],
        )

    flash("Libraries added!", "success")
    return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=lab_prep_id))