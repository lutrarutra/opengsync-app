from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_restful import Api, Resource
from flask_htmx import make_response

from .... import db, logger, forms

libraries_bp = Blueprint("libraries_bp", __name__, url_prefix="/api/libraries/")
api = Api(libraries_bp)

class GetLibraries(Resource):
    def get(self, page):
        n_pages = int(db.db_handler.get_num_libraries() / 20)
        
        page = min(page, n_pages)

        samples = db.db_handler.get_libraries(limit=20, offset=20*(page))

        return make_response(
            render_template(
                "components/tables/library.html", libraries=libraries,
                n_pages=n_pages, active_page=page
            ), push_url=False
        )
class PostLibrary(Resource):
    def post(self, run_id):
        run = db.db_handler.get_run(run_id)
        if not run:
            return redirect("/runs")
        
        library_form = forms.LibraryForm()        
        
        if not library_form.validate_on_submit():
            template = render_template(
                "forms/library.html", run_form=library_form
            )
            return make_response(
                template, push_url=False
            )
        
        library = db.db_handler.create_library(
            name=library_form.name.data,
            library_type=library_form.library_type.data,
        )
        db.db_handler.link_run_library(run_id, library.id)
        
        logger.debug(f"Created library '{library.name}'.")
        flash(f"Created library '{library.name}'.", "success")
        
        return make_response(
            redirect=url_for("libraries_page.library_page", library_id=library.id),
        )

class EditLibrary(Resource):
    def post(self, library_id):
        library = db.db_handler.get_library(library_id)
        if not library:
            return redirect("/libraries")
        
        library_form = forms.LibraryForm()

        if not library_form.validate_on_submit():
            if (
                "Library name already exists." in library_form.name.errors and 
                library_form.name.data == library.name
                ):
                library_form.name.errors.remove("Library name already exists.")
            else:
                template = render_template(
                    "forms/library.html", library_form=library_form, library_id=library_id
                )
                return make_response(
                    template, push_url=False
                )
        
        db.db_handler.update_library(
            library_id=library_id,
            name=library_form.name.data,
            library_type=library_form.library_type.data,
        )
        logger.debug(f"Updated library '{library.name}'.")
        flash(f"Updated library '{library.name}'.", "success")

        return make_response(
            redirect=url_for("libraries_page.library_page", library_id=library.id),
        )
    
class SearchLibrary(Resource):
    def get(self):
        query = request.args.get("query")

        if not query:
            template = render_template(
                "components/tables/library.html"
            )
            return make_response(
                template, push_url=False
            )
        
        template = render_template(
            "components/tables/library.html"
        )
        return make_response(
            template, push_url=False
        )
    

api.add_resource(GetLibraries, "get")    
api.add_resource(PostLibrary, "library/<int:run_id>")
api.add_resource(EditLibrary, "edit/<int:library_id>")
api.add_resource(SearchLibrary, "search")