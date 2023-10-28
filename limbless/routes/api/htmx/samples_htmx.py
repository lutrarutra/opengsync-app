from io import StringIO
from typing import Optional

from flask import Blueprint, redirect, url_for, render_template, flash, request, abort, Response
from flask_htmx import make_response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

import pandas as pd

from .... import db, logger, forms, tools, models
from ....core import DBSession
from ....categories import UserRole, HttpResponse

samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/api/samples/")


@samples_htmx.route("get/<int:page>", methods=["GET"])
@login_required
def get(page: int):
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "desc")
    reversed = order == "desc"

    logger.debug(request.args)
    logger.debug(sort_by)

    if sort_by not in models.Sample.sortable_fields:
        return abort(HttpResponse.BAD_REQUEST.value.id)
    
    template = "components/tables/sample.html"
    
    if (project_id := request.args.get("project_id", None)) is not None:
        try:
            project_id = int(project_id)
            if (project := db.db_handler.get_project(project_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        template = "components/tables/project-sample.html"
    else:
        project = None

    if (library_id := request.args.get("library_id", None)) is not None:
        try:
            library_id = int(library_id)
            if (library := db.db_handler.get_library(library_id)) is None:
                return abort(HttpResponse.NOT_FOUND.value.id)
        except (ValueError, TypeError):
            return abort(HttpResponse.BAD_REQUEST.value.id)
        template = "components/tables/library-sample.html"
    else:
        library = None
    
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            samples = session.get_samples(limit=20, project_id=project_id, user_id=current_user.id, sort_by=sort_by, reversed=reversed)
            n_pages = int(session.get_num_samples(user_id=current_user.id, project_id=project_id) / 20)
        else:
            samples = session.get_samples(limit=20, project_id=project_id, sort_by=sort_by, reversed=reversed)
            n_pages = int(session.get_num_samples(project_id=project_id) / 20)
    
        return make_response(
            render_template(
                template, samples=samples,
                n_pages=n_pages, active_page=page,
                current_sort=sort_by, current_sort_order=order,
                project=project, library=library
            ), push_url=False
        )


@samples_htmx.route("create/<int:project_id>", methods=["POST"])
@login_required
def create(project_id: int):
    sample_form = forms.SampleForm()
    name = sample_form.name.data

    if (project := db.db_handler.get_project(project_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)

    validated, sample_form = sample_form.custom_validate(
        db_handler=db.db_handler, user_id=current_user.id
    )
    if not validated:
        selected_organism = db.db_handler.get_organism(sample_form.organism.data)

        logger.debug(sample_form.errors)
        logger.debug(selected_organism)

        template = render_template(
            "forms/sample/sample.html",
            sample_form=sample_form, project=project,
            selected_organism=str(selected_organism) if selected_organism else ""
        )
        return make_response(
            template, push_url=False
        )

    with DBSession(db.db_handler) as session:
        sample = session.create_sample(
            name=name,
            organism_tax_id=sample_form.organism.data,
            project_id=project_id,
            owner_id=current_user.id
        )

    logger.info(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})")
    flash(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})", "success")
    return make_response(
        redirect=url_for(
            "projects_page.project_page", project_id=project_id,
        ),
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
    logger.debug("HELLO")
    with DBSession(db.db_handler) as session:
        if current_user.role_type == UserRole.CLIENT:
            samples = session.get_samples(limit=None, user_id=current_user.id)
        else:
            samples = session.get_samples(limit=None, user_id=None)

    df = pd.DataFrame.from_records([sample.to_dict() for sample in samples])
    logger.debug(df.columns)
    return Response(
        df.to_csv(sep="\t", index=False), mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=samples.tsv"}
    )


@samples_htmx.route("parse_table/<int:project_id>", methods=["POST"])
@login_required
def parse_table(project_id: int):
    if (project := db.db_handler.get_project(project_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    table_input_form = forms.TableForm()
    validated, table_input_form = table_input_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/sample/table.html",
                table_form=table_input_form,
                project_id=project_id,
            ), push_url=False
        )
    
    raw_text, sep = table_input_form.get_data()

    df = pd.read_csv(
        StringIO(raw_text.rstrip()), sep=sep, index_col=False, header=0
    )

    sample_table_form = forms.SampleTableForm()
    sample_table_form.data.data = df.to_csv(sep="\t", index=False, header=True)

    columns = df.columns.tolist()
    refs = [key for key, _ in forms.SampleColSelectForm._sample_fields if key]
    matches = tools.connect_similar_strings(forms.SampleColSelectForm._sample_fields, columns)

    for i, col in enumerate(columns):
        select_form = forms.SampleColSelectForm()
        select_form.select_field.label.text = col
        sample_table_form.fields.append_entry(select_form)
        sample_table_form.fields.entries[i].select_field.label.text = col
        if col in matches.keys():
            sample_table_form.fields.entries[i].select_field.data = matches[col]

    # Form is submittable if all columns are selected
    submittable: bool = set(matches.values()) == set(refs)

    return make_response(
        render_template(
            "components/popups/sample/col_mapping.html",
            columns=columns, sample_table_form=sample_table_form,
            matches=matches, data=df.values.tolist(),
            required_fields=refs,
            submittable=submittable,
            project_id=project_id,
        ), push_url=False
    )


@samples_htmx.route("map_columns/<int:project_id>", methods=["POST"])
@login_required
def map_columns(project_id: int):
    sample_table_form = forms.SampleTableForm()

    if not sample_table_form.validate_on_submit():
        return make_response(
            render_template(
                "components/popups/sample/col_mapping.html",
                sample_table_form=sample_table_form,
                project_id=project_id,
            ),
            push_url=False
        )

    df = pd.read_csv(StringIO(sample_table_form.data.data), sep="\t", index_col=False, header=0)
    for i, entry in enumerate(sample_table_form.fields.entries):
        val = entry.select_field.data.strip()
        if not val:
            continue
        df.rename(columns={df.columns[i]: val}, inplace=True)

    refs = [key for key, _ in forms.SampleColSelectForm._sample_fields if key]
    df = df[refs]

    category_mapping_form = forms.CategoricalMappingForm()
    organisms = sorted(df["organism"].unique())

    selected: list[str] = []
    for i, organism in enumerate(organisms):
        selected.append("")
        category_mapping_form.fields.append_entry(forms.CategoricalMappingField())
        category_mapping_form.fields.entries[i].raw_category.data = organism
        # category_mapping_form.fields.entries[i].category.data = organism

    category_mapping_form.data.data = df.to_csv(sep="\t", index=False)

    return make_response(
        render_template(
            "components/popups/sample/organism_map.html",
            category_mapping_form=category_mapping_form,
            categories=organisms,
            selected=selected,
            project_id=project_id,
        ), push_url=False
    )


@samples_htmx.route("map_organisms/<int:project_id>", methods=["POST"])
@login_required
def map_organisms(project_id: int):
    category_mapping_form = forms.CategoricalMappingForm()

    df = pd.read_csv(StringIO(category_mapping_form.data.data), sep="\t", index_col=False, header=0)
    category_mapping_form = forms.CategoricalMappingForm()
    organisms = sorted(df["organism"].unique())

    if not category_mapping_form.validate_on_submit():
        selected = []
        with DBSession(db.db_handler) as session:
            for i, organism in enumerate(organisms):
                category_mapping_form.fields.entries[i].raw_category.data = organism
                if category_mapping_form.fields.entries[i].category.data:
                    selected_organism = session.get_organism(category_mapping_form.fields.entries[i].category.data)
                    selected.append(str(selected_organism))
                else:
                    selected.append("")

        return make_response(
            render_template(
                "components/popups/sample/organism_map.html",
                category_mapping_form=category_mapping_form,
                categories=organisms, selected=selected, project_id=project_id,
            ), push_url=False
        )

    organism_id_mapping = {}
    for i, organism in enumerate(organisms):
        organism_id_mapping[organism] = category_mapping_form.fields.entries[i].category.data
    df["organism_id"] = df["organism"].map(organism_id_mapping)

    project_sample_select_form = forms.ProjectSampleSelectForm()
    project_samples, errors = project_sample_select_form.parse_project_samples(project_id, df)

    return make_response(
        render_template(
            "components/popups/sample/project_sample_select.html",
            project_sample_select_form=project_sample_select_form,
            project_samples=project_samples, project_id=project_id, errors=errors
        ), push_url=False
    )


@samples_htmx.route("table/<int:project_id>", methods=["POST"])
@login_required
def add_samples_from_table(project_id: int):
    if (project := db.db_handler.get_project(project_id)) is None:
        return abort(HttpResponse.NOT_FOUND.value.id)
    
    project_sample_select_form = forms.ProjectSampleSelectForm()
    project_samples, errors = project_sample_select_form.parse_project_samples(project_id)
    validated, project_sample_select_form = project_sample_select_form.custom_validate()

    if not validated:
        return make_response(
            render_template(
                "components/popups/sample/project_sample_select.html",
                project_sample_select_form=project_sample_select_form,
                project_samples=project_samples, project_id=project_id, errors=errors
            )
        )

    df = pd.read_csv(StringIO(project_sample_select_form.data.data), sep="\t", index_col=False, header=0)

    if project_sample_select_form.selected_samples.data is None:
        assert False    # This should never happen because its checked in custom_validate()

    selected_samples_ids = project_sample_select_form.selected_samples.data.removeprefix(",").split(",")
    selected_samples_ids = [int(i) for i in selected_samples_ids if i != ""]

    n_added = 0
    with DBSession(db.db_handler) as session:
        for i, row in df.iterrows():
            if i not in selected_samples_ids:
                continue

            session.create_sample(
                name=row["sample_name"],
                organism_tax_id=row["organism_id"],
                project_id=project_id,
                owner_id=current_user.id
            )
            n_added += 1

    logger.info(f"Added samples from table to project {project.name} (id: {project.id})")
    if n_added == 0:
        flash("No samples added.", "warning")
    elif n_added == len(selected_samples_ids):
        flash(f"Added all ({n_added}) samples to project succesfully.", "success")
    elif n_added < len(selected_samples_ids):
        flash(f"Some samples ({len(selected_samples_ids) - n_added}) could not be added.", "warning")

    return make_response(
        redirect=url_for(
            "projects_page.project_page",
            project_id=project_id
        ),
    )


@samples_htmx.route("restart_form/<int:project_id>", methods=["GET"])
@login_required
def restart_form(project_id: int):
    sample_table_form = forms.TableForm()
    return make_response(
        render_template(
            "components/popups/sample/table.html",
            table_form=sample_table_form,
            project_id=project_id,
        ), push_url=False
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


@samples_htmx.route("query", methods=["POST"], defaults={"exclude_library_id": None})
@samples_htmx.route("query/<int:exclude_library_id>", methods=["POST"])
@login_required
def query(exclude_library_id: Optional[int] = None):
    logger.debug(request.form.keys())
    field_name = next(iter(request.form.keys()))
    query = request.form.get(field_name)

    if query is None:
        return abort(HttpResponse.BAD_REQUEST.value.id)

    user = current_user
    if user.role_type == UserRole.CLIENT:
        _user_id = user.id
    else:
        _user_id = None
    if exclude_library_id is None:
        results = db.db_handler.query_samples(query, user_id=_user_id)
    else:
        results = db.db_handler.query_samples(
            query, exclude_library_id=exclude_library_id, user_id=_user_id
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

    user = current_user
    if user.role_type == UserRole.CLIENT:
        _user_id = user.id
    else:
        _user_id = None

    if field_name == "name":
        samples = db.db_handler.query_samples(word, user_id=_user_id)
    elif field_name == "id":
        try:
            word = int(word)
        except ValueError:
            return abort(HttpResponse.BAD_REQUEST.value.id)
        if (sample := db.db_handler.get_sample(word)) is None:
            samples = []
        else:
            samples = [sample]
    else:
        assert False  # This should never happen

    return make_response(
        render_template(
            "components/tables/sample.html",
            current_query=word,
            samples=samples,
            field_name=field_name
        ), push_url=False
    )