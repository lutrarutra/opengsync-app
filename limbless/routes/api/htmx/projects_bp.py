from flask import Blueprint, url_for, render_template, flash
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_login import login_required, current_user

from .... import db, forms, logger

projects_bp = Blueprint("projects_bp", __name__, url_prefix="/api/projects/")
api = Api(projects_bp)

class GetProjects(Resource):
    @login_required
    def get(self, page):
        n_pages = int(db.db_handler.get_num_projects() / 20)
        page = min(page, n_pages)
        projects = db.db_handler.get_projects(limit=20, offset=20*(page))
        
        return make_response(
            render_template(
                "components/tables/project.html", projects=projects,
                n_pages=n_pages, active_page=page
            ), push_url=False
        )

class PostProject(Resource):
    @login_required
    def post(self):
        project_form = forms.ProjectForm()

        if not project_form.validate_on_submit():
            template = render_template(
                "forms/project.html",
                project_form=project_form
            )
            return make_response(
                template, push_url=False
            )

        project = db.db_handler.create_project(
            name=project_form.name.data,
            description=project_form.description.data,
        )

        logger.debug(f"Created project {project.name}.")
        flash(f"Created project {project.name}.", "success")
        
        return make_response(
            redirect=url_for("projects_page.project_page", project_id=project.id),
        )


    
api.add_resource(PostProject, "post")
api.add_resource(GetProjects, "get")
