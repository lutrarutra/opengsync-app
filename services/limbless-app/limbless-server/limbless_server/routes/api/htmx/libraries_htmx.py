from typing import Optional, TYPE_CHECKING

from flask import Blueprint, render_template, request, abort
from flask_htmx import make_response
from flask_login import login_required

from limbless_db import models, DBSession, PAGE_LIMIT, DBHandler
from limbless_db.categories import HTTPResponse
from .... import db, forms, logger

if TYPE_CHECKING:
    current_user: models.User = None    # type: ignore
else:
    from flask_login import current_user

libraries_htmx = Blueprint("libraries_htmx", __name__, url_prefix="/api/hmtx/libraries/")


@libraries_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Library.sortable_fields:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    libraries: list[models.Library] = []
    context = {}

    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-library.html"
        try:
            seq_request_id = int(seq_request_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            libraries, n_pages = session.get_libraries(
                offset=offset, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending
            )
            context["seq_request"] = seq_request
    elif (experiment_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-library.html"
        try:
            experiment_id = int(experiment_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            libraries, n_pages = session.get_libraries(
                offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending
            )
            context["experiment"] = experiment
    elif (sample_id := request.args.get("sample_id", None)) is not None:
        template = "components/tables/sample-library.html"
        try:
            sample_id = int(sample_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (sample := session.get_sample(sample_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            libraries, n_pages = session.get_libraries(
                offset=offset, sample_id=sample_id, sort_by=sort_by, descending=descending
            )
            context["sample"] = sample
    elif (experiment_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-library.html"
        try:
            experiment_id = int(experiment_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            libraries, n_pages = session.get_libraries(
                offset=offset, experiment_id=experiment_id, sort_by=sort_by, descending=descending
            )
            context["experiment"] = experiment
    elif (pool_id := request.args.get("pool_id", None)) is not None:
        template = "components/tables/pool-library.html"
        try:
            pool_id = int(pool_id)
        except (ValueError, TypeError):
            return abort(HTTPResponse.BAD_REQUEST.id)
        
        with DBSession(db) as session:
            if (pool := session.get_pool(pool_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
            libraries, n_pages = session.get_libraries(
                offset=offset, pool_id=pool_id, sort_by=sort_by, descending=descending
            )
            context["pool"] = pool
    else:
        template = "components/tables/library.html"
        with DBSession(db) as session:
            if not current_user.is_insider():
                libraries, n_pages = session.get_libraries(offset=offset, user_id=current_user.id, sort_by=sort_by, descending=descending)
            else:
                libraries, n_pages = session.get_libraries(offset=offset, user_id=None, sort_by=sort_by, descending=descending)

    return make_response(
        render_template(
            template, libraries=libraries,
            libraries_n_pages=n_pages, libraries_active_page=page,
            libraries_current_sort=sort_by, libraries_current_sort_order=order,
            **context
        ), push_url=False
    )


@libraries_htmx.route("edit/<int:library_id>", methods=["POST"])
@login_required
def edit(library_id):
    with DBSession(db) as session:
        if (library := session.get_library(library_id)) is None:
            return abort(HTTPResponse.NOT_FOUND.id)
        if not library.is_editable() and not current_user.is_insider():
            return abort(HTTPResponse.FORBIDDEN.id)

    return forms.models.LibraryForm(request.form).process_request(
        library=library
    )


@libraries_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.args.keys()))
    if (word := request.form.get(field_name, default="")) is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    if not current_user.is_insider():
        results = db.query_libraries(word, current_user.id)
    else:
        results = db.query_libraries(word)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results, field_name=field_name,
        ), push_url=False
    )


@libraries_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name")) is not None:
        field_name = "name"
    elif (word := request.form.get("id")) is not None:
        field_name = "id"
    else:
        return abort(HTTPResponse.BAD_REQUEST.id)
    
    if word is None:
        return abort(HTTPResponse.BAD_REQUEST.id)

    def __get_libraries(
        session: DBHandler, word: str | int, field_name: str, sample_id: Optional[int] = None,
        seq_request_id: Optional[int] = None, experiment_id: Optional[int] = None, user_id: Optional[int] = None
    ) -> list[models.Library]:
        libraries: list[models.Library] = []
        if field_name == "name":
            libraries = session.query_libraries(
                str(word), user_id=user_id, seq_request_id=seq_request_id,
                experiment_id=experiment_id, sample_id=sample_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
                if (library := session.get_library(_id)) is not None:
                    if seq_request_id is not None:
                        if seq_request_id in [sr.id for sr in library.seq_requests]:
                            libraries = [library]
                    elif experiment_id is not None:
                        if experiment_id in [e.id for e in library.experiments]:
                            libraries = [library]
                    elif sample_id is not None:
                        if sample_id in [s.id for s in library.samples]:
                            libraries = [library]
                    elif user_id is not None:
                        if library.owner_id == user_id:
                            libraries = [library]
                    else:
                        libraries = [library]
            except ValueError:
                pass
        else:
            assert False    # This should never happen

        return libraries
    
    context = {}
    if (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-library.html"
        try:
            seq_request_id = int(seq_request_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with DBSession(db) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
                
            libraries = __get_libraries(session, word, field_name, seq_request_id=seq_request_id)
        context["seq_request"] = seq_request
    elif (seq_request_id := request.args.get("experiment_id", None)) is not None:
        template = "components/tables/experiment-library.html"
        try:
            experiment_id = int(seq_request_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with DBSession(db) as session:
            if (experiment := session.get_experiment(experiment_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
                
            libraries = __get_libraries(session, word, field_name, experiment_id=experiment_id)
            context["experiment"] = experiment
    elif (sample_id := request.args.get("sample_id", None)) is not None:
        template = "components/tables/sample-library.html"
        try:
            sample_id = int(sample_id)
        except ValueError:
            return abort(HTTPResponse.BAD_REQUEST.id)
        with DBSession(db) as session:
            if (sample := session.get_sample(sample_id)) is None:
                return abort(HTTPResponse.NOT_FOUND.id)
                
            libraries = __get_libraries(session, word, field_name, sample_id=sample_id)
            context["sample"] = sample
    else:
        template = "components/tables/library.html"

        with DBSession(db) as session:
            if not current_user.is_insider():
                user_id = current_user.id
            else:
                user_id = None
            libraries = __get_libraries(session, word, field_name, user_id=user_id)

    return make_response(
        render_template(
            template,
            current_query=word, field_name=field_name,
            libraries=libraries, **context
        ), push_url=False
    )