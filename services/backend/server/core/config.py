import os
from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def secret_value(value: SecretStr | str) -> str:
    """The plain value of a secret. Call it only where the value is handed to the library that needs it."""
    return value.get_secret_value() if isinstance(value, SecretStr) else value


class Personalization(BaseModel):
    organization: str
    email: str
    internal_share_template: str | None = None


class SampleSubmissionWindow(BaseModel):
    weekday: int
    start_time: time
    end_time: time


class DBConfig(BaseModel):
    lab_protocol_start_number: int


class SchedulerConfig(BaseModel):
    upload_folder_file_age_days: int
    upload_folder_clean_schedule: str
    rf_scan_interval_min: int
    status_update_interval_min: int
    # Non-admin users who have not logged in for this many days are set to DEACTIVATED.
    user_inactivity_days: int = 365
    user_deactivation_schedule: str = "0 2 * * *"


class ChatConfig(BaseModel):
    enabled: bool = False
    # "test" = offline echo model (no LLM). Otherwise a pydantic-ai model string, e.g. "openai:gpt-4.1-mini"
    # (hosted providers read their standard env var, e.g. OPENAI_API_KEY / ANTHROPIC_API_KEY),
    # or, together with `base_url`, the model name served by an OpenAI-compatible endpoint (vLLM, Ollama, ...)
    model: str = "test"
    base_url: str | None = None
    # vLLM extension (only used with `base_url`): the endpoint sends cumulative usage in every streamed chunk.
    # Enable for vLLM; other endpoints reject the unknown `stream_options.continuous_usage_stats` parameter
    continuous_usage_stats: bool = False
    history_ttl_hours: int = 72
    max_history_turns: int = 5  # questions (with answers) kept: shown in the widget and sent back to the model
    max_requests_per_turn: int = 25  # model requests per reply, each tool-call round trip counts as one


class ExperimentStatsConfig(BaseModel):
    # sequenced / planned reads of a pool (%) outside these bounds is flagged on the experiment stats tab
    under_planned_pct: float = 80.0
    over_planned_pct: float = 150.0
    # share of undetermined reads (%) above which the stats tab warns
    undetermined_warn_pct: float = 10.0


class FsIndexConfig(BaseModel):
    """SQLite search index over share_root, written by the worker (opengsync_worker.tasks.fs_index_*)."""
    enabled: bool = False
    # defaults: <app_data_folder>/fs_index/fs_index.sqlite3 and <app_data_folder>/fs_index/dumps
    db_file: str | None = None
    dump_dir: str | None = None
    # seconds or a 5-field cron string
    import_schedule: int | str = 600
    crawl_schedule: int | str = 60
    crawl_budget_s: int = 50
    crawl_batch: int = 500
    crawl_threads: int = 1
    # folders checked per second, all threads together (0: no limit); keeps the load on the share's metadata server low
    crawl_rate: float = 10
    min_interval_s: int = 120
    max_interval_s: int = 7 * 24 * 3600
    # directory names whose contents are not indexed (still counted in folder sizes); None: worker defaults
    index_ignore: list[str] | None = None

    def db_path(self, app_data_folder: str) -> str:
        return self.db_file or os.path.join(app_data_folder, "fs_index", "fs_index.sqlite3")

    def dump_path(self, app_data_folder: str) -> str:
        return self.dump_dir or os.path.join(app_data_folder, "fs_index", "dumps")


class AppConfig(BaseModel):
    """Pydantic model for opengsync.yaml"""
    personalization: Personalization
    sample_submission_windows: list[SampleSubmissionWindow] = []
    email_domain_white_list: list[str] = []
    external_base_url: str | None = None
    db: DBConfig
    share_path_mapping: dict[str, str] | None = None
    canary_files: dict[str, str] = {}
    app_root: str
    media_folder: str
    uploads_folder: str
    app_data_folder: str
    share_root: str
    static_folder: str
    template_folder: str
    log_folder: str
    illumina_run_folder: str
    scheduler: SchedulerConfig
    chat: ChatConfig = ChatConfig()
    experiment_stats: ExperimentStatsConfig = ExperimentStatsConfig()
    fs_index: FsIndexConfig = FsIndexConfig()


class Settings(BaseSettings):
    SECRET_KEY: SecretStr = SecretStr("")
    TZ: str = "UTC"
    SESSION_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days
    ENVIRONMENT: Literal["dev", "prod", "test"] = "prod"

    MAIL_SERVER: str = ""
    MAIL_PORT: int = 587
    MAIL_USER: str = ""
    MAIL_PASSWORD: SecretStr = SecretStr("")
    MAIL_SENDER: str = ""

    # Database
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: SecretStr = SecretStr("password")
    POSTGRES_HOST: str = "localhost"
    POSTGRES_DB: str = "codeflower"
    POSTGRES_PORT: int = 5432
    
    # Redis
    REDIS_HOST: str = "redis-cache"
    REDIS_PORT: int = 6379

    JWT_ALGORITHM: str = "HS256"

    # API key for chat.base_url (OpenAI-compatible endpoint)
    CHAT_API_KEY: SecretStr = SecretStr("")

    # WebAuthn / passkeys. RP ID must be the (registrable) domain users see, e.g. "lims.example.org".
    # Changing it later invalidates every registered passkey. Empty = derive from the request host.
    WEBAUTHN_RP_ID: str = ""
    WEBAUTHN_RP_NAME: str = "OpeNGSync"
    # Comma-separated allowed origins, e.g. "https://lims.example.org". Empty = derive from the request.
    WEBAUTHN_ORIGINS: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    _app_config: AppConfig | None = PrivateAttr(default=None)

    @property
    def TIMEZONE(self) -> ZoneInfo:
        return ZoneInfo(self.TZ)

    def now(self) -> datetime:
        return datetime.now(self.TIMEZONE)

    def datetime(
        self,
        year: int,
        month: int,
        day: int = 1,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
    ) -> datetime:
        return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=self.TIMEZONE)

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"
    
    def inject_app_config(self, cfg: AppConfig) -> None:
        self._app_config = cfg

    @property
    def app_config(self) -> AppConfig:
        if self._app_config is None:
            raise RuntimeError("AppConfig has not been injected. Load it during startup.")
        return self._app_config


settings = Settings()