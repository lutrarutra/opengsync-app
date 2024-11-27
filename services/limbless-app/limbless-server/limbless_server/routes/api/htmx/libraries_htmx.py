import json
import string
from typing import TYPE_CHECKING

import pandas as pd

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, PAGE_LIMIT, db_session
from limbless_db.categories import HTTPResponse, LibraryType, LibraryStatus

from .... import db, forms, logger  # noqa
from ....tools import SpreadSheetColumn

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/hmtx/libraries/")


@libraries_htmx.route("get", methods=["GET"], defaults={"page": 0})
@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None
    
    libraries, n_pages = db.get_libraries(
        offset=offset,
        user_id=current_user.id if not current_user.is_insider() else None,
        sort_by=sort_by, descending=descending,
        status_in=status_in, type_in=type_in
    )

    return make_response(
        render_template(
            "components/tables/library.html", libraries=libraries,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in, type_in=type_in
        )
    )


@libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
@db_session(db)
@login_required
def edit(library_id):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    if not library.is_editable() and not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)

    return forms.models.LibraryForm(library=library, formdata=request.form).process_request()


@libraries_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.args.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if not current_user.is_insider():
        results = db.query_libraries(name=word, user_id=current_user.id)
    else:
        results = db.query_libraries(name=word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name,
        )
    )


@libraries_htmx.route("<int:library_id>/get_feautres", methods=["GET"], defaults={"page": 0})
@libraries_htmx.route("<int:library_id>/get_feautres/<int:page>", methods=["GET"])
@login_required
def get_features(library_id: int, page: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    features, n_pages = db.get_features(offset=offset, library_id=library_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            "components/tables/library-feature.html",
            features=features, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, library=library
        )
    )


@libraries_htmx.route("<int:library_id>/render_feature_table", methods=["GET"])
@db_session(db)
@login_required
def render_feature_table(library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    df = db.get_library_features_df(library_id=library.id)
    df = df.drop(columns=["feature_type", "feature_type_id", "feature_kit_id"])

    columns = []
    for i, col in enumerate(df.columns):
        if col == "feature_id":
            width = 50
        elif col == "read":
            width = 50
        else:
            width = 200
        columns.append(
            SpreadSheetColumn(
                string.ascii_uppercase[i], col,
                col.replace("_", " ").title().replace("Id", "ID"),
                "text", width, var_type=str
            )
        )
    
    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id=f"library-feature-table-{library_id}"
        )
    )


@libraries_htmx.route("<int:library_id>/get_visium_annotation", methods=["GET"])
@db_session(db)
@login_required
def get_visium_annotation(library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if library.type in [LibraryType.TENX_VISIUM, LibraryType.TENX_VISIUM_FFPE, LibraryType.TENX_VISIUM_HD]:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    visium_annotation = library.visium_annotation
    
    return make_response(
        render_template(
            "components/library-visium-annotation.html",
            visium_annotation=visium_annotation, library=library
        )
    )


@libraries_htmx.route("table_query", methods=["GET"])
@login_required
def table_query():
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("owner_id")) is not None:
        field_name = "owner_id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    user_id = current_user.id if not current_user.is_insider() else None

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.query_libraries(name=word, user_id=user_id, status_in=status_in, type_in=type_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.get_library(_id)) is not None:
                if user_id is not None:
                    if library.owner_id == user_id:
                        libraries = [library]
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
        except ValueError:
            pass
    elif field_name == "owner_id":
        libraries = db.query_libraries(owner=word, user_id=user_id, status_in=status_in, type_in=type_in)

    return make_response(
        render_template(
            "components/tables/library.html",
            current_query=word, active_query_field=field_name,
            libraries=libraries, type_in=type_in, status_in=status_in
        )
    )


@libraries_htmx.route("<int:library_id>/get_samples", methods=["GET"], defaults={"page": 0})
@libraries_htmx.route("<int:library_id>/get_samples/<int:page>", methods=["GET"])
@login_required
def get_samples(library_id: int, page: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    
    samples, n_pages = db.get_samples(
        offset=offset, library_id=library_id, sort_by=sort_by, descending=descending
    )

    return make_response(
        render_template(
            "components/tables/library-sample.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, library=library
        )
    )


@libraries_htmx.route("<int:library_id>/reads_tab", methods=["GET"])
@db_session(db)
@login_required
def reads_tab(library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    return make_response(render_template("components/library-reads.html", library=library))


@libraries_htmx.route("<string:workflow>/browse", methods=["GET"], defaults={"page": 0})
@libraries_htmx.route("<string:workflow>/browse/<int:page>", methods=["GET"])
@login_required
def browse(workflow: str, page: int):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page
    context = {}

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
            
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["experiment_id"] = experiment.id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request_id"] = seq_request.id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["pool_id"] = pool.id
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    libraries, n_pages = db.get_libraries(
        sort_by=sort_by, descending=descending, offset=offset,
        seq_request_id=seq_request_id, experiment_id=experiment_id,
        type_in=type_in, status_in=status_in,
        pool_id=pool_id if workflow != "library_pooling" else None,
        pooled=False if workflow == "library_pooling" else None,
        in_lab_prep=False if workflow == "library_prep" else None
    )
    context["workflow"] = workflow

    return make_response(
        render_template(
            "components/tables/select-libraries.html",
            libraries=libraries, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, status_in=status_in, context=context,
            type_in=type_in, workflow=workflow
        )
    )


@libraries_htmx.route("<string:workflow>/browse_query", methods=["GET"])
@login_required
def browse_query(workflow: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("owner_id")) is not None:
        field_name = "owner_id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["experiment"] = experiment
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["pool"] = pool
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.query_libraries(
            name=word, status_in=status_in, type_in=type_in, experiment_id=experiment_id, seq_request_id=seq_request_id,
            pool_id=pool_id if workflow != "library_pooling" else None,
            pooled=False if workflow == "library_pooling" else None
        )
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.get_library(_id)) is not None:
                libraries = [library]
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
                # FIXME: during library pooling workflow
                if library.pool_id != pool_id:
                    libraries = []
        except ValueError:
            pass
    elif field_name == "owner_id":
        libraries = db.query_libraries(
            owner=word, status_in=status_in, type_in=type_in, experiment_id=experiment_id, seq_request_id=seq_request_id,
            pool_id=pool_id if workflow != "library_pooling" else None,
            pooled=False if workflow == "library_pooling" else None
        )

    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-libraries.html",
            current_query=word, active_query_field=field_name,
            libraries=libraries, type_in=type_in, status_in=status_in, context=context,
            workflow=workflow
        )
    )


@libraries_htmx.route("<string:workflow>/select_all", methods=["GET"])
@login_required
def select_all(workflow: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
            
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(type_in) == 0:
            type_in = None

    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["experiment"] = experiment
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["pool"] = pool
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        
    if (lab_prep_id := request.args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
            if (lab_prep := db.get_lab_prep(lab_prep_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["lab_prep"] = lab_prep
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    libraries, _ = db.get_libraries(
        seq_request_id=seq_request_id, status_in=status_in, type_in=type_in, experiment_id=experiment_id, limit=None,
        pool_id=pool_id if workflow != "library_pooling" else None,
        pooled=False if workflow == "library_pooling" else None,
        in_lab_prep=False if workflow == "library_prep" else None,
    )

    form = forms.SelectSamplesForm.create_workflow_form(workflow, context=context, selected_libraries=libraries)
    return form.make_response(libraries=libraries)


@libraries_htmx.route("<int:library_id>/get_flex_table", methods=["GET"])
@db_session(db)
@login_required
def get_flex_table(library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    df = db.get_library_samples_df(library.id)

    df = df[["sample_name", "flex_barcode"]]

    columns = []
    for i, col in enumerate(df.columns):
        if col == "flex_barcode":
            width = 100
        else:
            width = 300
        columns.append(
            SpreadSheetColumn(
                string.ascii_uppercase[i], col,
                col.replace("_", " ").title().replace("Id", "ID"),
                "text", width, var_type=str
            )
        )

    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id="flex-table"
        )
    )


@libraries_htmx.route("<int:library_id>/get_hto_table", methods=["GET"])
@db_session(db)
@login_required
def get_hto_table(library_id: int):
    if (library := db.get_library(library_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and not library.owner_id != current_user.id:
        affiliation = db.get_user_library_access_type(user_id=current_user.id, library_id=library.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    df = db.get_library_samples_df(library.id)

    df = df[["sample_name", "cmo_sequence", "cmo_pattern", "cmo_read"]]

    columns = []
    for i, col in enumerate(df.columns):
        columns.append(
            SpreadSheetColumn(
                string.ascii_uppercase[i], col,
                col.replace("_", " ").title().replace("Id", "ID").replace("Cmo", "CMO"),
                "text", 300, var_type=str
            )
        )

    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id="flex-table"
        )
    )