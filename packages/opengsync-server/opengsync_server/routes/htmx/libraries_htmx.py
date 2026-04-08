import json

import pandas as pd

from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response
import sqlalchemy as sa
from sqlalchemy import orm

from opengsync_db import models
from opengsync_db.categories import LibraryType, LibraryStatus, ServiceType, MUXType, AccessType, SampleStatus, PoolStatus
from opengsync_server.routes.pages.libraries_page import library

from ... import db, forms, logic
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
def render_feature_table(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.libraries.get_access_type(library=library, user=current_user) < AccessType.VIEW:
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

    spreadsheet = StaticSpreadSheet(df, columns=columns)
    return make_response(render_template("components/itable.html", columns=columns, spreadsheet=spreadsheet))


@wrappers.htmx_route(libraries_htmx, db=db)
def get_crispr_guides(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    if db.libraries.get_access_type(library=library, user=current_user) < AccessType.VIEW:
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
    
    access_type = db.libraries.get_access_type(library=library, user=current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()

    if not library.read_qualities:
        raise exceptions.BadRequestException("No read quality data available for this library.")
    
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
    return make_response(render_template(**logic.library.get_browse_context(current_user, request, workflow=workflow, page=page)))

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
    
    df = db.pd.query(
        sa.select(
            models.Library.id,
            models.Library.service_type_id.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status_id.label("status")
        ).where(
            models.Library.status_id.in_([LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED]),
        )
    )
    
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
    
    df = db.pd.query(
        sa.select(
            models.Library.id,
            models.Library.seq_request_id,
            models.Library.service_type_id.label("service_type"),
            models.Library.name.label("library_name"),
            models.Library.status_id.label("status")
        ).where(
            models.Library.status_id.in_([LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED]),
            models.Library.service_type_id == service_type.id,
        ).order_by(models.Library.seq_request_id, models.Library.id)
    )

    data = {
        "seq_request": [],
        "num_waiting_samples": [],
        "num_preparing_libraries": [],
        "num_pooled_libraries": [],
        "library_type_counts": [],
        "num_waiting_libraries": [],
        "num_waiting_pools": [],
    }

    for (seq_request_id,), _df in df.groupby(["seq_request_id"]):
        seq_request = db.seq_requests.get(
            seq_request_id,  # type: ignore
            options=[
                orm.selectinload(models.SeqRequest.samples),
                orm.selectinload(models.SeqRequest.libraries),
                orm.selectinload(models.SeqRequest.pools),
            ]  # type: ignore
        )
        if seq_request is None:
            raise exceptions.NotFoundException()
        

        data["seq_request"].append(seq_request)
        data["num_waiting_samples"].append(sum([s.status == SampleStatus.WAITING_DELIVERY for s in seq_request.samples]))
        data["num_preparing_libraries"].append(sum([ls.status == LibraryStatus.PREPARING for ls in seq_request.libraries]))
        data["num_pooled_libraries"].append(sum([ls.status in [LibraryStatus.POOLED, LibraryStatus.SEQUENCED, LibraryStatus.SHARED, LibraryStatus.ARCHIVED] for ls in seq_request.libraries]))
        data["library_type_counts"].append(seq_request.library_type_counts)
        data["num_waiting_libraries"].append(sum([ls.status == LibraryStatus.ACCEPTED for ls in seq_request.libraries]))
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

@wrappers.htmx_route(libraries_htmx, db=db, methods=["GET", "POST"])
def edit_properties(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if request.method == "GET":
        return forms.LibraryPropertiesForm(library=library).make_response()
    
    return forms.LibraryPropertiesForm(
        library=library, formdata=request.form,
    ).process_request()


@wrappers.htmx_route(libraries_htmx, db=db, methods=["GET", "POST"])
def edit_features(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.EDIT:
        raise exceptions.NoPermissionsException()
    if library.status != LibraryStatus.DRAFT and access_type < AccessType.INSIDER:
        raise exceptions.NoPermissionsException()
    
    if library.type not in [LibraryType.TENX_ANTIBODY_CAPTURE, LibraryType.TENX_SC_ABC_FLEX]:
        raise exceptions.BadRequestException("Only 10x Antibody Capture and 10x SC ABC Flex libraries have features that can be edited.")
    
    if request.method == "GET":
        return forms.LibraryFeaturesForm(library=library).make_response()
    
    return forms.LibraryFeaturesForm(
        library=library, formdata=request.form,
    ).process_request()