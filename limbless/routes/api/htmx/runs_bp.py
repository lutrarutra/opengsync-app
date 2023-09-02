from flask import Blueprint, redirect, url_for, render_template, flash
from flask_restful import Api, Resource
from flask_htmx import make_response

from .... import db, logger, forms

runs_bp = Blueprint("runs_bp", __name__, url_prefix="/api/runs/")
api = Api(runs_bp)

class GetRuns(Resource):
    def get(self, page):
        n_pages = int(db.db_handler.get_num_runs() / 20)
        page = min(page, n_pages)

        runs = db.db_handler.get_runs(limit=20, offset=20*(page))
        return make_response(
            render_template(
                "components/tables/run.html", runs=runs,
                n_pages=n_pages, active_page=page
            ), push_url=False
        )

class PostRun(Resource):
    def post(self, experiment_id):
        run_form = forms.RunForm()        
        
        if not run_form.validate_on_submit():
            template = render_template(
                "forms/run.html", run_form=run_form
            )
            return make_response(
                template, push_url=False
            )
        
        experiment_runs = db.db_handler.get_experiment_runs(experiment_id)        
        if run_form.lane.data in [run.lane for run in experiment_runs]:
            run_form.lane.errors.append("Lane already exists in experiment.")
            template = render_template(
                "forms/run.html", run_form=run_form
            )
            return make_response(
                template, push_url=False
            )
        
        run = db.db_handler.create_run(
            lane=run_form.lane.data,
            experiment_id=experiment_id,
            r1_cycles=run_form.r1_cycles.data,
            r2_cycles=run_form.r2_cycles.data,
            i1_cycles=run_form.i1_cycles.data,
            i2_cycles=run_form.i2_cycles.data,
        )
        
        logger.debug(f"Created run.")
        flash(f"Added new run for lane '{run.lane}'", "success")
        
        return make_response(
            redirect=url_for("runs_page.run_page", run_id=run.id),
        )

class EditRun(Resource):
    def post(self, run_id):
        run = db.db_handler.get_run(run_id)
        if not run:
            return redirect("/runs")
        
        run_form = forms.RunForm()
        
        if not run_form.validate_on_submit():
            template = render_template(
                "forms/run.html", run_form=run_form, run_id=run_id
            )
            return make_response(
                template, push_url=False
            )
        
        if run_form.lane.data != run.lane:
            experiment_runs = db.db_handler.get_experiment_runs(run.experiment_id)        
            if run_form.lane.data in [run.lane for run in experiment_runs]:
                run_form.lane.errors.append("Lane already exists in experiment.")
                template = render_template(
                    "forms/run.html", run_form=run_form, run_id=run_id
                )
                return make_response(
                    template, push_url=False
                )

        db.db_handler.update_run(
            run_id, lane=run_form.lane.data,
            r1_cycles=run_form.r1_cycles.data,
            r2_cycles=run_form.r2_cycles.data,
            i1_cycles=run_form.i1_cycles.data,
            i2_cycles=run_form.i2_cycles.data,
        )

        logger.debug(f"Edited {run}")
        flash(f"Changes saved succesfully!", "success")

        return make_response(
            redirect=url_for("runs_page.run_page", run_id=run_id),
        )
    
api.add_resource(GetRuns, "get")
api.add_resource(PostRun, "<int:experiment_id>/run")
api.add_resource(EditRun, "edit/<int:run_id>")