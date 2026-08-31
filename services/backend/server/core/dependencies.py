import json
from typing import TypeVar
from collections.abc import Callable
import hashlib

from fastapi import Depends, Request, Header, Cookie, Query
from fastapi_cache import FastAPICache
from taskiq import TaskiqDepends

from sqlalchemy.orm import make_transient_to_detached, joinedload

from opengsync_db import queries as Q, SyncSession, exceptions as db_exc, models, categories as C, utils

from . import mailer, audit, auth, exceptions as exc, secrets, runtime, cache, responses, redis as rds

_USER_CACHE_TTL = 300


def _user_to_cache_dict(user: models.User) -> dict:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "password": user.password,
        "role_id": user.role_id,
    }


def _decode_redis_value(value: bytes | str | int) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)

def get_runtime_request(request: Request = TaskiqDepends()) -> runtime.Request:
    return request  # type: ignore

def db_session(request: runtime.Request = Depends(get_runtime_request)):
    if (session := getattr(request.state, "db_session", None)) is None:
        session = request.app.state.db_handler.get_session()
        request.state.db_session = session
    return session

def taskiq_session(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    with request.app.state.db_handler.get_session() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        
def authenticate(token: str = Depends(auth.oauth2_scheme)):
    payload = secrets.validate_login_token(token)
    return payload

def redis(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    with rds.RedisClient(pool=request.app.state.redis_pool) as redis:
        yield redis

def __get_cached_user(key: str, r: rds.RedisClient) -> models.User | None:
    if (cached_user_str := r.get(key)) is None:
        return None
    user_data = json.loads(cached_user_str)  # type: ignore
    user = models.User(
        id=int(user_data["id"]),
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        email=user_data["email"],
        password=user_data.get("password", ""),
        role_id=int(user_data["role_id"]),
    )
    make_transient_to_detached(user)
    return user


def __cache_current_user(user_data: dict, r: rds.RedisClient) -> None:
    r.set(f"user:{user_data['id']}", json.dumps(user_data), ex=_USER_CACHE_TTL)


def __cache_api_token_mapping(user_data: dict, cache_key: str, r: rds.RedisClient) -> None:
    r.set(cache_key, str(user_data["id"]), ex=_USER_CACHE_TTL)
    r.set(f"user:{user_data['id']}", json.dumps(user_data), ex=_USER_CACHE_TTL)


def _resolve_user(
    auth_response: auth.AuthResponse,
    session: SyncSession,
    r: rds.RedisClient,
) -> models.User | None:
    """Shared helper to fetch user from cache or DB and schedule cache updates."""
    if (user := __get_cached_user(f"user:{auth_response.id}", r)) is not None:
        return user

    if (user := session.first(
        Q.user.select(id=auth_response.id),
    )) is None:
        return None

    __cache_current_user(_user_to_cache_dict(user), r)
    return user

def _resolve_user_by_api_token(
    token: str,
    session: SyncSession,
    r: rds.RedisClient,
) -> models.User | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cache_key = f"api_token:{token_hash}"

    if (cached_user_id := r.get(cache_key)) is not None:
        user_id = int(_decode_redis_value(cached_user_id))  # type: ignore
        if (user := __get_cached_user(f"user:{user_id}", r)) is not None:
            return user
        if (user := session.first(Q.user.select(id=user_id))) is not None:
            __cache_current_user(_user_to_cache_dict(user), r)
            return user

    db_token = session.first(
        Q.api_token.select(uuid=token),
        options=[joinedload(models.APIToken.owner)],
    )
    if db_token is None or db_token.is_expired:
        return None

    user = db_token.owner
    __cache_api_token_mapping(_user_to_cache_dict(user), cache_key, r)
    return user

def get_user(
    request: runtime.Request = TaskiqDepends(),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
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
        user = _resolve_user(auth_response, session, r)
    elif api_token:
        user = _resolve_user_by_api_token(api_token, session, r)
    else:
        user = None

    if not user:
        request.state.current_user = None
        return None
    
    if user.role == C.UserRole.DEACTIVATED:
        raise exc.UserAccountSuspendedException()
    
    request.state.current_user = user
    return user


def require_user(user: models.User | None = Depends(get_user)) -> models.User:
    if not user:
        raise exc.UserNotAuthenticatedException()
    return user

def require_admin(user: models.User = Depends(require_user)) -> models.User:
    if user.role != C.UserRole.ADMIN:
        raise exc.HTTPException(status_code=403, detail="Admin privileges required")
    return user

def require_insider(user: models.User = Depends(require_user)) -> models.User:
    if not user.is_insider:
        raise exc.NoPermissionsException()
    return user

def mail_client(request: runtime.Request = TaskiqDepends(get_runtime_request)) -> mailer.Mailer:
    return request.app.state.mailer

def get_bcrypt(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    return request.app.state.bcrypt

def audit_log(request: runtime.Request = TaskiqDepends(get_runtime_request)):
    request.state.audit = audit.AuditLogger(request)
    return request.state.audit

def invalidate_cache(request: runtime.Request):
    substrings: list[str] = []
    yield substrings

    if not substrings:
        return

    prefix = FastAPICache.get_prefix()
    for substring in substrings:
        pattern = f"{prefix}:*:{substring}:*"
        cache.scan_and_delete(pattern=pattern, redis_pool=request.app.state.redis_pool)


def project_permissions(
    project_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:project:{project_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.project.permissions(project_id=project_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this project.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Project not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def seq_request_permissions(
    seq_request_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:seq_request:{seq_request_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this sequencing request.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Sequencing request not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def sample_permissions(
    sample_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:sample:{sample_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.sample.permissions(sample_id=sample_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this sample.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Sample not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def library_permissions(
    library_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:library:{library_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.library.permissions(library_id=library_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this library.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Library not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def pool_permissions(
    pool_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:pool:{pool_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.pool.permissions(pool_id=pool_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this pool.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Pool not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def media_file_permissions(
    media_file_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:media_file:{media_file_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.media_file.permissions(media_file_id=media_file_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this media file.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Media file not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def user_permissions(
    user_id: int,
    current_user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:user:{user_id}:user:{current_user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.user.permissions(user_id=user_id, viewer_id=current_user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this user.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("User not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level

def group_permissions(
    group_id: int,
    user: models.User = Depends(require_user),
    session: SyncSession = Depends(db_session),
    r: rds.RedisClient = Depends(redis),
):
    cache_key = f"access:group:{group_id}:user:{user.id}"
    if (cached_access := r.get(cache_key)) is not None:
        return C.AccessLevel(int(cached_access))  #type: ignore
    try:
        if (access_level := session.get_access_level(Q.group.permissions(group_id=group_id, user_id=user.id))) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to access this group.")
    except db_exc.NotFoundException:
        raise exc.NotFoundException("Group not found.")

    r.set(cache_key, int(access_level), ex=300)
    return access_level
    
E = TypeVar("E", bound=C.ExtendedEnum)

def parse_enum_ids(
    enum_type: type[E], query_param: str,        
) -> Callable[[], list[E] | None]:
    def dependency(
        ids_in: str | None = Query(None, alias=query_param, description=f"JSON list of {enum_type.__name__} IDs to filter by")
    ) -> list[E] | None:
        if ids_in is None:
            return None
        
        try:
            enum_ids = json.loads(ids_in)
            return [enum_type.get(int(enum_id)) for enum_id in enum_ids] or None
        except ValueError:
            raise exc.BadRequestException()
    
    return dependency

def parse_enum_id(
    enum_type: type[E], query_param: str,        
) -> Callable[[], E | None]:
    def dependency(
        id_in: int | None = Query(None, alias=query_param, description=f"{enum_type.__name__} ID to filter by")
    ) -> E | None:
        if id_in is None:
            return None
        
        try:
            return enum_type.get(int(id_in))
        except ValueError:
            raise exc.BadRequestException()
    
    return dependency
    
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

def parse_from_page(
    from_page: str | None = Query(None, alias="from", description="The page the user came from, in the format 'page_name@id'."),
) -> list[tuple[str, responses.URL]] | None:
    if from_page is None:
        return None
    
    path_list = []
    if from_page is not None:
        page, id = from_page.split("@")
        if page == "user":
            path_list = [
                ("Users", responses.url_for("users_page")),
                (f"User {id}", responses.url_for("user_page", user_id=id)),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", responses.url_for("seq_requests_page")),
                (f"Request {id}", responses.url_for("seq_request_page", seq_request_id=id)),
            ]
        elif page == "project":
            path_list = [
                ("Projects", responses.url_for("projects_page")),
                (f"Project {id}", responses.url_for("project_page", project_id=id)),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", responses.url_for("samples_page")),
                (f"Sample {id}", responses.url_for("sample_page", sample_id=id)),
            ]

    return path_list