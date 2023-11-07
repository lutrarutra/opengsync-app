from io import StringIO
from typing import Optional, Any, TYPE_CHECKING

from flask import Blueprint, redirect, url_for, render_template, flash, request, abort, Response
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename

import pandas as pd

from .... import db, logger, forms, tools, models, PAGE_LIMIT
from ....core import DBSession
from ....categories import UserRole, HttpResponse

if TYPE_CHECKING:
    current_user: models.User = None
else:
    from flask_login import current_user

samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/api/samples/")


@samples_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    descending = order == "desc"
    offset = PAGE_LIMIT * page

    if sort_by not in models.Sample.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    samples: list[models.Sample] = []
    context = {}
    if (project_id := request.args.get("project_id", None)) is not None:
        template = "components/tables/project-sample.html"
        try:
            project_id = int(project_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        with DBSession(db.db_handler) as session:
            if (project := session.get_project(project_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            samples, n_pages = session.get_samples(
                limit=PAGE_LIMIT, offset=offset, project_id=project_id, sort_by=sort_by, descending=descending
            )
            context["project"] = project

    elif (library_id := request.args.get("library_id", None)) is not None:
        template = "components/tables/library-sample.html"
        try:
            library_id = int(library_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (library := session.get_library(library_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            samples, n_pages = session.get_samples(
                limit=PAGE_LIMIT, offset=offset, library_id=library_id, sort_by=sort_by, descending=descending
            )
            for sample in samples:
                sample.indices = session.get_sample_indices_from_library(sample.id, library.id)
            context["library"] = library

    elif (seq_request_id := request.args.get("seq_request_id", None)) is not None:
        template = "components/tables/seq_request-sample.html"
        try:
            seq_request_id = int(seq_request_id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        
        with DBSession(db.db_handler) as session:
            if (seq_request := session.get_seq_request(seq_request_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            samples, n_pages = session.get_samples(
                limit=PAGE_LIMIT, offset=offset, seq_request_id=seq_request_id, sort_by=sort_by, descending=descending
            )
            context["seq_request"] = seq_request
    else:
        template = "components/tables/sample.html"
        with DBSession(db.db_handler) as session:
            if not current_user.is_insider():
                samples, n_pages = session.get_samples(limit=PAGE_LIMIT, offset=offset, project_id=project_id, user_id=current_user.id, sort_by=sort_by, descending=descending)
            else:
                samples, n_pages = session.get_samples(limit=PAGE_LIMIT, offset=offset, project_id=project_id, sort_by=sort_by, descending=descending)
    
    return make_response(
        render_template(
            template, samples=samples,
            n_pages=n_pages, active_page=page,
            current_sort=sort_by, current_sort_order=order,
            index_form=forms.IndexForm(), **context
        ), push_url=False
    )


@samples_htmx.route("<int:sample_id>/delete", methods=["DELETE"])
@login_required
def delete(sample_id: int):
    logger.debug(sample_id)
    if (sample := db.db_handler.get_sample(sample_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    if not sample.is_editable():
        return abort(HttpResponse.FORBIDDEN.value.id)

    db.db_handler.delete_sample(sample_id)

    logger.info(f"Deleted sample {sample.name} (id: {sample.id})")
    flash(f"Deleted sample {sample.name} (id: {sample.id})", "success")

    return make_response(
        redirect=url_for(
            "samples_page.samples_page"
        ),
    )


@samples_htmx.route("download", methods=["GET"])
@login_required
def download():
    file_name = f"{current_user.last_name}_samples.tsv"
    
    if (project_id := request.args.get("project_id", None)) is not None:
        try:
            project_id = int(project_id)
            with DBSession(db.db_handler) as session:
                if (project := session.get_project(project_id)) is None:
                    return abort(HttpResponse.NOT_FOUND.value.id)
                file_name = f"{project.name}_project_samples.tsv"
                samples = project.samples
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)

    elif (library_id := request.args.get("library_id", None)) is not None:
        with DBSession(db.db_handler) as session:
            if (library := session.get_library(library_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
            for sample in library.samples:
                sample.indices = session.get_sample_indices_from_library(sample.id, library.id)
            file_name = f"{library.name}_library_samples.tsv"
            samples = library.samples
    else:
        samples, _ = db.db_handler.get_samples(
            limit=None, user_id=current_user.id
        )

    file_name = secure_filename(file_name)

    df = pd.DataFrame.from_records([sample.to_dict() for sample in samples])
    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={file_name}"}
    )


@samples_htmx.route("<int:sample_id>/edit", methods=["POST"])
@login_required
def edit(sample_id):
    with DBSession(db.db_handler) as session:
        if (sample := session.get_sample(sample_id)) is None:
            return abort(HttpResponse.NOT_FOUND.value.id)

        if not sample.is_editable():
            return abort(HttpResponse.FORBIDDEN.value.id)

    sample_form = forms.SampleForm()
    validated, sample_form = sample_form.custom_validate(
        db_handler=db.db_handler,
        user_id=current_user.id,
        sample_id=sample_id
    )

    if not validated:
        return make_response(
            render_template(
                "forms/sample/sample.html",
                selected_organism=sample.organism,
                sample_form=sample_form, sample=sample
            ), push_url=False
        )

    db.db_handler.update_sample(
        sample_id,
        name=sample_form.name.data,
        organism_tax_id=sample_form.organism.data
    )

    logger.debug(f"Edited {sample}")
    flash("Changes saved succesfully!", "success")

    return make_response(
        redirect=url_for("samples_page.sample_page", sample_id=sample_id),
    )


@samples_htmx.route("query", methods=["POST"])
@login_required
def query():
    field_name = next(iter(request.form.keys()))
    word = request.form.get(field_name)

    if (exclude_library_id := request.args.get("exclude_library_id", None)) is not None:
        try:
            exclude_library_id = int(exclude_library_id)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)

    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    if current_user.role_type == UserRole.CLIENT:
        _user_id = current_user.id
    else:
        _user_id = None
    if exclude_library_id is None:
        results = db.db_handler.query_samples(word, user_id=_user_id)
    else:
        results = db.db_handler.query_samples(
            word, exclude_library_id=exclude_library_id, user_id=_user_id
        )

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )


@samples_htmx.route("table_query", methods=["POST"])
@login_required
def table_query():
    if (word := request.form.get("name", None)) is not None:
        field_name = "name"
    elif (word := request.form.get("id", None)) is not None:
        field_name = "id"
    else:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if word is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    if not current_user.is_insider():
        _user_id = current_user.id
    else:
        _user_id = None
    
    def __get_samples(
        session, word: str | int, field_name: str,
        library_id: Optional[int], project_id: Optional[int]
    ) -> list[models.Sample]:
        samples: list[models.Sample] = []
        if field_name == "name":
            samples = session.query_samples(
                str(word), library_id=library_id,
                project_id=project_id, user_id=_user_id
            )
        elif field_name == "id":
            try:
                _id = int(word)
                if (sample := session.get_sample(_id)) is not None:
                    if _user_id is not None:
                        if sample.owner_id == _user_id:
                            samples = [sample]
            except ValueError:
                pass
        else:
            assert False    # This should never happen

        return samples

    context = {}
    if (project_id := request.args.get("project_id", None)) is not None:
        template = "components/tables/project-sample.html"
        try:
            project_id = int(project_id)
            with DBSession(db.db_handler) as session:
                if (project := session.get_project(project_id)) is None:
                    return abort(HttpResponse.NOT_FOUND.value.id)
                    
                samples = __get_samples(session, word, field_name, library_id=None, project_id=project_id)
                context["project"] = project
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)

    elif (library_id := request.args.get("library_id", None)) is not None:
        template = "components/tables/library-sample.html"
        try:
            library_id = int(library_id)
            with DBSession(db.db_handler) as session:
                if (library := session.get_library(library_id)) is None:
                    return abort(HttpResponse.NOT_FOUND.value.id)
                
                samples = __get_samples(session, word, field_name, library_id=library_id, project_id=None)
                for sample in samples:
                    sample.indices = session.get_sample_indices_from_library(sample.id, library.id)

                context["library"] = library
                context["index_form"] = forms.IndexForm()

        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)

    else:
        template = "components/tables/sample.html"
        with DBSession(db.db_handler) as session:
            samples = __get_samples(session, word, field_name, library_id=None, project_id=None) 

    return make_response(
        render_template(
            template,
            current_query=word,
            samples=samples,
            field_name=field_name,
            **context
        ), push_url=False
    )