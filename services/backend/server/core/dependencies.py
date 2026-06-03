import json
import token
from uuid import UUID
import hashlib

from fastapi import Depends, BackgroundTasks, Request, Header, Cookie
from starlette.background import BackgroundTask
from redis.asyncio import Redis, ConnectionPool
from fastapi_cache import FastAPICache
from taskiq import TaskiqDepends

from sqlalchemy.orm import make_transient_to_detached

from opengsync_db import queries as Q, AsyncSession, exceptions as db_exc, models, categories as cats

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
    
    if user.role == cats.UserRole.DEACTIVATED:
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
    if user.role < cats.UserRole.ADMIN:
        raise exc.HTTPException(status_code=403, detail="Admin privileges required")
    return user

async def require_insider(
    user: models.User = Depends(require_user),
):
    if not user.is_insider():
        raise exc.PermissionDeniedException()
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