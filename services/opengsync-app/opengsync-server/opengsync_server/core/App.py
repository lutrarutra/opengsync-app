import os
import yaml
from uuid import uuid4

import pandas as pd

from flask import Flask, render_template, redirect, request, url_for, session, abort, make_response, flash
from flask_htmx import make_response as make_htmx_response

from opengsync_db import categories, models, TIMEZONE

from .. import logger, log_buffer, cache, msf_cache, DEBUG, SECRET_KEY, htmx, bcrypt, login_manager, mail, db
from ..tools import spread_sheet_components as ssc
from ..tools.utils import WeekTimeWindow
from ..routes import api, pages
from .. import tools
from . import wrappers


class App(Flask):
    sample_submission_windows: list[WeekTimeWindow] | None
    email_domain_white_list: list[str] | None
    lab_protocol_start_number: int
    root_folder: str
    media_folder: str
    uploads_folder: str
    app_data_folder: str
    share_root: str
    secret_key: str
    debug: bool

    def __init__(
        self,
        static_folder: str,
        template_folder: str,
        config_path: str
    ):
        log_buffer.start()

        if not os.path.exists(static_folder):
            raise FileNotFoundError(f"Static folder not found: {static_folder}")
        
        if not os.path.exists(template_folder):
            raise FileNotFoundError(f"Template folder not found: {template_folder}")
    
        super().__init__(__name__, static_folder=static_folder, template_folder=template_folder)

        self.root_folder = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))
        self.media_folder = tools.io.mkdir(os.path.join(self.root_folder, "media"))
        self.uploads_folder = tools.io.mkdir(os.path.join(self.root_folder, "uploads"))
        self.app_data_folder = tools.io.mkdir(os.path.join(self.root_folder, "app_data"))
        self.share_root = "/usr/src/app/share"
        self.debug = DEBUG
        self.timezone = TIMEZONE

        logger.info(f"MEDIA_FOLDER: {self.media_folder}")
        logger.info(f"UPLOADS_FOLDER: {self.uploads_folder}")
        logger.info(f"APP_DATA_FOLDER: {self.app_data_folder}")

        if (REDIS_PORT := os.environ["REDIS_PORT"]) is None:
            raise ValueError("REDIS_PORT env-variable not set")
        
        cache.init_app(self, config={"CACHE_TYPE": "redis", "CACHE_REDIS_URL": f"redis://redis-cache:{REDIS_PORT}/0"})
        msf_cache.connect("redis-cache", int(REDIS_PORT), 0)

        for file_type in categories.FileType.as_list():
            if file_type.dir is None:
                continue
            path = os.path.join(self.media_folder, file_type.dir)
            if not os.path.exists(path):
                os.makedirs(path)

        logger.info(f"DEBUG: {self.debug}")

        self.secret_key = SECRET_KEY

        self.config["MAIL_SERVER"] = "smtp-relay.sendinblue.com"
        self.config["MAIL_PORT"] = 587
        self.config["MAIL_USE_TLS"] = True

        self.config["MAIL_USERNAME"] = os.environ["EMAIL_USER"]
        self.config["MAIL_PASSWORD"] = os.environ["EMAIL_PASS"]

        htmx.init_app(self)
        bcrypt.init_app(self)
        login_manager.init_app(self)
        mail.init_app(self)
        db.connect(
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            db=os.environ["POSTGRES_DB"],
        )

        data = yaml.safe_load(open(config_path))
        if (windows := data.get("sample_submission_windows")):
            self.sample_submission_windows = tools.utils.parse_time_windows(windows)
        else:
            self.sample_submission_windows = None

        if (whitelist := data.get("email_domain_white_list")):
            self.email_domain_white_list = whitelist
        else:
            self.email_domain_white_list = None
            logger.warning("No email domain white list configured. All domains are allowed.")

        self.lab_protocol_start_number = data["lab_protocol_start_number"]

        if self.debug:
            import traceback
            from . import exceptions

            @self.errorhandler(Exception)
            def handle_exception(e: Exception):
                exc = e
                if e.__cause__:
                    exc = e.__cause__
                exc_tb = traceback.TracebackException(type(exc), exc, exc.__traceback__)
                for frame in exc_tb.stack:
                    try:
                        frame.filename = frame.filename.replace("/usr/src/app/", "")
                    except Exception:
                        pass
                    
                logger.error("".join(exc_tb.format()))
                log_buffer.flush()
                if isinstance(e, exceptions.HTMXException):
                    return make_htmx_response(render_template("errors/htmx_traceback.html", exc=exc_tb), 200, retarget="#debug-modal")
                return make_response(render_template("errors/traceback.html", exc=exc_tb))

        @login_manager.user_loader
        def load_user(user_id: int) -> models.User | None:
            if (user := db.get_user(user_id)) is None:
                logger.error(f"User not found: {user_id}")
                return None
            return user
        
        if self.debug:
            @wrappers.page_route(self, db=db)
            def test(current_user: models.User):
                logger.info(current_user)
                if tools.textgen is not None:
                    msg = tools.textgen.generate(
                        "You need to write in 1-2 sentences make a joke to greet user to my web self. \
                        Only raw text, no special characters (only punctuation , or . or !), no markdown, no code blocks, no quotes, no emojis, no links, no hashtags, no mentions. \
                        Just the joke text."
                    )
                    flash(msg, category="info")
                return render_template("test.html")
            
        @wrappers.page_route(self, login_required=False)
        @cache.cached(timeout=1500)
        def help():
            return render_template("help.html")
        
        @wrappers.page_route(self, db=db, route="/")
        def dashboard(current_user: models.User):
            if not current_user.is_authenticated:
                return redirect(url_for("auth_page.auth", next=url_for("dashboard")))
            
            if current_user.is_insider():
                return render_template("dashboard-insider.html")
            return render_template("dashboard-user.html")

        @wrappers.page_route(self, db=db)
        @cache.cached(timeout=60)
        def pdf_file(file_id: int, current_user: models.User):
            if (file := db.get_file(file_id)) is None:
                return abort(categories.HTTPResponse.NOT_FOUND.id)
            
            if file.uploader_id != current_user.id and not current_user.is_insider():
                if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                    return abort(categories.HTTPResponse.FORBIDDEN.id)
            
            if file.extension != ".pdf":
                return abort(categories.HTTPResponse.BAD_REQUEST.id)

            filepath = os.path.join(self.config["MEDIA_FOLDER"], file.path)
            if not os.path.exists(filepath):
                logger.error(f"File not found: {filepath}")
                return abort(categories.HTTPResponse.NOT_FOUND.id)
            
            with open(filepath, "rb") as f:
                data = f.read()

            response = make_response(data)
            response.headers["Content-Type"] = "application/pdf"
            response.headers["Content-Disposition"] = "inline; filename=auth_form.pdf"
            return response
        
        @wrappers.page_route(self, db=db)
        @cache.cached(timeout=60)
        def img_file(file_id: int, current_user: models.User):
            if (file := db.get_file(file_id)) is None:
                return abort(categories.HTTPResponse.NOT_FOUND.id)
            
            if file.uploader_id != current_user.id and not current_user.is_insider():
                if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                    return abort(categories.HTTPResponse.FORBIDDEN.id)
            
            if file.extension not in [".png", ".jpg", ".jpeg"]:
                return abort(categories.HTTPResponse.BAD_REQUEST.id)

            filepath = os.path.join(self.config["MEDIA_FOLDER"], file.path)
            if not os.path.exists(filepath):
                logger.error(f"File not found: {filepath}")
                return abort(categories.HTTPResponse.NOT_FOUND.id)
            
            with open(filepath, "rb") as f:
                data = f.read()

            response = make_response(data)
            response.headers["Content-Type"] = f"image/{file.extension[1:]}"
            response.headers["Content-Disposition"] = "inline; filename={file.name}"
            return response
        
        @wrappers.page_route(self, db=db)
        @cache.cached(timeout=60)
        def download_file(file_id: int, current_user: models.User):
            if (file := db.get_file(file_id)) is None:
                return abort(categories.HTTPResponse.NOT_FOUND.id)
            
            if file.uploader_id != current_user.id and not current_user.is_insider():
                if not db.file_permissions_check(user_id=current_user.id, file_id=file_id):
                    return abort(categories.HTTPResponse.FORBIDDEN.id)

            filepath = os.path.join(self.config["MEDIA_FOLDER"], file.path)
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
            return redirect(url_for("auth_page.auth", next=next))
        
        @self.context_processor
        def inject_debug():
            return dict(debug=self.debug)
        
        @self.context_processor
        def inject_uuid():
            return dict(uuid4=uuid4)
        
        from .jfilters import inject_jinja_format_filters
        inject_jinja_format_filters(self)

        @self.context_processor
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
                MUXType=categories.MUXType,
                SpreadSheetErrors=[ssc.InvalidCellValue(""), ssc.MissingCellValue(""), ssc.DuplicateCellValue("")],
                isna=pd.isna,
                notna=pd.notna,
            )
        
        @self.before_request
        def before_request():
            session["from_url"] = request.referrer

        @wrappers.page_route(self, login_required=False)
        def status():
            return make_response("OK", 200)
        
        db.open_session()
        tools.utils.update_index_kits(db, self.app_data_folder)
        db.close_session()
        
        self.register_blueprint(api.htmx.samples_htmx)
        self.register_blueprint(api.htmx.projects_htmx)
        self.register_blueprint(api.htmx.experiments_htmx)
        self.register_blueprint(api.htmx.pools_htmx)
        self.register_blueprint(api.htmx.auth_htmx)
        self.register_blueprint(api.htmx.barcodes_htmx)
        self.register_blueprint(api.htmx.seq_requests_htmx)
        self.register_blueprint(api.htmx.sequencers_htmx)
        self.register_blueprint(api.htmx.users_htmx)
        self.register_blueprint(api.htmx.libraries_htmx)
        self.register_blueprint(api.htmx.feature_kits_htmx)
        self.register_blueprint(api.htmx.index_kits_htmx)
        self.register_blueprint(api.htmx.plates_htmx)
        self.register_blueprint(api.htmx.lanes_htmx)
        self.register_blueprint(api.htmx.seq_runs_htmx)
        self.register_blueprint(api.htmx.files_htmx)
        self.register_blueprint(api.htmx.lab_preps_htmx)
        self.register_blueprint(api.htmx.events_htmx)
        self.register_blueprint(api.htmx.groups_htmx)
        self.register_blueprint(api.htmx.kits_htmx)
        self.register_blueprint(api.htmx.share_tokens_htmx)
        
        self.register_blueprint(api.plotting.plots_api)
        self.register_blueprint(api.files.file_share_bp)

        self.register_blueprint(api.workflows.library_annotation_workflow)
        self.register_blueprint(api.workflows.lane_pools_workflow)
        self.register_blueprint(api.workflows.ba_report_workflow)
        self.register_blueprint(api.workflows.select_experiment_pools_workflow)
        self.register_blueprint(api.workflows.dilute_pools_workflow)
        self.register_blueprint(api.workflows.check_barcode_clashes_workflow)
        self.register_blueprint(api.workflows.lane_qc_workflow)
        self.register_blueprint(api.workflows.load_flow_cell_workflow)
        self.register_blueprint(api.workflows.qubit_measure_workflow)
        self.register_blueprint(api.workflows.store_samples_workflow)
        self.register_blueprint(api.workflows.library_pooling_workflow)
        self.register_blueprint(api.workflows.library_prep_workflow)
        self.register_blueprint(api.workflows.mux_prep_workflow)
        self.register_blueprint(api.workflows.dist_reads_workflow)
        self.register_blueprint(api.workflows.reindex_workflow)
        self.register_blueprint(api.workflows.reseq_workflow)
        self.register_blueprint(api.workflows.merge_pools_workflow)
        self.register_blueprint(api.workflows.select_pool_libraries_workflow)
        self.register_blueprint(api.workflows.library_remux_workflow)

        self.register_blueprint(pages.samples_page_bp)
        self.register_blueprint(pages.projects_page_bp)
        self.register_blueprint(pages.experiments_page_bp)
        self.register_blueprint(pages.libraries_page_bp)
        self.register_blueprint(pages.auth_page_bp)
        self.register_blueprint(pages.users_page_bp)
        self.register_blueprint(pages.seq_requests_page_bp)
        self.register_blueprint(pages.kits_page_bp)
        self.register_blueprint(pages.errors_bp)
        self.register_blueprint(pages.devices_page_bp)
        self.register_blueprint(pages.pools_page_bp)
        self.register_blueprint(pages.seq_runs_page_bp)
        self.register_blueprint(pages.lab_preps_page_bp)
        self.register_blueprint(pages.groups_page_bp)
        self.register_blueprint(pages.share_tokens_page_bp)

        log_buffer.flush()
