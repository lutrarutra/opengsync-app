import json

import pandas as pd

from flask import Blueprint, render_template, request, flash, url_for
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT
from opengsync_db.categories import LibraryType, LibraryStatus, AssayType, MUXType, AccessType, DataPathType, SampleStatus

from ... import db, forms, logger  # noqa
from ...core import wrappers, exceptions
from ...tools.spread_sheet_components import TextColumn

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/htmx/libraries/")


@wrappers.htmx_route(libraries_htmx, db=db)
def get(current_user: models.User, page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

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
    
    libraries, n_pages = db.libraries.find(
        page=page,
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


@wrappers.htmx_route(libraries_htmx, db=db, methods=["POST"])
def edit(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    if not library.is_editable() and not current_user.is_insider():
        raise exceptions.NoPermissionsException()

    return forms.models.LibraryForm(library=library, formdata=request.form).process_request()


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
def table_query(current_user: models.User):
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    elif (word := request.args.get("owner_id")) is not None:
        field_name = "owner_id"
    else:
        raise exceptions.BadRequestException()
    
    user_id = current_user.id if not current_user.is_insider() else None

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
        libraries = db.libraries.query(name=word, user_id=user_id, status_in=status_in, type_in=type_in)
    elif field_name == "id":
        try:
            _id = int(word)
            if (library := db.libraries.get(_id)) is not None:
                libraries = [library]
                if user_id is not None:
                    if library.owner_id != user_id:
                        libraries = []
                if status_in is not None and library.status not in status_in:
                    libraries = []
                if type_in is not None and library.type not in type_in:
                    libraries = []
        except ValueError:
            pass
    elif field_name == "owner_id":
        libraries = db.libraries.query(owner=word, user_id=user_id, status_in=status_in, type_in=type_in)

    return make_response(
        render_template(
            "components/tables/library.html",
            current_query=word, active_query_field=field_name,
            libraries=libraries, type_in=type_in, status_in=status_in
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_samples(current_user: models.User, library_id: int, page: int = 0):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(status_in) == 0:
            status_in = None
    
    samples: list[models.Sample] = []
    
    samples, n_pages = db.samples.find(
        page=page, library_id=library_id, sort_by=sort_by, descending=descending,
        status_in=status_in
    )

    return make_response(
        render_template(
            "components/tables/library-sample.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order, library=library,
            status_in=status_in
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_data_paths(current_user: models.User, library_id: int, page: int = 0):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()

    access_type = db.libraries.get_access_type(library, current_user)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = page * PAGE_LIMIT

    if (type_in := request.args.get("type_id_in")) is not None:
        type_in = json.loads(type_in)
        try:
            type_in = [DataPathType.get(int(t)) for t in type_in]
        except ValueError:
            raise exceptions.BadRequestException()
    
        if len(type_in) == 0:
            type_in = None

    data_paths, n_pages = db.data_paths.find(offset=offset, library_id=library_id, type_in=type_in, sort_by=sort_by, descending=descending, count_pages=True)

    return make_response(
        render_template(
            "components/tables/library-data_path.html", data_paths=data_paths,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            library=library, type_in=type_in
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def reads_tab(current_user: models.User, library_id: int):
    if (library := db.libraries.get(library_id)) is None:
        raise exceptions.NotFoundException()
    
    access_type = db.libraries.get_access_type(user=current_user, library=library)
    if access_type < AccessType.VIEW:
        raise exceptions.NoPermissionsException()
    
    return make_response(render_template("components/library-reads.html", library=library))


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

    return make_response(
        render_template(
            "components/itable.html", columns=columns,
            spreadsheet_data=df.replace(pd.NA, "").values.tolist(),
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_todo_libraries(current_user: models.User):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    libraries, _ = db.libraries.find(
        status_in=[LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED],
        limit=512
    )

    data = {
        "assay_type": [],
        "library_name": [],
        "status": [],
    }

    for library in libraries:
        data["assay_type"].append(library.assay_type)
        data["library_name"].append(library.name)
        data["status"].append(library.status)

    df = pd.DataFrame(data)
    
    return make_response(
        render_template(
            "components/dashboard/todo-assays-lists.html", df=df
        )
    )


@wrappers.htmx_route(libraries_htmx, db=db)
def get_assay_type_todo_libraries(current_user: models.User, assay_type_id: int):
    if not current_user.is_insider():
        raise exceptions.NoPermissionsException()
    
    try:
        assay_type = AssayType.get(assay_type_id)
    except ValueError:
        raise exceptions.BadRequestException()

    libraries, _ = db.libraries.find(
        status_in=[LibraryStatus.ACCEPTED, LibraryStatus.PREPARING, LibraryStatus.STORED],
        assay_type=assay_type, limit=512
    )

    data = {
        "library_name": [],
        "library_type": [],
        "status": [],
        "seq_request": [],
        "sample_name": []
    }

    for library in libraries:
        data["library_name"].append(library.name)
        data["library_type"].append(library.type)
        data["seq_request"].append(library.seq_request)
        data["status"].append(library.status)
        data["sample_name"].append(library.sample_name)

    df = pd.DataFrame(data)

    return make_response(
        render_template(
            "components/assay_type-todo-list.html",
            assay_type=assay_type, df=df
        )
    )