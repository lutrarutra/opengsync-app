import json

import pandas as pd

from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import LibraryType, LibraryStatus, ServiceType, MUXType, AccessType, DataPathType, SampleStatus, PoolStatus

from ... import db, forms, logger, logic
from ...core import wrappers, exceptions
from ...tools.spread_sheet_components import TextColumn
from ...tools import StaticSpreadSheet

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/htmx/libraries/")


@wrappers.htmx_route(libraries_htmx, db=db)
def get(current_user: models.User):
    return make_response(render_template(**logic.library.get_table_context(current_user, request)))


@wrappers.htmx_route(libraries_htmx, db=db)
def search(current_user: models.User):
    context = logic.library.get_search_context(current_user=current_user, request=request)
    return make_response(render_template(**context))


@wrappers.htmx_route(libraries_htmx, db=db, methods=["POST"])
def query(current_user: models.User):
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        raise exceptions.BadRequestException()

    if not current_user.is_insider():
        results = db.libraries.query(name=word, user_id=current_user.id)
    else:
        results = db.libraries.query(name=word)

    return make_response(
        render_template(
            "components/search/library.html",
            results=results, field_name=field_name,
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_features(current_user: models.User, library_id: int, page: int = 0):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    features, n_pages = db.features.find(offset=offset, library_id=library_id, sort_by=sort_by, descending=descending, count_pages=True)
    
    return make_response(
        render_template(
            "components/tables/library-feature.html",
            features=features, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, library=library
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def render_feature_table(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    df = db.pd.get_library_features(library_id=library.id)
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
            TextColumn(
                col, col.replace("_", " ").title().replace("Id", "ID"),
                width, max_length=1000
            )
        )
    
    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
            table_id=f"library-feature-table-{library_id}"
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_spatial_annotation(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    if library.type not in LibraryType.get_spatial_library_types():
        raise exceptions.BadRequestException()
    
    return make_response(render_template("components/library-spatial-annotation.html", library=library))


@wrappers.htmx_route(libraries_htmx, db=db)
def get_crispr_guides(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if not current_user.is_insider() and library.owner_id != current_user.id:
        raise exceptions.NoPermissionsException()
    
    if library.type != LibraryType.PARSE_SC_CRISPR:
        raise exceptions.BadRequestException()
    
    df = pd.DataFrame(library.properties.get("crispr_guides", [])) if library.properties else pd.DataFrame(columns=["guide_name", "target_gene", "prefix", "guide_sequence", "suffix"])
    df = df[["guide_name", "target_gene", "prefix", "guide_sequence", "suffix"]]
    
    columns = []
    for col in df.columns:
        columns.append(TextColumn(col, col.replace("_", " ").title(), 200, max_length=1000))

    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def reads_tab(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    library_stats_per_lane = db.pd.get_library_stats(library_id, per_lane=True)
    library_stats_average = db.pd.get_library_stats(library_id, per_lane=False)

    per_lane_columns = []
    for col in library_stats_per_lane.columns:
        per_lane_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    average_columns = []
    for col in library_stats_average.columns:
        average_columns.append(TextColumn(col, col.replace("_", " ").title(), {"lane": 50}.get(col, 150), max_length=1000))

    per_lane_stats_ss = StaticSpreadSheet(df=library_stats_per_lane, columns=per_lane_columns, id=f"library-{library_id}-reads-per-lane")
    average_stats_ss = StaticSpreadSheet(df=library_stats_average, columns=average_columns, id=f"library-{library_id}-reads-average")
    
    return make_response(render_template(
        "components/library-reads.html", library=library,
        per_lane_stats_ss=per_lane_stats_ss, average_stats_ss=average_stats_ss
    ))


@wrappers.htmx_route(libraries_htmx, db=db)
def browse(current_user: models.User, workflow: str, page: int = 0):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    context = {}

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
            
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.experiments.get(experiment_id)) is None:
                raise exceptions.NotFoundException()
            context["experiment_id"] = experiment.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request_id"] = seq_request.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool_id"] = pool.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (lab_prep_id := request.args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
            if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
                raise exceptions.NotFoundException()
            context["lab_prep_id"] = lab_prep.id
        except ValueError:
            raise exceptions.BadRequestException()
    
    libraries, n_pages = db.libraries.find(
        sort_by=sort_by, descending=descending, page=page,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        type_in=type_in,
        status_in=status_in,
        pooled=False if workflow == "library_prep" else None,
        pool_id=pool_id if workflow != "select_pool_libraries" else None,
        lab_prep_id=lab_prep_id if workflow != "library_prep" else None,
        in_lab_prep=False if workflow == "library_prep" else None,
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


@wrappers.htmx_route(libraries_htmx, db=db)
def browse_query(current_user: models.User, workflow: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("owner_id")) is not None:
        field_name = "owner_id"
    else:
        raise exceptions.BadRequestException()
    
    context = {}
    
    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.experiments.get(experiment_id)) is None:
                raise exceptions.NotFoundException()
            context["experiment_id"] = experiment.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request_id"] = seq_request.id
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool_id"] = pool.id
        except ValueError:
            raise exceptions.BadRequestException()
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    libraries: list[models.Library] = []
    if field_name == "name":
        libraries = db.libraries.query(
            name=word, status_in=status_in, type_in=type_in, experiment_id=experiment_id,
            seq_request_id=seq_request_id, pool_id=pool_id,
        )
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.libraries.get(_id)) is not None:
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
        libraries = db.libraries.query(
            owner=word, status_in=status_in, type_in=type_in, experiment_id=experiment_id,
            seq_request_id=seq_request_id, pool_id=pool_id,
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


@wrappers.htmx_route(libraries_htmx, db=db)
def select_all(current_user: models.User, workflow: str):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    context = {}
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [LibraryStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
            
    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [LibraryType.get(int(type_)) for type_ in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    if (experiment_id := request.args.get("experiment_id")) is not None:
        try:
            experiment_id = int(experiment_id)
            if (experiment := db.experiments.get(experiment_id)) is None:
                raise exceptions.NotFoundException()
            context["experiment"] = experiment
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.seq_requests.get(seq_request_id)) is None:
                raise exceptions.NotFoundException()
            context["seq_request"] = seq_request
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (pool_id := request.args.get("pool_id")) is not None:
        try:
            pool_id = int(pool_id)
            if (pool := db.pools.get(pool_id)) is None:
                raise exceptions.NotFoundException()
            context["pool"] = pool
        except ValueError:
            raise exceptions.BadRequestException()
        
    if (lab_prep_id := request.args.get("lab_prep_id")) is not None:
        try:
            lab_prep_id = int(lab_prep_id)
            if (lab_prep := db.lab_preps.get(lab_prep_id)) is None:
                raise exceptions.NotFoundException()
            context["lab_prep"] = lab_prep
        except ValueError:
            raise exceptions.BadRequestException()

    libraries, _ = db.libraries.find(
        seq_request_id=seq_request_id, status_in=status_in, type_in=type_in, experiment_id=experiment_id, limit=None,
        pool_id=pool_id, in_lab_prep=False if workflow == "library_prep" else None,
    )

    form = forms.SelectSamplesForm.create_workflow_form(workflow, context=context, selected_libraries=libraries)
    return form.make_response(libraries=libraries)


@wrappers.htmx_route(libraries_htmx, db=db, methods=["DELETE"])
def remove_sample(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()

    if (sample_id := request.args.get("sample_id")) is None:
        raise exceptions.BadRequestException()
    try:
        sample_id = int(sample_id)
    except ValueError:
        raise exceptions.BadRequestException()
    
    if (sample := db.samples.get(sample_id)) is None:
        raise exceptions.NotFoundException()
    
    db.links.unlink_sample_library(sample_id=sample.id, library_id=library.id)

    flash("Sample removed from library successfully.", "success")
    return make_response(redirect=url_for("libraries_page.library", library_id=library.id))


@wrappers.htmx_route(libraries_htmx, db=db)
def get_mux_table(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    if library.mux_type is None:
        raise exceptions.BadRequestException()

    mux_data = {
        "sample_name": [],
        "barcode": [],
    }

    if library.mux_type == MUXType.TENX_OLIGO:
        mux_data["read"] = []
        mux_data["pattern"] = []

    for link in library.sample_links:
        mux_data["sample_name"].append(link.sample.name)
        if link.mux is not None:
            mux_data["barcode"].append(link.mux.get("barcode"))
            if library.mux_type == MUXType.TENX_OLIGO:
                mux_data["read"].append(link.mux.get("read", ""))
                mux_data["pattern"].append(link.mux.get("pattern", ""))
        else:
            mux_data["barcode"].append(None)
            if library.mux_type == MUXType.TENX_OLIGO:
                mux_data["read"].append("")
                mux_data["pattern"].append("")
                
    df = pd.DataFrame(mux_data)
    columns = []
    for i, col in enumerate(df.columns):
        columns.append(
            TextColumn(
                col,
                col.replace("_", " ").title().replace("Id", "ID").replace("Cmo", "CMO"),
                {
                    "sample_name": 300,
                    "barcode": 200,
                    "read": 80,
                    "pattern": 200
                }.get(col, 100),
                max_length=1000
            )
        )

    spreadsheet = StaticSpreadSheet(df, columns=columns)

    return make_response(render_template("components/itable.html", columns=columns, spreadsheet=spreadsheet))


@wrappers.htmx_route(libraries_htmx, db=db)
def get_todo_libraries(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    libraries, _ = db.libraries.find(
        status_in=[LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED],
        limit=512
    )

    data = {
        "service_type": [],
        "library_name": [],
        "status": [],
    }

    for library in libraries:
        data["service_type"].append(library.service_type)
        data["library_name"].append(library.name)
        data["status"].append(library.status)

    df = pd.DataFrame(data)
    
    return make_response(
        render_template(
            "components/dashboard/todo-assays-lists.html", df=df
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_service_type_todo_libraries(current_user: models.User, service_type_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    try:
        service_type = ServiceType.get(service_type_id)
    except ValueError:
        raise exceptions.BadRequestException()

    libraries, _ = db.libraries.find(
        status_in=[LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED],
        service_type=service_type, limit=512
    )

    seq_requests: set[models.SeqRequest] = set()
    for library in libraries:
        seq_requests.add(library.seq_request)

    data = {
        "seq_request": [],
        "num_waiting_samples": [],
        "num_preparing_libraries": [],
        "num_pooled_libraries": [],
        "library_type_counts": [],
        "num_waiting_libraries": [],
        "num_waiting_pools": [],
    }

    for seq_request in seq_requests:
        data["seq_request"].append(seq_request)
        data["num_waiting_samples"].append(sum([s.status == SampleStatus.WAITING_DELIVERY for s in seq_request.samples]))
        data["num_preparing_libraries"].append(sum([l.status == LibraryStatus.PREPARING for l in seq_request.libraries]))
        data["num_pooled_libraries"].append(sum([l.status in [LibraryStatus.POOLED, LibraryStatus.SEQUENCED, LibraryStatus.SHARED, LibraryStatus.ARCHIVED] for l in seq_request.libraries]))
        data["library_type_counts"].append(seq_request.library_type_counts)
        data["num_waiting_libraries"].append(sum([l.status == LibraryStatus.ACCEPTED for l in seq_request.libraries]))
        data["num_waiting_pools"].append(sum([p.status == PoolStatus.ACCEPTED for p in seq_request.pools]))


    df = pd.DataFrame(data)

    return make_response(
        render_template(
            "components/assay_type-todo-list.html",
            service_type=service_type, df=df
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db, methods=["GET", "POST"])
def edit(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.models.LibraryForm(library=library).make_response()
    
    return forms.models.LibraryForm(
        library=library, formdata=request.form,
    ).process_request()


@wrappers.htmx_route(libraries_htmx, db=db, methods=["GET", "POST"])
def properties(current_user: models.User):
    form = logic.library.get_properties_form(current_user, request)
    if request.method == "GET":
        return form.make_response()
    return form.process_request()