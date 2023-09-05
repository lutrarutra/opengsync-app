from flask import Blueprint, redirect, url_for, render_template, flash, request
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import FormField
from flask_login import login_required, current_user

from .... import db, logger, forms
from ....models import categories

libraries_bp = Blueprint("libraries_bp", __name__, url_prefix="/api/libraries/")
api = Api(libraries_bp)

class GetLibraries(Resource):
    @login_required
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
    @login_required
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
    @login_required
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
                    "forms/library.html",
                    library_form=library_form,
                    library_id=library_id,
                    selected_kit=library.index_kit,
                )
                return make_response(
                    template, push_url=False
                )

        try:
            library_type_id = int(library_form.library_type.data)
            library_type = categories.LibraryType.get(library_type_id)
        except ValueError:
            library_type = None
        
        library = db.db_handler.update_library(
            library_id=library_id,
            name=library_form.name.data,
            library_type=library_type,
            index_kit_id=library_form.index_kit.data,
        )
        logger.debug(f"Updated library '{library.name}'.")
        flash(f"Updated library '{library.name}'.", "success")

        return make_response(
            redirect=url_for("libraries_page.library_page", library_id=library.id),
        )
    
class SearchLibrary(Resource):
    @login_required
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
    
class Form(FlaskForm):
    library_sample_form = FormField(forms.LibrarySampleForm)
    index_form = FormField(forms.SCRNAIndexForm)
    
class AddSample(Resource):
    @login_required
    def post(self, library_id: int):
        library = db.db_handler.get_library(library_id)
        if not library:
            return redirect("/libraries")
        
        library_sample_form = forms.LibrarySampleForm()
        index_form = forms.SCRNAIndexForm()

        if library_sample_form.sample.data is not None:
            selected_sample = db.db_handler.get_sample(library_sample_form.sample.data)
        else:
            selected_sample = None

        if index_form.adapter.data is not None:
            selected_adapter = index_form.adapter.data
        else:
            selected_adapter = ""

        form = Form()
        form.library_sample_form.form = library_sample_form
        form.library_sample_form.form.sample.data = library_sample_form.sample.data
        form.index_form.form = index_form

        if not form.validate_on_submit():
            logger.debug(form.errors)
            template = render_template(
                "forms/sample_library.html",
                library=library,
                library_sample_form=form.library_sample_form.form,
                index_form=form.index_form.form,
                selected_sample=selected_sample.name if selected_sample is not None else "",
                selected_adapter=selected_adapter
            )
            return make_response(template)
        
        logger.debug(form.validate_on_submit())
        logger.debug(form.errors)

        logger.debug(form.index_form.form.adapter.data)
        logger.debug(form.library_sample_form.form.sample.data)

api.add_resource(GetLibraries, "get")    
api.add_resource(PostLibrary, "library/<int:run_id>")
api.add_resource(EditLibrary, "edit/<int:library_id>")
api.add_resource(SearchLibrary, "search")
api.add_resource(AddSample, "<int:library_id>/add_sample")