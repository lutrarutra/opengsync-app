import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from opengsync_db import SyncDBHandler, SyncSession, queries as Q
from opengsync_db.models.Base import Base
from opengsync_db.categories import UserRole

PASSWORD = "testpassword"


@pytest.fixture(scope="function")  # type: ignore[attr-defined]
def _db_handler():
    db_name = f"db{uuid.uuid4().hex}"
    engine = sa.create_engine(SyncDBHandler.AdminURL(
        user="admin", password="password", host="postgres", port=5434, db="postgres"
    ))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sa.text(f"CREATE DATABASE {db_name}"))
    engine.dispose()

    db = SyncDBHandler(auto_open=False, expire_on_commit=False, auto_commit=True)
    db.connect(user="admin", password="password", host="postgres", port=5434, db=db_name)
    with db._engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        db.info("Created pg_trgm extension")

        Base.metadata.create_all(conn)
        db.info("Successfully created all tables")
    db.open_session()
    yield db
    db.close_session()


@pytest.fixture(scope="function")  # type: ignore[attr-defined]
def session(_db_handler: SyncDBHandler) -> SyncSession:
    return _db_handler.session


def _ensure_backend_on_path() -> None:
    try:
        import server  # noqa: F401
        return
    except ImportError:
        pass
    candidates = [
        Path("/app/services/backend"),
        Path(__file__).resolve().parents[2] / "backend",
    ]
    for path in candidates:
        if (path / "server").is_dir():
            sys.path.insert(0, str(path))
            return


def _ensure_app_dirs() -> None:
    for directory in ("/static", "/templates", "/logs"):
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def _inject_test_app_config() -> None:
    from server.core.config import (
        settings, AppConfig, Personalization, DBConfig, SchedulerConfig,
    )

    try:
        settings.app_config
    except RuntimeError:
        settings.inject_app_config(AppConfig(
            personalization=Personalization(organization="Test Org", email="test@example.com"),
            db=DBConfig(lab_protocol_start_number=1),
            app_root="/app",
            media_folder="/media",
            uploads_folder="/uploads",
            app_data_folder="/app-data",
            share_root="/share",
            static_folder="/static",
            template_folder="/templates",
            log_folder="/logs",
            illumina_run_folder="/illumina",
            scheduler=SchedulerConfig(
                upload_folder_file_age_days=7,
                upload_folder_clean_schedule="0 0 * * *",
                rf_scan_interval_min=60,
                status_update_interval_min=60,
            ),
        ))
    if not settings.SECRET_KEY:
        settings.SECRET_KEY = "test-secret-key-for-pytest"


class _DummyMailer:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None
        return _noop


@pytest.fixture(scope="function")  # type: ignore[attr-defined]
def client(_db_handler: SyncDBHandler):
    """FastAPI TestClient bound to the per-test database."""
    _ensure_app_dirs()
    _ensure_backend_on_path()
    _inject_test_app_config()

    from fastapi.testclient import TestClient
    from redis import ConnectionPool

    from server.main import app
    from server.core import config, secrets, templates

    @asynccontextmanager
    async def test_lifespan(app_):
        app_.state.db_handler = _db_handler
        app_.state.mailer = _DummyMailer()
        app_.state.redis_pool = ConnectionPool.from_url(config.settings.REDIS_URL)
        app_.state.bcrypt = secrets.BcryptCompat()
        templates.j2.env.globals["contact_email"] = config.settings.app_config.personalization.email
        templates.j2.env.globals["organization_name"] = config.settings.app_config.personalization.organization
        yield
        app_.state.redis_pool.disconnect()

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = test_lifespan
    try:
        with TestClient(app) as test_client:
            from redis import Redis
            Redis(connection_pool=test_client.app.state.redis_pool).flushdb()
            yield test_client
            Redis(connection_pool=test_client.app.state.redis_pool).flushdb()
    finally:
        app.router.lifespan_context = original_lifespan


def _create_test_user(session: SyncSession, *, email: str, role: UserRole):
    from server.core.secrets import BcryptCompat

    user = session.save(Q.user.create(
        email=email,
        hashed_password=BcryptCompat().generate_password_hash(PASSWORD),
        first_name="Test",
        last_name=role.name.title(),
        role=role,
    ), flush=True)
    session.commit()
    return user


def _login_token(user) -> str:
    from server.core import config, secrets
    if not config.settings.SECRET_KEY:
        config.settings.SECRET_KEY = "test-secret-key-for-pytest"
    return secrets.create_login_token(user)


@pytest.fixture  # type: ignore[attr-defined]
def user(session: SyncSession):
    _ensure_backend_on_path()
    return _create_test_user(session, email="user@example.com", role=UserRole.CLIENT)


@pytest.fixture  # type: ignore[attr-defined]
def user_2(session: SyncSession):
    _ensure_backend_on_path()
    return _create_test_user(session, email="user2@example.com", role=UserRole.CLIENT)


@pytest.fixture  # type: ignore[attr-defined]
def insider(session: SyncSession):
    _ensure_backend_on_path()
    return _create_test_user(session, email="insider@example.com", role=UserRole.TECHNICIAN)


@pytest.fixture  # type: ignore[attr-defined]
def admin(session: SyncSession):
    _ensure_backend_on_path()
    return _create_test_user(session, email="admin@example.com", role=UserRole.ADMIN)


@pytest.fixture  # type: ignore[attr-defined]
def user_token(client, user) -> str:
    return _login_token(user)


@pytest.fixture  # type: ignore[attr-defined]
def user_2_token(client, user_2) -> str:
    return _login_token(user_2)


@pytest.fixture  # type: ignore[attr-defined]
def insider_token(client, insider) -> str:
    return _login_token(insider)


@pytest.fixture  # type: ignore[attr-defined]
def admin_token(client, admin) -> str:
    return _login_token(admin)
