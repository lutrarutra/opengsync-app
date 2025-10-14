import os
import yaml
from uuid import uuid4
from pathlib import Path

import pandas as pd

from flask import (
    Flask,
    redirect,
    request,
    url_for,
)
from jinja2 import StrictUndefined
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
    limiter,
)
from ..tools import spread_sheet_components as ssc
from ..tools.utils import WeekTimeWindow
from .. import routes
from .. import tools


class App(Flask):
    static_folder: str
    template_folder: str
    root_folder: Path
    media_folder: Path
    uploads_folder: Path
    app_data_folder: Path
    share_root: Path
    sample_submission_windows: list[WeekTimeWindow] | None
    email_domain_white_list: list[str] | None
    secret_key: str
    share_path_mapping: dict[str, str]
    debug: bool
    personalization: dict

    def __init__(self, config_path: str):
        opengsync_config = yaml.safe_load(open(config_path))
        super().__init__(__name__, static_folder=opengsync_config["static_folder"], template_folder=opengsync_config["template_folder"])

        if DEBUG:
            self.jinja_env.undefined = StrictUndefined

        self.jinja_env.globals["uuid"] = lambda: str(uuid4())
        log_buffer.set_log_dir(Path(opengsync_config["log_folder"]))
        log_buffer.start()

        self.root_folder = Path(opengsync_config["app_root"])
        self.share_root = Path(opengsync_config["share_root"])
        self.media_folder = Path(opengsync_config["media_folder"])
        self.uploads_folder = Path(opengsync_config["uploads_folder"])
        self.app_data_folder = Path(opengsync_config["app_data_folder"])
        self.share_path_mapping = opengsync_config.get("share_path_mapping", {})
        self.personalization = opengsync_config["personalization"]

        if not os.path.exists(self.static_folder):
            raise FileNotFoundError(f"Static folder not found: {self.static_folder}")

        if not os.path.exists(self.template_folder):
            raise FileNotFoundError(f"Template folder not found: {self.template_folder}")

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
        self.config["SESSION_COOKIE_SECURE"] = False  # True does not work, at least not without https
        self.config["SESSION_REDIS"] = session_cache

        Session(self)

        htmx.init_app(self)
        bcrypt.init_app(self)
        login_manager.init_app(self)
        limiter.init_app(self)
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

        if (windows := opengsync_config.get("sample_submission_windows")):
            self.sample_submission_windows = tools.utils.parse_time_windows(windows)
        else:
            self.sample_submission_windows = None

        if (whitelist := opengsync_config.get("email_domain_white_list")):
            self.email_domain_white_list = whitelist
        else:
            self.email_domain_white_list = None
            logger.warning("No email domain white list configured. All domains are allowed.")

        db.lab_protocol_start_number = int(opengsync_config["db"]["lab_protocol_start_number"])

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
        def inject_defaults():
            return dict(
                current_query=None,
                path_list=[],
                context={},
                sort_by=None,
                sort_order=None,
                active_query_field=None,
                active_page=0,
                n_pages=None,
                next=None,
                contact_email=self.personalization["email"],
                organization_name=self.personalization["organization"],
            )

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
                AffiliationType=categories.AffiliationType,
                ProjectStatus=categories.ProjectStatus,
                FileType=categories.MediaFileType,
                MUXType=categories.MUXType,
                DataPathType=categories.DataPathType,
                ExperimentWorkFlow=categories.ExperimentWorkFlow,
                SpreadSheetErrors=[ssc.InvalidCellValue(""), ssc.MissingCellValue(""), ssc.DuplicateCellValue("")],
                isna=pd.isna,
                notna=pd.notna,
            )

        db.open_session()
        tools.utils.update_index_kits(db, self.app_data_folder)
        db.close_session()

        with self.app_context():
            from ..routes import core_routes  # noqa

        self.register_blueprint(routes.htmx.samples_htmx)
        self.register_blueprint(routes.htmx.projects_htmx)
        self.register_blueprint(routes.htmx.experiments_htmx)
        self.register_blueprint(routes.htmx.pools_htmx)
        self.register_blueprint(routes.htmx.auth_htmx)
        self.register_blueprint(routes.htmx.barcodes_htmx)
        self.register_blueprint(routes.htmx.seq_requests_htmx)
        self.register_blueprint(routes.htmx.sequencers_htmx)
        self.register_blueprint(routes.htmx.users_htmx)
        self.register_blueprint(routes.htmx.libraries_htmx)
        self.register_blueprint(routes.htmx.feature_kits_htmx)
        self.register_blueprint(routes.htmx.index_kits_htmx)
        self.register_blueprint(routes.htmx.plates_htmx)
        self.register_blueprint(routes.htmx.lanes_htmx)
        self.register_blueprint(routes.htmx.seq_runs_htmx)
        self.register_blueprint(routes.htmx.files_htmx)
        self.register_blueprint(routes.htmx.lab_preps_htmx)
        self.register_blueprint(routes.htmx.events_htmx)
        self.register_blueprint(routes.htmx.groups_htmx)
        self.register_blueprint(routes.htmx.kits_htmx)
        self.register_blueprint(routes.htmx.share_tokens_htmx)

        self.register_blueprint(routes.plotting.plots_api)
        self.register_blueprint(routes.files.file_share_bp)
        self.register_blueprint(routes.files.webdav_bp)

        self.register_blueprint(routes.workflows.library_annotation_workflow)
        self.register_blueprint(routes.workflows.lane_pools_workflow)
        self.register_blueprint(routes.workflows.ba_report_workflow)
        self.register_blueprint(routes.workflows.select_experiment_pools_workflow)
        self.register_blueprint(routes.workflows.dilute_pools_workflow)
        self.register_blueprint(routes.workflows.check_barcode_clashes_workflow)
        self.register_blueprint(routes.workflows.lane_qc_workflow)
        self.register_blueprint(routes.workflows.load_flow_cell_workflow)
        self.register_blueprint(routes.workflows.qubit_measure_workflow)
        self.register_blueprint(routes.workflows.store_samples_workflow)
        self.register_blueprint(routes.workflows.library_pooling_workflow)
        self.register_blueprint(routes.workflows.library_prep_workflow)
        self.register_blueprint(routes.workflows.mux_prep_workflow)
        self.register_blueprint(routes.workflows.dist_reads_workflow)
        self.register_blueprint(routes.workflows.reindex_workflow)
        self.register_blueprint(routes.workflows.reseq_workflow)
        self.register_blueprint(routes.workflows.merge_pools_workflow)
        self.register_blueprint(routes.workflows.select_pool_libraries_workflow)
        self.register_blueprint(routes.workflows.library_remux_workflow)
        self.register_blueprint(routes.workflows.relib_workflow)
        self.register_blueprint(routes.workflows.share_project_data_workflow)
        self.register_blueprint(routes.workflows.billing_workflow)
        self.register_blueprint(routes.workflows.check_barcode_constraints_workflow)

        self.register_blueprint(routes.pages.samples_page_bp)
        self.register_blueprint(routes.pages.projects_page_bp)
        self.register_blueprint(routes.pages.experiments_page_bp)
        self.register_blueprint(routes.pages.libraries_page_bp)
        self.register_blueprint(routes.pages.auth_page_bp)
        self.register_blueprint(routes.pages.users_page_bp)
        self.register_blueprint(routes.pages.seq_requests_page_bp)
        self.register_blueprint(routes.pages.kits_page_bp)
        self.register_blueprint(routes.pages.devices_page_bp)
        self.register_blueprint(routes.pages.pools_page_bp)
        self.register_blueprint(routes.pages.seq_runs_page_bp)
        self.register_blueprint(routes.pages.lab_preps_page_bp)
        self.register_blueprint(routes.pages.groups_page_bp)
        self.register_blueprint(routes.pages.share_tokens_page_bp)
        self.register_blueprint(routes.pages.browser_page_bp)

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
