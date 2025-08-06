import json
from typing import Optional, TYPE_CHECKING

from flask import Blueprint, url_for, render_template, flash, request, abort
from flask_htmx import make_response

from opengsync_db import models, PAGE_LIMIT, DBHandler
from opengsync_db.categories import HTTPResponse, UserRole, SampleStatus
from .... import db, logger, forms, htmx_route

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/api/hmtx/samples/")


@htmx_route(samples_htmx, db=db)
def get(page: int = 0):
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Sample.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None
    
    samples: list[models.Sample] = []

    samples, n_pages = db.get_samples(
        offset=offset,
        user_id=current_user.id if not current_user.is_insider() else None,
        sort_by=sort_by, descending=descending, status_in=status_in, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/sample.html", samples=samples,
            n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            status_in=status_in
        )
    )


@htmx_route(samples_htmx, db=db, methods=["DELETE"])
def delete(sample_id: int):
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not sample.is_editable():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if not current_user.is_insider() and sample.owner_id != current_user.id:
        affiliation = db.get_user_sample_access_type(user_id=current_user.id, sample_id=sample.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)

    db.delete_sample(sample_id)

    logger.info(f"Deleted sample {sample.name} (id: {sample.id})")
    flash(f"Deleted sample {sample.name} (id: {sample.id})", "success")

    return make_response(
        redirect=url_for(
            "samples_page.samples"
        ),
    )


@htmx_route(samples_htmx, db=db, methods=["GET", "POST"])
def edit(sample_id: int):
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    if not current_user.is_insider() and sample.owner_id != current_user.id:
        affiliation = db.get_user_sample_access_type(user_id=current_user.id, sample_id=sample.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
        
    if request.method == "GET":
        return forms.models.SampleForm(sample).make_response()
    
    return forms.models.SampleForm(sample, request.form).process_request()


@htmx_route(samples_htmx, db=db, methods=["POST"])
def query():
    field_name = next(iter(request.form.keys()))
    if (word := request.form.get(field_name)) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if current_user.role == UserRole.CLIENT:
        _user_id = current_user.id
    else:
        _user_id = None

    results = db.query_samples(word, user_id=_user_id)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        )
    )


@htmx_route(samples_htmx, db=db)
def table_query():
    if (word := request.args.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.args.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if not current_user.is_insider():
        _user_id = current_user.id
    else:
        _user_id = None
    
    def __get_samples(
        session: DBHandler, word: str | int, field_name: str,
        seq_request_id: Optional[int], project_id: Optional[int],
    ) -> list[models.Sample]:
        samples: list[models.Sample] = []
        if field_name == "name":
            samples = session.query_samples(
                str(word),
                project_id=project_id, user_id=_user_id,
                seq_request_id=seq_request_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
            except ValueError:
                return []
            if (sample := session.get_sample(_id)) is not None:
                samples = [sample]
                if _user_id is not None:
                    if sample.owner_id == _user_id:
                        samples = [sample]

                if project_id is not None:
                    if sample.project_id == project_id:
                        samples = [sample]
                    else:
                        samples = []
                
                if seq_request_id is not None:
                    if session.is_sample_in_seq_request(sample.id, seq_request_id):
                        samples = [sample]
                    else:
                        samples = []
                
        else:
            assert False    # This should never happen

        return samples

    context = {}
    if (project_id := request.args.get("project_id", None)) is not None:
        template = "components/tables/project-sample.html"
        try:
            project_id = int(project_id)

        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (project := db.get_project(project_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
            
        samples = __get_samples(db, word, field_name, project_id=project_id, seq_request_id=None)
        context["project"] = project
    
    elif (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-sample.html"
        try:
            seq_request_id = int(seq_request_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        if (seq_request := db.get_seq_request(seq_request_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        
        samples = __get_samples(db, word, field_name, project_id=None, seq_request_id=seq_request_id)
        context["seq_request"] = seq_request
    else:
        template = "components/tables/sample.html"
        samples = __get_samples(db, word, field_name, project_id=None, seq_request_id=None)

    return make_response(
        render_template(
            template,
            current_query=word,
            samples=samples,
            field_name=field_name,
            **context
        )
    )
    

@htmx_route(samples_htmx, db=db)
def get_libraries(sample_id: int):
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    if not current_user.is_insider() and sample.owner_id != current_user.id:
        affiliation = db.get_user_sample_access_type(user_id=current_user.id, sample_id=sample.id)
        if affiliation is None:
            return abort(HTTPResponse.FORBIDDEN.id)
    
    libraries, n_pages = db.get_libraries(
        sample_id=sample_id, count_pages=True
    )
    
    return make_response(
        render_template(
            "components/tables/sample-library.html",
            sample=sample, libraries=libraries,
            n_pages=n_pages
        )
    )


@htmx_route(samples_htmx, db=db)
def get_plate(sample_id: int):
    raise NotImplementedError()
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (sample := db.get_sample(sample_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)
    
    return make_response(
        render_template(
            "components/plate.html", plate=sample.plate,
            sample=sample
        )
    )


@htmx_route(samples_htmx, db=db)
def browse(workflow: str, page: int = 0):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "desc")
    descending = sort_order == "desc"
    offset = PAGE_LIMIT * page

    context = {}

    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
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
        
    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    samples, n_pages = db.get_samples(
        seq_request_id=seq_request_id, status_in=status_in, offset=offset, sort_by=sort_by, descending=descending,
        pool_id=pool_id, count_pages=True
    )
    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, n_pages=n_pages, active_page=page,
            sort_by=sort_by, sort_order=sort_order,
            workflow=workflow, context=context, status_in=status_in
        )
    )


@htmx_route(samples_htmx, db=db)
def browse_query(workflow: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (word := request.args.get("name")) is not None:
        field_name = "name"
    elif (word := request.args.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            context["seq_request_id"] = seq_request_id
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

    samples: list[models.Sample] = []

    if field_name == "name":
        samples = db.query_samples(word=word, seq_request_id=seq_request_id, pool_id=pool_id)
    elif field_name == "id":
        try:
            sample_id = int(word)
            if (sample := db.get_sample(sample_id)) is not None:
                samples.append(sample)
        except ValueError:
            pass
        
    context["workflow"] = workflow
    return make_response(
        render_template(
            "components/tables/select-samples.html",
            samples=samples, acitve_query_field=field_name, active_query_word=word,
            workflow=workflow, context=context
        )
    )


@htmx_route(samples_htmx, db=db)
def select_all(workflow: str):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id")) is not None:
        try:
            seq_request_id = int(seq_request_id)
            if (seq_request := db.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            context["seq_request"] = seq_request
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)

    if (status_in := request.args.get("status_id_in")) is not None:
        status_in = json.loads(status_in)
        try:
            status_in = [SampleStatus.get(int(status)) for status in status_in]
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
    
        if len(status_in) == 0:
            status_in = None

    samples, _ = db.get_samples(
        seq_request_id=seq_request_id, status_in=status_in, limit=None
    )

    form = forms.SelectSamplesForm.create_workflow_form(workflow, context=context, selected_samples=samples)
    return form.make_response(samples=samples)
