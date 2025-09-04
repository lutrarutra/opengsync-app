import os
import yaml
from uuid import uuid4

import pandas as pd

from flask import (
    Flask,
    redirect,
    request,
    url_for,
)

from flask_session import Session
from flask_session.base import ServerSideSession
from opengsync_db import categories, models, TIMEZONE

from .. import (
    logger,
    log_buffer,
    route_cache,
    msf_cache,
    flash_cache,
    session_cache,
    DEBUG,
    SECRET_KEY,
    htmx,
    bcrypt,
    login_manager,
    mail_handler,
    db,
    file_handler,
)
from ..tools import spread_sheet_components as ssc
from ..tools.utils import WeekTimeWindow
from ..routes import api, pages
from .. import tools


class App(Flask):
    static_folder: str
    template_folder: str
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

        self.root_folder = "/usr/src/app/"
        self.media_folder = tools.io.mkdir(os.path.join(self.root_folder, "media"))
        self.uploads_folder = tools.io.mkdir(os.path.join(self.root_folder, "uploads"))
        self.app_data_folder = tools.io.mkdir(os.path.join(self.root_folder, "app_data"))
        self.share_root = os.path.join(self.root_folder, "share")
        file_handler.init_app(
            media_folder=self.media_folder,
            uploads_folder=self.uploads_folder,
            app_data_folder=self.app_data_folder,
            share_root=self.share_root
        )
        
        self.debug = DEBUG
        self.timezone = TIMEZONE

        logger.info(f"MEDIA_FOLDER: {self.media_folder}")
        logger.info(f"UPLOADS_FOLDER: {self.uploads_folder}")
        logger.info(f"APP_DATA_FOLDER: {self.app_data_folder}")

        REDIS_PORT = int(os.environ["REDIS_PORT"])
        
        route_cache.init_app(self, config={"CACHE_TYPE": "redis", "CACHE_REDIS_URL": f"redis://redis-cache:{REDIS_PORT}/0"})
        msf_cache.connect("redis-cache", REDIS_PORT, 1)
        flash_cache.connect("redis-cache", REDIS_PORT, 2)

        for file_type in categories.MediaFileType.as_list():
            if file_type.dir is None:
                continue
            path = os.path.join(self.media_folder, file_type.dir)
            if not os.path.exists(path):
                os.makedirs(path)

        logger.info(f"DEBUG: {self.debug}")

        self.secret_key = SECRET_KEY

        self.config["SESSION_TYPE"] = "redis"
        self.config["SESSION_PERMANENT"] = False
        self.config["SESSION_USE_SIGNER"] = True
        self.config["SESSION_COOKIE_SECURE"] = False  # Set to True if your application is served over HTTPS
        self.config["SESSION_REDIS"] = session_cache

        Session(self)

        htmx.init_app(self)
        bcrypt.init_app(self)
        login_manager.init_app(self)
        mail_handler.init_app(
            smtp_server=os.environ["MAIL_SERVER"],
            smtp_port=int(os.environ["MAIL_PORT"]),
            smtp_user=os.environ["MAIL_USER"],
            sender_address=os.environ["MAIL_SENDER"],
            smtp_password=os.environ["MAIL_PASSWORD"],
        )

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

        self.lab_protocol_start_number = int(os.environ.get("LAB_PROTOCOL_START_NUMBER", 0))

        @login_manager.user_loader
        def load_user(user_id: int) -> models.User | None:
            if (user := db.users.get(user_id)) is None:
                logger.error(f"User not found: {user_id}")
                return None
            return user
        
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
                FileType=categories.MediaFileType,
                MUXType=categories.MUXType,
                DataPathType=categories.DataPathType,
                SpreadSheetErrors=[ssc.InvalidCellValue(""), ssc.MissingCellValue(""), ssc.DuplicateCellValue("")],
                isna=pd.isna,
                notna=pd.notna,
            )
        
        db.open_session()
        tools.utils.update_index_kits(db, self.app_data_folder)
        db.close_session()

        with self.app_context():
            from ..routes import core_routes  # noqa

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
        self.register_blueprint(api.workflows.relib_workflow)
        self.register_blueprint(api.workflows.share_project_data_workflow)

        self.register_blueprint(pages.samples_page_bp)
        self.register_blueprint(pages.projects_page_bp)
        self.register_blueprint(pages.experiments_page_bp)
        self.register_blueprint(pages.libraries_page_bp)
        self.register_blueprint(pages.auth_page_bp)
        self.register_blueprint(pages.users_page_bp)
        self.register_blueprint(pages.seq_requests_page_bp)
        self.register_blueprint(pages.kits_page_bp)
        self.register_blueprint(pages.devices_page_bp)
        self.register_blueprint(pages.pools_page_bp)
        self.register_blueprint(pages.seq_runs_page_bp)
        self.register_blueprint(pages.lab_preps_page_bp)
        self.register_blueprint(pages.groups_page_bp)
        self.register_blueprint(pages.share_tokens_page_bp)

        log_buffer.flush()

    def no_context_render_template(self, template_name: str, **context: dict) -> str:
        return self.jinja_env.get_template(template_name).render(**context)
    
    def consume_flashes(self, session: ServerSideSession) -> list[tuple[str, str]]:
        flashes = session.pop("_flashes") if "_flashes" in session else []
        return flashes
    
    def delete_user_sessions(self, user_id: int) -> str:
        lua_script = """
        local keys_to_delete = {}
        local session_keys = redis.call('KEYS', 'session:*')
        
        for i, key in ipairs(session_keys) do
            local session_data = redis.call('GET', key)
            if session_data then
                if string.find(session_data, '_user_id') and string.find(session_data, tostring(ARGV[1])) then
                    table.insert(keys_to_delete, key)
                end
            end
        end

        if #keys_to_delete > 0 then
            redis.call('DEL', unpack(keys_to_delete))
        end
        
        return #keys_to_delete
        """
        deleted_count = session_cache.eval(lua_script, 0, str(user_id))
        return deleted_count  # type: ignore