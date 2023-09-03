from flask import Blueprint, url_for, render_template, flash
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger

experiments_bp = Blueprint("experiments_bp", __name__, url_prefix="/api/experiments/")
api = Api(experiments_bp)

class GetExperiments(Resource):
    @login_required
    def get(self, page):
        n_pages = int(db.db_handler.get_num_experiments() / 20)
        page = min(page, n_pages)
        experiments = db.db_handler.get_experiments(limit=20, offset=20*(page))

        return make_response(
            render_template(
                "components/tables/experiment.html",
                experiments=experiments,
                n_pages=n_pages, active_page=page
            ), push_url=False
        )

class PostExperiment(Resource):
    @login_required
    def post(self):
        experiment_form = forms.ExperimentForm()

        if not experiment_form.validate_on_submit():
            template = render_template(
                "forms/experiment.html",
                experiment_form=experiment_form
            )
            return make_response(
                template, push_url=False
            )
        
        experiment = db.db_handler.create_experiment(
            name=experiment_form.name.data,
            flowcell=experiment_form.flowcell.data
        )
        
        logger.debug(f"Created experiment {experiment.name}.")
        flash(f"Created experiment {experiment.name}.", "success")

        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id),
        )

class AddSampleToProject(Resource):
    @login_required
    def post(self, project_id):
        project = db.db_handler.get_project(project_id)
        if not project:
            return make_response(
                redirect=url_for("projects_page.project_page"),
            )
        
        sample_select_form = forms.SampleSelectForm()
        if sample_select_form.validate_on_submit():
            sample = db.db_handler.get_sample(sample_select_form.sample.data.id)
            db.db_handler.link_project_sample(
                project_id=project_id,
                sample_id=sample.id
            )
            return make_response(
                redirect=url_for("projects_page.project_page"),
            )
    
api.add_resource(PostExperiment, "experiment")
api.add_resource(AddSampleToProject, "<int:project_id>/add_sample")
api.add_resource(GetExperiments, "get")