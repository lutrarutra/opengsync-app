import os
from uuid import uuid4
from typing import TYPE_CHECKING
from datetime import datetime

import pandas as pd

from flask import Flask, render_template, redirect, request, url_for, session, abort, make_response
from flask_login import login_required

from limbless_db import categories, models, db_session, TIMEZONE, to_utc

from . import htmx, bcrypt, login_manager, mail, SECRET_KEY, logger, db, cache, msf_cache
from .routes import api, pages
from .tools.spread_sheet_components import InvalidCellValue, MissingCellValue, DuplicateCellValue

if TYPE_CHECKING:
    current_user: models.User = None   # type: ignore
else:
    from flask_login import current_user


def create_app(static_folder: str, template_folder: str) -> Flask:
    if not os.path.exists(static_folder):
        raise FileNotFoundError(f"Static folder not found: {static_folder}")
    
    if not os.path.exists(template_folder):
        raise FileNotFoundError(f"Template folder not found: {template_folder}")
    
    app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
    db.connect(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        db=os.environ["POSTGRES_DB"],
    )
    app.debug = os.getenv("LIMBLESS_DEBUG") == "1"
    app.config["MEDIA_FOLDER"] = os.path.join("media")
    app.config["UPLOADS_FOLDER"] = os.path.join("uploads")
    if (REDIS_PORT := os.getenv("REDIS_PORT")) is None:
        raise ValueError("REDIS_PORT env-variable not set")
    cache.init_app(app, config={"CACHE_TYPE": "redis", "CACHE_REDIS_URL": f"redis://redis-cache:{REDIS_PORT}/0"})

    msf_cache.connect("redis-cache", int(REDIS_PORT), 1)

    for file_type in categories.FileType.as_list():
        if file_type.dir is None:
            continue
        path = os.path.join(app.config["MEDIA_FOLDER"], file_type.dir)
        if not os.path.exists(path):
            os.makedirs(path)

    logger.info(f"Debug mode: {app.debug}")
    logger.info(f"TIMEZONE: {TIMEZONE}")
    logger.info(f"Time: {datetime.now().strftime('%H:%M')} (UTC: {to_utc(datetime.now()).strftime('%H:%M')})")

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAIL_SERVER"] = "smtp-relay.sendinblue.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    # app.config["MAIL_USE_SSL"] = True
    app.config["MAIL_USERNAME"] = os.environ["EMAIL_USER"]
    app.config["MAIL_PASSWORD"] = os.environ["EMAIL_PASS"]
    assert app.config["MAIL_USERNAME"]
    assert app.config["MAIL_PASSWORD"]

    htmx.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: int) -> models.User | None:
        if (user := db.get_user(user_id)) is None:
            logger.error(f"User not found: {user_id}")
            return None
        return user
    
    if app.debug:
        @app.route("/test")
        def test():
            return render_template("test.html")
        
    @app.route("/help")
    @cache.cached(timeout=1500)
    def help_page():
        return render_template("help.html")
    
    @app.route("/")
    @db_session(db)
    @login_required
    def dashboard():
        if not current_user.is_authenticated:
            return redirect(url_for("auth_page.auth_page", next=url_for("dashboard")))
        
        if current_user.is_insider():
            return render_template("dashboard-insider.html")
        return render_template("dashboard-user.html")

    @app.route("/pdf_file/<int:file_id>")
    @login_required
    @cache.cached(timeout=60)
    def pdf_file(file_id: int):
        if (file := db.get_file(file_id)) is None:
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        if file.uploader_id != current_user.id and not current_user.is_insider():
            if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                return abort(categories.HTTPResponse.FORBIDDEN.id)
        
        if file.extension != ".pdf":
            return abort(categories.HTTPResponse.BAD_REQUEST.id)

        filepath = os.path.join(app.config["MEDIA_FOLDER"], file.path)
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        with open(filepath, "rb") as f:
            data = f.read()

        response = make_response(data)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = "inline; filename=auth_form.pdf"
        return response
    
    @app.route("/img_file/<int:file_id>")
    @login_required
    @cache.cached(timeout=60)
    def img_file(file_id: int):
        if (file := db.get_file(file_id)) is None:
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        if file.uploader_id != current_user.id and not current_user.is_insider():
            if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                return abort(categories.HTTPResponse.FORBIDDEN.id)
        
        if file.extension not in [".png", ".jpg", ".jpeg"]:
            return abort(categories.HTTPResponse.BAD_REQUEST.id)

        filepath = os.path.join(app.config["MEDIA_FOLDER"], file.path)
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        with open(filepath, "rb") as f:
            data = f.read()

        response = make_response(data)
        response.headers["Content-Type"] = f"image/{file.extension[1:]}"
        response.headers["Content-Disposition"] = "inline; filename={file.name}"
        return response
    
    @app.route("/download_file/<int:file_id>")
    @login_required
    @cache.cached(timeout=60)
    def download_file(file_id: int):
        if (file := db.get_file(file_id)) is None:
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        if file.uploader_id != current_user.id and not current_user.is_insider():
            if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                return abort(categories.HTTPResponse.FORBIDDEN.id)

        filepath = os.path.join(app.config["MEDIA_FOLDER"], file.path)
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return abort(categories.HTTPResponse.NOT_FOUND.id)
        
        with open(filepath, "rb") as f:
            data = f.read()

        response = make_response(data)
        response.headers["Content-Type"] = "application/octet-stream"
        response.headers["Content-Disposition"] = f"attachment; filename={file.name}{file.extension}"
        return response
    
    @login_manager.unauthorized_handler
    def unauthorized():
        next = url_for(request.endpoint, **request.view_args)   # type: ignore
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
            LibraryStatus=categories.LibraryStatus,
            UserRole=categories.UserRole,
            DataDeliveryMode=categories.DataDeliveryMode,
            GenomeRef=categories.GenomeRef,
            LibraryType=categories.LibraryType,
            PoolStatus=categories.PoolStatus,
            AssayType=categories.AssayType,
            SampleStatus=categories.SampleStatus,
            RunStatus=categories.RunStatus,
            SubmissionType=categories.SubmissionType,
            AttributeType=categories.AttributeType,
            IndexType=categories.IndexType,
            EventType=categories.EventType,
            PrepStatus=categories.PrepStatus,
            LabProtocol=categories.LabProtocol,
            PoolType=categories.PoolType,
            KitType=categories.KitType,
            ProjectStatus=categories.ProjectStatus,
            FileType=categories.FileType,
            SpreadSheetErrors=[InvalidCellValue(""), MissingCellValue(""), DuplicateCellValue("")],
            isna=pd.isna,
            notna=pd.notna,
        )
    
    @app.before_request
    def before_request():
        session["from_url"] = request.referrer

    @app.route("/status")
    def status():
        return make_response("OK", 200)
    
    app.register_blueprint(api.htmx.samples_htmx)
    app.register_blueprint(api.htmx.projects_htmx)
    app.register_blueprint(api.htmx.experiments_htmx)
    app.register_blueprint(api.htmx.pools_htmx)
    app.register_blueprint(api.htmx.auth_htmx)
    app.register_blueprint(api.htmx.barcodes_htmx)
    app.register_blueprint(api.htmx.seq_requests_htmx)
    app.register_blueprint(api.htmx.adapters_htmx)
    app.register_blueprint(api.htmx.sequencers_htmx)
    app.register_blueprint(api.htmx.users_htmx)
    app.register_blueprint(api.htmx.libraries_htmx)
    app.register_blueprint(api.htmx.feature_kits_htmx)
    app.register_blueprint(api.htmx.index_kits_htmx)
    app.register_blueprint(api.htmx.plates_htmx)
    app.register_blueprint(api.htmx.lanes_htmx)
    app.register_blueprint(api.htmx.seq_runs_htmx)
    app.register_blueprint(api.htmx.files_htmx)
    app.register_blueprint(api.htmx.lab_preps_htmx)
    app.register_blueprint(api.htmx.events_htmx)
    app.register_blueprint(api.htmx.groups_htmx)
    app.register_blueprint(api.htmx.kits_htmx)
    
    app.register_blueprint(api.plotting.plots_api)

    app.register_blueprint(api.workflows.library_annotation_workflow)
    app.register_blueprint(api.workflows.lane_pools_workflow)
    app.register_blueprint(api.workflows.ba_report_workflow)
    app.register_blueprint(api.workflows.select_experiment_pools_workflow)
    app.register_blueprint(api.workflows.dilute_pools_workflow)
    app.register_blueprint(api.workflows.check_barcode_clashes_workflow)
    app.register_blueprint(api.workflows.lane_qc_workflow)
    app.register_blueprint(api.workflows.load_flow_cell_workflow)
    app.register_blueprint(api.workflows.qubit_measure_workflow)
    app.register_blueprint(api.workflows.store_samples_workflow)
    app.register_blueprint(api.workflows.library_pooling_workflow)
    app.register_blueprint(api.workflows.library_prep_workflow)
    app.register_blueprint(api.workflows.mux_prep_workflow)
    app.register_blueprint(api.workflows.dist_reads_workflow)

    app.register_blueprint(pages.samples_page_bp)
    app.register_blueprint(pages.projects_page_bp)
    app.register_blueprint(pages.experiments_page_bp)
    app.register_blueprint(pages.libraries_page_bp)
    app.register_blueprint(pages.auth_page_bp)
    app.register_blueprint(pages.users_page_bp)
    app.register_blueprint(pages.seq_requests_page_bp)
    app.register_blueprint(pages.kits_page_bp)
    app.register_blueprint(pages.errors_bp)
    app.register_blueprint(pages.devices_page_bp)
    app.register_blueprint(pages.pools_page_bp)
    app.register_blueprint(pages.seq_runs_page_bp)
    app.register_blueprint(pages.lab_preps_page_bp)
    app.register_blueprint(pages.groups_page_bp)

    return app
