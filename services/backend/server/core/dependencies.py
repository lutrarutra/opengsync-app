import json
from uuid import UUID
import hashlib

from fastapi import Depends, BackgroundTasks, Request, Header, Cookie, Query
from starlette.background import BackgroundTask
from redis.asyncio import Redis, ConnectionPool
from fastapi_cache import FastAPICache
import sqlalchemy as sa
from taskiq import TaskiqDepends

from sqlalchemy.orm import make_transient_to_detached

from opengsync_db import queries as Q, AsyncSession, exceptions as db_exc, models, categories as C, utils

from . import mailer, audit, auth, exceptions as exc, secrets, runtime, cache

def get_runtime_request(request: Request = TaskiqDepends()) -> runtime.Request:
    return request  # type: ignore

async def db_session(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    async with request.app.state.db_handler.get_session() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        
async def authenticate(token: str = Depends(auth.oauth2_scheme)):
    payload = secrets.validate_login_token(token)
    return payload

async def __get_cached_user(key: str, r: Redis):
    if (cached_user_str := await r.get(key)) is not None:
        user_data = json.loads(cached_user_str)
        user_data["id"] = UUID(user_data["id"])

        user = models.User(**user_data)
        make_transient_to_detached(user)
        return user
    
async def _resolve_user(
    auth_response: auth.AuthResponse,
    background_tasks: BackgroundTasks,
    request: runtime.Request,
    session: AsyncSession,
) -> models.User | None:
    """Shared helper to fetch user from cache or DB and schedule cache updates."""
    async with Redis(connection_pool=request.app.state.redis_pool) as redis:
        if (user := await __get_cached_user(f"user:{auth_response.id}", redis)) is not None:
            return user

    if (user := await session.first(
        Q.user.select(id=auth_response.id),
    )) is None:
        return None
    
    # async def __cache_current_user(user_obj: models.User, pool: ConnectionPool):
    #     async with Redis(connection_pool=pool) as r:
    #         await r.set(f"user:{user_obj.id}", json.dumps(user_obj.to_dict()), ex=300)

    # task = BackgroundTask(
    #     __cache_current_user,
    #     user_obj=user,
    #     pool=request.app.state.redis_pool
    # )
    # background_tasks.add_task(task)
    return user

async def _resolve_user_by_api_token(
    token: str,
    background_tasks: BackgroundTasks,
    request: runtime.Request,
    session: AsyncSession,
) -> models.User | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cache_key = f"api_token:{token_hash}"
    
    async with Redis(connection_pool=request.app.state.redis_pool) as redis:
        if (cached_user_id := await redis.get(cache_key)) is not None:
            user_id_str = cached_user_id.decode("utf-8")
            if (user := await __get_cached_user(f"user:{user_id_str}", redis)) is not None:
                return user
            
    # hint = token[-models.APIToken.HINT_SIZE:]
    user = None
    # for db_token in await session.get_all(
    #     Q.api_token.select(hint=hint, is_valid=True),
    #     options=[joinedload(models.APIToken.user).joinedload(models.User.avatar)],
    #     limit=None
    # ):
    #     if secrets.verify_api_token(token, db_token.token_hash):
    #         user = db_token.user
    #         break
        
    if not user:
        return None
    
    # async def __cache_api_token_mapping(user_obj: models.User, cached_key_name: str, pool: ConnectionPool):
    #     async with Redis(connection_pool=pool) as r:
    #         await r.set(cached_key_name, str(user_obj.id), ex=300)
    #         await r.set(f"user:{user_obj.id}", json.dumps(user_obj.to_dict()), ex=300)

    # task = BackgroundTask(
    #     __cache_api_token_mapping,
    #     user_obj=user,
    #     cached_key_name=cache_key,
    #     pool=request.app.state.redis_pool
    # )
    # background_tasks.add_task(task)
    
    return user

async def get_user(
    background_tasks: BackgroundTasks,
    request: runtime.Request = TaskiqDepends(),
    session: AsyncSession = Depends(db_session),
    token: str | None = Depends(auth.optional_oauth2_scheme),
    api_token: str | None = Header(None, alias="X-API-Token"),
    access_token: str | None = Cookie(None)
) -> models.User | None:
    """Returns the current user if authenticated, or None otherwise."""

    if getattr(request.state, "current_user", runtime.NOT_CHECKED) != runtime.NOT_CHECKED:
        return request.state.current_user  # type: ignore
    
    if not token:
        token = access_token
        
    if token:
        try:
            payload = secrets.validate_login_token(token)
            auth_response = auth.AuthResponse.model_validate(payload)
        except exc.HTTPException:
            request.state.current_user = None
            return None
        user = await _resolve_user(auth_response, background_tasks, request, session)
    elif api_token:        
        if not api_token.startswith("cf-"):
            raise exc.HTTPException(status_code=409, detail="Invalid API Token. API tokens must start with 'cf-'.")
        
        user = await _resolve_user_by_api_token(api_token, background_tasks, request, session)
    else:
        user = None

    if not user:
        request.state.current_user = None
        return None
    
    if user.role == C.UserRole.DEACTIVATED:
        raise exc.HTTPException(status_code=403, detail="User account is suspended")
    
    request.state.current_user = user
    return user


async def require_user(
    user: models.User | None = Depends(get_user),
) -> models.User:
    if not user:
        raise exc.UserNotAuthenticatedException()
    return user

async def require_admin(
    user: models.User = Depends(require_user),
):
    if user.role < C.UserRole.ADMIN:
        raise exc.HTTPException(status_code=403, detail="Admin privileges required")
    return user

async def require_insider(
    user: models.User = Depends(require_user),
):
    if not user.is_insider():
        raise exc.NoPermissionsException()
    return user

def mail_client(request: runtime.Request = TaskiqDepends(get_runtime_request)) -> mailer.Mailer:
    return request.app.state.mailer

def get_bcrypt(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    return request.app.state.bcrypt

def audit_log(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    request.state.audit = audit.AuditLogger(request)
    return request.state.audit

async def redis(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    async with Redis(connection_pool=request.app.state.redis_pool) as redis:
        yield redis

async def invalidate_cache(request: runtime.Request):
    substrings: list[str] = []
    yield substrings

    if not substrings:
        return

    prefix = FastAPICache.get_prefix()
    for substring in substrings:
        pattern = f"{prefix}:*:{substring}:*"
        await cache.scan_and_delete(pattern=pattern, redis_pool=request.app.state.redis_pool)


async def project_permissions(
    project_id: int,
    user: models.User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    r: Redis = Depends(redis),
):
    cache_key = f"access:project:{project_id}:user:{user.id}"
    if (cached_access := await r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))
    try:
        if (access_level := await session.get_access_level(Q.project.permissions(project_id=project_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this project.")
    except db_exc.ModelNotFoundException:
        raise exc.ItemNotFoundException("Project not found.")

    await r.set(cache_key, int(access_level), ex=300)
    return access_level

async def seq_request_permissions(
    seq_request_id: int,
    user: models.User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    r: Redis = Depends(redis),
):
    cache_key = f"access:seq_request:{seq_request_id}:user:{user.id}"
    if (cached_access := await r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))
    try:
        if (access_level := await session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this sequencing request.")
    except db_exc.ModelNotFoundException:
        raise exc.ItemNotFoundException("Sequencing request not found.")

    await r.set(cache_key, int(access_level), ex=300)
    return access_level

async def sample_permissions(
    sample_id: int,
    user: models.User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    r: Redis = Depends(redis),
):
    cache_key = f"access:sample:{sample_id}:user:{user.id}"
    if (cached_access := await r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))
    try:
        if (access_level := await session.get_access_level(Q.sample.permissions(sample_id=sample_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this sample.")
    except db_exc.ModelNotFoundException:
        raise exc.ItemNotFoundException("Sample not found.")

    await r.set(cache_key, int(access_level), ex=300)
    return access_level

async def library_permissions(
    library_id: int,
    user: models.User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    r: Redis = Depends(redis),
):
    cache_key = f"access:library:{library_id}:user:{user.id}"
    if (cached_access := await r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))
    try:
        if (access_level := await session.get_access_level(Q.library.permissions(library_id=library_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this library.")
    except db_exc.ModelNotFoundException:
        raise exc.ItemNotFoundException("Library not found.")

    await r.set(cache_key, int(access_level), ex=300)
    return access_level

async def pool_permissions(
    pool_id: int,
    user: models.User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    r: Redis = Depends(redis),
):
    cache_key = f"access:pool:{pool_id}:user:{user.id}"
    if (cached_access := await r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))
    try:
        if (access_level := await session.get_access_level(Q.pool.permissions(pool_id=pool_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this pool.")
    except db_exc.ModelNotFoundException:
        raise exc.ItemNotFoundException("Pool not found.")

    await r.set(cache_key, int(access_level), ex=300)
    return access_level


def parse_project_status_ids(
    status_in: str | None = Query(None, description="JSON list of project status IDs to filter by")
) -> list[C.ProjectStatus] | None:
    if status_in is None:
        return None
    
    try:
        status_ids = json.loads(status_in)
        return [C.ProjectStatus.get(int(status)) for status in status_ids]
    except ValueError:
        raise exc.BadRequestException()

def parse_library_type_ids(
    library_types_in: str | None = Query(None, description="JSON list of library type IDs to filter by")
) -> list[C.LibraryType] | None:
    if library_types_in is None:
        return None
    
    try:
        library_type_ids = json.loads(library_types_in)
        return [C.LibraryType.get(int(library_type)) for library_type in library_type_ids]
    except ValueError:
        raise exc.BadRequestException()
    
def parse_sample_status_ids(
    status_in: str | None = Query(None, description="JSON list of sample status IDs to filter by")
) -> list[C.SampleStatus] | None:
    if status_in is None:
        return None
    
    try:
        status_ids = json.loads(status_in)
        return [C.SampleStatus.get(int(status)) for status in status_ids]
    except ValueError:
        raise exc.BadRequestException()
    
def parse_seq_request_status_ids(
    status_in: str | None = Query(None, description="JSON list of sequencing request status IDs to filter by")
) -> list[C.SeqRequestStatus] | None:
    if status_in is None:
        return None
    
    try:
        status_ids = json.loads(status_in)
        return [C.SeqRequestStatus.get(int(status)) for status in status_ids]
    except ValueError:
        raise exc.BadRequestException()

def parse_experiment_status_ids(
    status_in: str | None = Query(None, description="JSON list of experiment status IDs to filter by")
) -> list[C.ExperimentStatus] | None:
    if status_in is None:
        return None
    
    try:
        status_ids = json.loads(status_in)
        return [C.ExperimentStatus.get(int(status)) for status in status_ids]
    except ValueError:
        raise exc.BadRequestException()

def parse_experiment_workflow_ids(
    workflow_in: str | None = Query(None, description="JSON list of experiment workflow IDs to filter by")
) -> list[C.ExperimentWorkFlow] | None:
    if workflow_in is None:
        return None
    
    try:
        workflow_ids = json.loads(workflow_in)
        return [C.ExperimentWorkFlow.get(int(workflow)) for workflow in workflow_ids]
    except ValueError:
        raise exc.BadRequestException()

def parse_user_role_ids(
    role_in: str | None = Query(None, description="JSON list of user role IDs to filter by")
) -> list[C.UserRole] | None:
    if role_in is None:
        return None
    
    try:
        role_ids = json.loads(role_in)
        return [C.UserRole.get(int(role)) for role in role_ids]
    except ValueError:
        raise exc.BadRequestException()
    
def parse_order_by(
    model: type[utils.Base],
    default: utils.OrderBy | None = None,
):
    def dependency(
        order_by: str | None = Query(None, description="Field and direction to order by, in the format 'field:asc|desc' e.g. 'created_at:desc'"),
    ) -> utils.OrderBy | None:
        if order_by is None:
            return default
        
        try:
            attr, order = order_by.split(":")
            model_attr = getattr(model, attr)
            return getattr(model_attr, "desc" if order == "desc" else "asc")()
        except (AttributeError, ValueError):
            raise exc.BadRequestException()
            
    return dependency