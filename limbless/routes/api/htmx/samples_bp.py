from io import StringIO

from flask import Blueprint, redirect, url_for, render_template, flash
from flask_restful import Api, Resource
from flask_htmx import make_response
import pandas as pd

from .... import db, logger, forms, tools
from ....core.DBSession import DBSession

samples_bp = Blueprint("samples_bp", __name__, url_prefix="/api/samples/")
api = Api(samples_bp)

class GetSamples(Resource):
    def get(self, page):
        n_pages = int(db.db_handler.get_num_samples() / 20)
        if page > n_pages:
            page = n_pages
        samples = db.db_handler.get_samples(limit=20, offset=20*(page))
        return make_response(
            render_template(
                "components/tables/sample.html", samples=samples,
                n_pages=n_pages, active_page=page
            ), push_url=False
        )

class PostSample(Resource):
    def post(self, project_id):
        sample_form = forms.SampleForm()
        project = db.db_handler.get_project(project_id)
        if not project:
            return redirect("/projects") # TODO: 404

        if sample_form.validate_on_submit():
            with DBSession(db.db_handler) as session:
                sample = session.create_sample(
                    name=sample_form.name.data,
                    organism=sample_form.organism.data,
                    index1=sample_form.index1.data,
                    index2=sample_form.index2.data,
                    project_id=project_id
                )

                sample = session.get_sample(sample.id)
                project = session.get_project(project.id)
                project.samples = session.get_project_samples(project.id)

            logger.info(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})")
            flash(f"Added sample {sample.name} (id: {sample.id}) to project {project.name} (id: {project.id})", "success")
            return make_response(
                redirect=url_for(
                    "projects_page.project_page", project_id=project_id,
                ),
            )
        else:
            logger.debug(sample_form.errors)

        template = render_template(
            "forms/sample.html",
            sample_form=sample_form, project=project,
        )
        return make_response(
            template, push_url=False
        )
    
class ReadSampleTable(Resource):
    def post(self):
        sample_text_form = forms.SampleTextForm()
        sample_table_form = forms.SampleTableForm()
        if sample_text_form.validate_on_submit():
            df = pd.read_csv(
                StringIO(sample_text_form.text.data.rstrip()), sep="\t",
                index_col=False, header=0
            )

            sample_table_form.text.data = sample_text_form.text.data

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
                    "forms/sample_table.html",
                    columns=columns, sample_table_form=sample_table_form,
                    matches=matches, data=df.values.tolist(),
                    required_fields=refs,
                    submittable=submittable
                ), push_url=False
            )
        else:
            return make_response(
                render_template(
                    "components/sample_popup.html",
                    table_form=sample_text_form,
                ), push_url=False
            )
    
class PostSampleTable(Resource):
    def post(self, project_id):
        table_form = forms.SampleTableForm()

        project = db.db_handler.get_project(project_id)
        if not project:
            return redirect("/projects") # TODO: 404

        if table_form.validate_on_submit():
            df = pd.read_csv(StringIO(table_form.text.data), sep="\t", index_col=False, header=0)
            for i, entry in enumerate(table_form.fields.entries):
                val = entry.select_field.data.strip()
                if not val:
                    continue
                df.rename(columns={df.columns[i]:val}, inplace=True)

            n_added = 0
            with DBSession(db.db_handler) as session:
                for _, row in df.iterrows():
                    existing_sample = session.get_sample_by_name(row["sample_name"])

                    if existing_sample:
                        continue

                    session.create_sample(
                        name=row["sample_name"],
                        organism=row["organism"],
                        project_id=project_id,
                        index1=row["index1"],
                        index2=row["index2"]
                    )
                    n_added += 1

            logger.info(f"Added samples from table to project {project.name} (id: {project.id})")
            if n_added == len(df):
                flash(f"Added all ({n_added}) samples to project succesfully.", "success")
            elif n_added == 0:
                flash(f"No samples added.", "error")
            elif n_added < len(df):
                flash(f"Some samples ({len(df) - n_added}) could not be added.", "warning")

            return make_response(
                redirect=url_for("projects_page.project_page", project_id=project_id),
            )
        else:
            logger.debug(table_form.errors)

        template = render_template(
            "components/sample_popup.html",
            table_form=table_form, project=project,
        )
        return make_response(
            template, push_url=False
        )
    
class EditSample(Resource):
    def post(self, sample_id):
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
                    "forms/sample.html", sample_form=sample_form
                )
                return make_response(
                    template, push_url=False
                )
    
        db.db_handler.update_sample(
            sample_id,
            name=sample_form.name.data,
            organism=sample_form.organism.data,
            index1=sample_form.index1.data,
            index2=sample_form.index2.data
        )

        logger.debug(f"Edited {sample}")
        flash(f"Changes saved succesfully!", "success")

        return make_response(
            redirect=url_for("samples_page.sample_page", sample_id=sample_id),
        )

    
api.add_resource(PostSample, "add/<int:project_id>")
api.add_resource(GetSamples, "get/<int:page>")
api.add_resource(PostSampleTable, "table/<int:project_id>")
api.add_resource(EditSample, "edit/<int:sample_id>")
api.add_resource(ReadSampleTable, "read_table")
