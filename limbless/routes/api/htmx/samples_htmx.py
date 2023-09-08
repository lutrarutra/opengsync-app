from io import StringIO

from flask import Blueprint, redirect, url_for, render_template, flash, request, abort
from flask_htmx import make_response
from flask_login import login_required
from werkzeug.utils import secure_filename

import pandas as pd

from .... import db, logger, forms, tools, models
from ....core import DBSession

samples_htmx = Blueprint("samples_htmx", __name__, url_prefix="/api/samples/")


@login_required
@samples_htmx.route("get/<int:page>", methods=["GET"])
def get(page):
    n_pages = int(db.db_handler.get_num_samples() / 20)
    page = min(page, n_pages)
    samples = db.db_handler.get_samples(limit=20, offset=20 * page)
    return make_response(
        render_template(
            "components/tables/sample.html", samples=samples,
            n_pages=n_pages, active_page=page
        ), push_url=False
    )


@login_required
@samples_htmx.route("create/<int:project_id>", methods=["POST"])
def create(project_id):
    sample_form = forms.SampleForm()
    name = sample_form.name.data

    with DBSession(db.db_handler) as session:
        if (project := session.get_project(project_id)) is None:
            return abort(404)

        sample_name_taken = name in [sample.name for sample in project.samples]

    if not sample_form.validate_on_submit() or sample_name_taken:
        if sample_name_taken:
            sample_form.name.errors.append("Sample name already exists.")

        query = sample_form.organism_search.data
        if query == "" or query is None:
            q_organisms = db.common_organisms
        else:
            try:
                query = int(query)
                if res := db.db_handler.get_organism(query):
                    q_organisms = [res]
                else:
                    q_organisms = []
            except ValueError:
                q_organisms = db.db_handler.query_organisms(query)

        logger.debug(q_organisms)
        selected_organism = db.db_handler.get_organism(sample_form.organism.data)

        template = render_template(
            "forms/sample.html",
            sample_form=sample_form, project=project,
            sample_results=q_organisms,
            selected_organism=str(selected_organism) if selected_organism else None
        )
        return make_response(
            template, push_url=False
        )

    with DBSession(db.db_handler) as session:
        sample = session.create_sample(
            name=name,
            organism_tax_id=sample_form.organism.data,
            project_id=project_id
        )

    logger.info(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})")
    flash(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})", "success")
    return make_response(
        redirect=url_for(
            "projects_page.project_page", project_id=project_id,
        ),
    )


@login_required
@samples_htmx.route("<int:sample_id>/delete", methods=["GET"])
def delete(sample_id: int):
    sample = db.db_handler.get_sample(sample_id)
    if sample is None:
        return redirect("/projects")

    with DBSession(db.db_handler) as session:
        session.delete_sample(sample_id)

    logger.info(f"Deleted sample {sample.name} (id: {sample.id})")
    flash(f"Deleted sample {sample.name} (id: {sample.id})", "success")

    return make_response(
        redirect=url_for(
            "samples_page.samples_page"
        ),
    )


@login_required
@samples_htmx.route("parse_table/<int:project_id>", methods=["POST"])
def parse_table(project_id: int):
    table_input_form = forms.TableForm()
    sample_table_form = forms.SampleTableForm()

    if not table_input_form.validate_on_submit():
        return make_response(
            render_template(
                "components/popups/sample_table.html",
                table_form=table_input_form,
                project_id=project_id,
            ), push_url=False
        )

    if table_input_form.data.data:
        raw_text = table_input_form.data.data
        sep = "\t" if raw_text.count("\t") > raw_text.count(",") else ","
    elif table_input_form.file.data:
        filename = secure_filename(table_input_form.file.data.filename)
        table_input_form.file.data.save("data/uploads/" + filename)
        logger.debug(f"Saved file to data/uploads/{filename}")
        raw_text = open("data/uploads/" + filename).read()
        sep = "\t" if filename.split(".")[-1] == "tsv" else ","
    else:
        table_input_form.text.errors.append("Please enter text or upload a file.")
        table_input_form.file.errors.append("Please enter text or upload a file.")
        logger.debug(table_input_form.errors)
        return make_response(
            render_template(
                "components/popups/sample_table.html",
                table_form=table_input_form,
                project_id=project_id,
            ), push_url=False
        )

    df = pd.read_csv(
        StringIO(raw_text.rstrip()), sep=sep,
        index_col=False, header=0
    )

    sample_table_form.data.data = raw_text

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
            "components/popups/sample_col.html",
            columns=columns, sample_table_form=sample_table_form,
            matches=matches, data=df.values.tolist(),
            required_fields=refs,
            submittable=submittable,
            project_id=project_id,
        ), push_url=False
    )


@login_required
@samples_htmx.route("map_columns/<int:project_id>", methods=["POST"])
def map_columns(project_id: int):
    sample_table_form = forms.SampleTableForm()

    if not sample_table_form.validate_on_submit():
        return make_response(
            render_template(
                "components/popups/sample_col.html",
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

    results: list[list[str]] = []
    selected: list[str] = []
    with DBSession(db.db_handler) as session:
        for i, organism in enumerate(organisms):
            selected.append("")
            category_mapping_form.fields.append_entry(forms.CategoricalMappingField())
            category_mapping_form.fields.entries[i].raw_category.data = organism
            results.append(session.query_organisms(organism, limit=20))
        # category_mapping_form.fields.entries[i].category.data = organism

    category_mapping_form.data.data = df.to_csv(sep="\t", index=False)

    return make_response(
        render_template(
            "components/popups/sample_organism_map.html",
            category_mapping_form=category_mapping_form,
            categories=organisms,
            results=results,
            selected=selected,
            project_id=project_id,
        ), push_url=False
    )


@login_required
@samples_htmx.route("map_organisms/<int:project_id>", methods=["POST"])
def map_organisms(project_id: int):
    category_mapping_form = forms.CategoricalMappingForm()

    df = pd.read_csv(StringIO(category_mapping_form.data.data), sep="\t", index_col=False, header=0)
    category_mapping_form = forms.CategoricalMappingForm()
    organisms = sorted(df["organism"].unique())

    results: list[list[str]] = []

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
                results.append(session.query_organisms(organism, limit=20))
        return make_response(
            render_template(
                "components/popups/sample_organism_map.html",
                category_mapping_form=category_mapping_form,
                categories=organisms,
                results=results,
                selected=selected,
                project_id=project_id,
            ), push_url=False
        )

    organism_id_mapping = {}

    for i, organism in enumerate(organisms):
        organism_id_mapping[organism] = category_mapping_form.fields.entries[i].category.data

    df["organism_id"] = df["organism"].map(organism_id_mapping)

    sample_table_confirm_form = forms.SampleTableConfirmForm()
    sample_table_confirm_form.data.data = df.to_csv(sep="\t", index=False)
    new_samples = [
        models.Sample(id=i + 1, name=row["sample_name"], organism=row["organism"], organism_id=row["organism_id"])
        for i, row in df.iterrows()
    ]

    # Check if sample names are unique in project
    errors = []
    with DBSession(db.db_handler) as session:
        project = session.get_project(project_id)
        project_names = [sample.name for sample in project.samples]

    selected_samples = []
    for sample in new_samples:
        if sample.name in project_names:
            errors.append(f"Sample name {sample.name} already exists.")
        else:
            errors.append(None)
            selected_samples.append(str(sample.id))

    sample_table_confirm_form.selected_samples.data = ",".join(selected_samples)

    return make_response(
        render_template(
            "components/popups/sample_table_confirm.html",
            sample_table_confirm_form=sample_table_confirm_form,
            new_samples=new_samples,
            project_id=project_id,
            errors=errors
        ), push_url=False
    )


@login_required
@samples_htmx.route("table/<int:project_id>", methods=["POST"])
def add_samples_from_table(project_id: int):
    sample_table_confirm_form = forms.SampleTableConfirmForm()
    df = pd.read_csv(StringIO(sample_table_confirm_form.data.data), sep="\t", index_col=False, header=0)

    selected_samples_ids = sample_table_confirm_form.selected_samples.data.removeprefix(",").split(",")
    selected_samples_ids = [int(i) for i in selected_samples_ids if i != ""]

    if not sample_table_confirm_form.validate_on_submit():
        new_samples = [
            models.Sample(id=i + 1, name=row["sample_name"], organism=row["organism"], organism_id=row["organism_id"])
            for i, row in df.iterrows()
        ]
        return make_response(
            render_template(
                "components/popups/sample_table_confirm.html",
                sample_table_confirm_form=sample_table_confirm_form,
                new_samples=new_samples,
                project_id=project_id,
            ), push_url=False
        )

    if (project := db.db_handler.get_project(project_id)) is None:
        return redirect("/projects")

    n_added = 0
    with DBSession(db.db_handler) as session:
        for i, row in df.iterrows():
            if i + 1 not in selected_samples_ids:
                continue

            session.create_sample(
                name=row["sample_name"],
                organism_tax_id=row["organism_id"],
                project_id=project_id,
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


@login_required
@samples_htmx.route("restart_form/<int:project_id>", methods=["GET"])
def restart_form(project_id: int):
    sample_table_form = forms.TableForm()
    return make_response(
        render_template(
            "components/popups/sample_table.html",
            table_form=sample_table_form,
            project_id=project_id,
        ), push_url=False
    )


@login_required
@samples_htmx.route("<int:sample_id>/edit", methods=["POST"])
def edit(sample_id):
    sample = db.db_handler.get_sample(sample_id)
    if not sample:
        return redirect("/projects")

    sample_form = forms.SampleForm()

    if not sample_form.validate_on_submit():
        if (
            "Sample name already exists." in sample_form.name.errors and
            sample_form.name.data == sample.name
        ):
            sample_form.name.errors.remove("Sample name already exists.")
        else:
            template = render_template(
                "forms/sample.html",
                sample_form=sample_form,
                sample=sample
            )
            return make_response(
                template, push_url=False
            )

    print(sample_form.organism.data)
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


@login_required
@samples_htmx.route("query", methods=["GET"])
def query():
    field_name = next(iter(request.args.keys()))
    query = request.args.get(field_name)
    assert query is not None

    results = db.db_handler.query_samples(query)

    logger.debug(results)

    return make_response(
        render_template(
            "components/search_select_results.html",
            results=results,
            field_name=field_name
        ), push_url=False
    )
