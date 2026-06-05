from typing import Literal
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

import pytz

class Personalization(BaseModel):
    organization: str
    email: str
    internal_share_template: str | None = None


class SampleSubmissionWindow(BaseModel):
    weekday: int
    start_time: str
    end_time: str


class DBConfig(BaseModel):
    lab_protocol_start_number: int


class SharePathMapping(BaseModel):
    BSF_PROJECTS: str
    BSF_SEQUENCES: str
    BSF_SEQUENCES_10X: str


class SchedulerConfig(BaseModel):
    upload_folder_file_age_days: int
    upload_folder_clean_schedule: str
    rf_scan_interval_min: int
    status_update_interval_min: int


class AppConfig(BaseModel):
    """Pydantic model for opengsync.yaml"""
    personalization: Personalization
    sample_submission_windows: list[SampleSubmissionWindow] = []
    email_domain_white_list: list[str] = []
    external_base_url: str | None = None
    db: DBConfig
    share_path_mapping: SharePathMapping
    canary_files: dict[str, str] = dict()
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

class Settings(BaseSettings):
    SECRET_KEY: str = ""
    TZ: str = "UTC"
    SESSION_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days
    ENVIRONMENT: Literal["dev", "prod", "test"] = "prod"

    MAIL_SERVER: str = ""
    MAIL_PORT: int = 587
    MAIL_USER: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_SENDER: str = ""

    # Database
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_DB: str = "codeflower"
    POSTGRES_PORT: int = 5432
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    JWT_ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def TIMEZONE(self) -> pytz.BaseTzInfo:
        return pytz.timezone(self.TZ)
    
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