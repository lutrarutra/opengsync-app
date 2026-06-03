from typing import Literal, Final, ClassVar
from pydantic_settings import BaseSettings, SettingsConfigDict

import pytz

class Settings(BaseSettings):
    SECRET_KEY: str = ""
    TZ: str = "UTC"
    SESSION_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days
    ENVIRONMENT: Literal["dev", "prod", "test"] = "prod"

    # Database
    POSTGRES_USER: str = "codeflower"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_DB: str = "codeflower"
    POSTGRES_PORT: int = 5432
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    HETZNER_ACCESS_KEY: str = ""
    HETZNER_SECRET_KEY: str = ""

    CLOUDFLARE_R2_ACCESS_KEY: str = ""
    CLOUDFLARE_R2_SECRET_KEY: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_ACCESS_CLIENT_ID: str = ""
    CLOUDFLARE_ACCESS_CLIENT_SECRET: str = ""

    AWS_ACCESS_KEY: str = ""
    AWS_SECRET_KEY: str = ""

    GCS_ACCESS_KEY: str = ""
    GCS_SECRET_KEY: str = ""

    RESEND_API_KEY: str = ""
    EMAIL_SENDER: str = "CodeFlower <noreply@codeflower.com>"

    PROXMOX_HOST: str = ""
    PROXMOX_USER: str = "root@pam"
    PROXMOX_API_TOKEN_NAME: str = ""
    PROXMOX_API_TOKEN_VALUE: str = ""
    PROXMOX_PORT: int = 8006

    JWT_ALGORITHM: ClassVar[Final[str]] = "HS256"

    REGISTRY_URL: str = "registry:5000"
    
    BINARY_PACKAGE_MAX_SIZE_BYTES: int = 20 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def TIMEZONE(self) -> pytz.BaseTzInfo:
        return pytz.timezone(self.TZ)
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"


settings = Settings()