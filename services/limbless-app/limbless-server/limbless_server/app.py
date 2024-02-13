import os
from uuid import uuid4
from typing import TYPE_CHECKING

from flask import Flask, render_template, redirect, request, url_for, session, current_app, abort, make_response, send_from_directory
from flask_login import login_required
import sass

from limbless_db import categories, models
from . import htmx, bcrypt, login_manager, mail, db, SECRET_KEY, logger
from .routes import api, pages

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user


def create_app():
    app = Flask(__name__, static_folder="/usr/src/app/static", template_folder="/usr/src/app/templates")

    app.debug = os.getenv("LIMBLESS_DEBUG") == "1"

    for _, file_type in categories.FileType.as_tuples():
        if not os.path.exists(file_type.description):   # type: ignore
            os.makedirs(file_type.description)          # type: ignore

    if app.debug:
        logger.debug("Compiling SASS..")
        sass.compile(dirname=("/usr/src/app/static/style", "/usr/src/app/static/style/compiled"))

    logger.info(f"Debug mode: {app.debug}")

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAIL_SERVER"] = "smtp-relay.sendinblue.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    # app.config["MAIL_USE_SSL"] = True
    app.config["MAIL_USERNAME"] = os.environ.get("EMAIL_USER")
    app.config["MAIL_PASSWORD"] = os.environ.get("EMAIL_PASS")
    assert app.config["MAIL_USERNAME"]
    assert app.config["MAIL_PASSWORD"]

    htmx.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: int) -> models.User:
        user = db.db_handler.get_user(user_id)
        return user

    @app.route("/index_page")
    def _index_page():
        return redirect(url_for("index_page"))

    @app.route("/")
    def index_page():
        if not current_user.is_authenticated:
            return redirect(url_for("auth_page.auth_page", next=url_for("index_page")))
            
        if current_user.is_insider():
            show_drafts = False
            _user_id = None
            recent_experiments, _ = db.db_handler.get_experiments(sort_by="id", descending=False)
        else:
            show_drafts = True
            _user_id = current_user.id
            recent_experiments = None

        recent_seq_requests, _ = db.db_handler.get_seq_requests(user_id=_user_id, sort_by="submitted_time", descending=True, show_drafts=show_drafts)

        return render_template(
            "index.html",
            recent_seq_requests=recent_seq_requests,
            recent_experiments=recent_experiments
        )
    
    @app.route("/pdf_file/<int:file_id>")
    @login_required
    def pdf_file(file_id: int):
        if (file := db.db_handler.get_file(file_id)) is None:
            return abort(categories.HttpResponse.NOT_FOUND.value.id)
        
        if file.uploader_id != current_user.id and not current_user.is_insider():
            return abort(categories.HttpResponse.FORBIDDEN.value.id)
        
        if file.extension != ".pdf":
            return abort(categories.HttpResponse.BAD_REQUEST.value.id)

        file_path = os.path.join(current_app.root_path, "..", file.path)
        if not os.path.exists(file_path):
            return abort(categories.HttpResponse.NOT_FOUND.value.id)
        
        with open(file_path, "rb") as f:
            data = f.read()

        response = make_response(data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "inline; filename=auth_form.pdf"
        return response
    
    @app.route("/img_file/<int:file_id>")
    @login_required
    def img_file(file_id: int):
        if (file := db.db_handler.get_file(file_id)) is None:
            return abort(categories.HttpResponse.NOT_FOUND.value.id)
        
        if file.uploader_id != current_user.id and not current_user.is_insider():
            return abort(categories.HttpResponse.FORBIDDEN.value.id)
        
        if file.extension not in [".png", ".jpg", ".jpeg"]:
            return abort(categories.HttpResponse.BAD_REQUEST.value.id)

        file_path = os.path.join(current_app.root_path, "..", file.path)
        if not os.path.exists(file_path):
            return abort(categories.HttpResponse.NOT_FOUND.value.id)
        
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))

    @login_manager.unauthorized_handler
    def unauthorized():
        next = url_for(request.endpoint, **request.view_args)
        return redirect(url_for("auth_page.auth_page", next=next))
    
    @app.context_processor
    def inject_debug():
        return dict(debug=app.debug)
    
    @app.context_processor
    def inject_uuid():
        return dict(uuid4=uuid4)
    
    @app.context_processor
    def inject_categories():
        return dict(
            ExperimentStatus=categories.ExperimentStatus,
            SeqRequestStatus=categories.SeqRequestStatus,
            UserRole=categories.UserRole,
        )
    
    @app.before_request
    def before_request():
        session["from_url"] = request.referrer

    @app.route("/status")
    def status():
        return make_response("OK", 200)
    
    # app.register_blueprint(api.jobs_bp)
    app.register_blueprint(api.samples_htmx)
    app.register_blueprint(api.projects_htmx)
    app.register_blueprint(api.experiments_htmx)
    app.register_blueprint(api.pools_htmx)
    app.register_blueprint(api.auth_htmx)
    app.register_blueprint(api.organisms_htmx)
    app.register_blueprint(api.barcodes_htmx)
    app.register_blueprint(api.seq_requests_htmx)
    app.register_blueprint(api.adapters_htmx)
    app.register_blueprint(api.sequencers_htmx)
    app.register_blueprint(api.users_htmx)
    app.register_blueprint(api.libraries_htmx)
    app.register_blueprint(api.seq_request_form_htmx)
    app.register_blueprint(api.features_htmx)
    app.register_blueprint(api.pooling_form_htmx)
    app.register_blueprint(api.feature_kits_htmx)

    app.register_blueprint(pages.samples_page_bp)
    app.register_blueprint(pages.projects_page_bp)
    app.register_blueprint(pages.experiments_page_bp)
    app.register_blueprint(pages.libraries_page_bp)
    app.register_blueprint(pages.auth_page_bp)
    app.register_blueprint(pages.users_page_bp)
    app.register_blueprint(pages.seq_requests_page_bp)
    app.register_blueprint(pages.index_kits_page_bp)
    app.register_blueprint(pages.errors_bp)
    app.register_blueprint(pages.devices_page_bp)
    app.register_blueprint(pages.pools_page_bp)
    app.register_blueprint(pages.feature_kits_page_bp)

    return app
