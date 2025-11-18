import os
from typing import Callable, Literal, Any, Sequence
from functools import wraps
import traceback

from flask import Blueprint, Flask, render_template, flash, request, Response
from flask_htmx import make_response
from flask_login import login_required as login_required_f, current_user
from flask_limiter.errors import RateLimitExceeded

from opengsync_db import DBHandler
from opengsync_db.categories import HTTPResponse
from opengsync_db import exceptions as db_exceptions

from .. import logger
from ..core.LogBuffer import log_buffer
from ..tools import routes as rt, textgen
from . import exceptions as serv_exceptions
from .RunTime import runtime

DEBUG = os.getenv("OPENGSYNC_DEBUG", "0") == "1"


def __get_flash_msg(msg: str) -> str:
    if textgen is None:
        return msg
    return textgen.generate(
        "You need to write in 1-2 sentences make a joke about error/bug..."
    ) or msg


def _default_logger(blueprint: Blueprint | Flask, routes, args, kwargs, e: Exception, exc_type: str, type: Literal["error", "warning", "info"] | None = None) -> None:
    if type is None:
        match e:
            case serv_exceptions.NoPermissionsException | serv_exceptions.NotFoundException | serv_exceptions.BadRequestException | serv_exceptions.MethodNotAllowedException | db_exceptions.ElementDoesNotExist:
                type = "warning"

    match type:
        case "warning":
            log_func = logger.warning
        case "info":
            log_func = logger.info
        case _:
            log_func = logger.error

    log_func(
        f"\n-------- {exc_type} --------"
        f"\n\tBlueprint: {blueprint}"
        f"\n\tRoute: {routes}"
        f"\n\targs: {args}"
        f"\n\tkwargs: {kwargs}"
        f"\n\tError: {e}"
        f"\n\tMessage: {e}"
        f"\n\tTraceback: {traceback.format_exc()}"
        f"\n-------- END ERROR --------"
    )


def _route_decorator(
    blueprint: Blueprint | Flask,
    route: str | None,
    methods: Sequence[Literal["GET", "POST", "PUT", "DELETE", "PROPFIND", "OPTIONS", "HEAD"]],
    db: DBHandler | None,
    login_required: bool,
    debug: bool,
    strict_slashes: bool,
    arg_params: list[str],
    form_params: list[str],
    json_params: list[str],
    response_handler: Callable[[Exception], Any],
    cache_timeout_seconds: int | None,
    api_token_required: bool,
    cache_query_string: bool,
    cache_type: Literal["user", "insider", "global"],
    cache_kwargs: dict[str, Any] | None,
    limit: str | None = None,
    limit_exempt: Literal["all", "insider", "user", None] = "insider",
    limit_override: bool = False,
) -> Callable[[Callable[..., Any]], Response]:
    """Base decorator for all route types."""
    from .. import route_cache, flash_cache, limiter

    def decorator(fnc: Callable[..., Any]) -> Response:
        routes, current_user_required, params = rt.infer_route(fnc, base=route, arg_params=arg_params, form_params=form_params, json_params=json_params)
        original_fnc = fnc
        match current_user_required:
            case "required":
                if not login_required:
                    logger.error(f"Route {fnc.__name__} requires current_user but login_required is False.")

            case "optional":
                if login_required:
                    logger.error(f"Route {fnc.__name__} current_user is optional but login_required is True.")

        if login_required and db is None:
            raise ValueError("db must be provided if login_required is True")
        
        if limit_exempt == "all" or DEBUG:
            fnc = limiter.exempt(fnc)
        else:
            if limit is not None:
                match limit_exempt:
                    case "insider":
                        def exempt_when() -> bool:
                            return current_user.is_authenticated and current_user.is_insider()
                    case "user":
                        def exempt_when() -> bool:
                            return current_user.is_authenticated
                    case _:
                        exempt_when = None  # type: ignore
                    
                fnc = limiter.limit(
                    limit, override_defaults=limit_override,
                    exempt_when=exempt_when
                )(fnc)

        if cache_timeout_seconds is not None and not DEBUG:
            def user_cache_key() -> str:
                query_string = ""
                user_id = current_user.id if current_user.is_authenticated else "anon"
                if cache_query_string and request.args:
                    args = request.args
                    sorted_args = sorted((k, v) for k, v in args.items())
                    query_string = "?" + "&".join(f"{k}={v}" for k, v in sorted_args)
                key = f"{request.method}-{request.headers.get('X-Forwarded-Prefix', '/')}view/{user_id}{request.path}{query_string}"
                return key
            
            def insider_cache_key() -> str:
                if current_user.is_authenticated and not current_user.is_insider():
                    return user_cache_key()
                query_string = ""
                if cache_query_string and request.args:
                    args = request.args
                    sorted_args = sorted((k, v) for k, v in args.items())
                    query_string = "?" + "&".join(f"{k}={v}" for k, v in sorted_args)

                key = f"{request.method}-{request.headers.get('X-Forwarded-Prefix', '/')}view/insider{request.path}{query_string}"
                return key

            def default_cache_key() -> str:
                return f"{request.method}-{request.headers.get('X-Forwarded-Prefix', '/')}view/%s"

            fnc = route_cache.cached(
                timeout=cache_timeout_seconds,
                query_string=cache_query_string if cache_type == "global" else False,
                key_prefix=user_cache_key if cache_type == "user" else insider_cache_key if cache_type == "insider" else default_cache_key,  # type: ignore
                **(cache_kwargs or {})
            )(fnc)

        if login_required:
            fnc = login_required_f(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            log_buffer.start(f"{request.method} -> {request.path}")

            if db is not None:
                db.open_session()
            
            if current_user_required != "no":
                kwargs["current_user"] = current_user if current_user.is_authenticated else None

            rollback = False
            try:
                try:
                    kwargs, additional_kwargs = rt.validate_parameters(original_fnc, request, kwargs)
                except ValueError as e:
                    raise serv_exceptions.BadRequestException("Invalid query parameters") from e
                
                if api_token_required:
                    if db is None:
                        raise serv_exceptions.InternalServerErrorException("Database handler is required for API token validation.")
                    if (api_token := additional_kwargs.pop("api_token", None)) is None:
                        raise serv_exceptions.UnauthorizedException("API token is required but not provided.")
                    if (token := db.api_tokens.get(api_token)) is None:
                        raise serv_exceptions.NoPermissionsException(f"Invalid API token '{api_token}'.")
                    if token.is_expired:
                        raise serv_exceptions.NoPermissionsException("API token is expired.")
                    
                    if limiter.current_limit is not None:
                        limiter.storage.clear(limiter.current_limit.key)

                return fnc(*args, **kwargs)
            except serv_exceptions.InternalServerErrorException as e:
                rollback = db.needs_commit if db is not None else False
                _default_logger(blueprint, routes, args, kwargs, e, "InternalServerErrorException", "error")
                return response_handler(e)
            except serv_exceptions.OpeNGSyncServerException as e:
                rollback = db.needs_commit if db is not None else False
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncServerException", None)
                return response_handler(e)
            except db_exceptions.OpeNGSyncDBException as e:
                rollback = db.needs_commit if db is not None else False
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncDBException", None)
                return response_handler(e)
            except RateLimitExceeded as e:
                logger.warning(f"Rate limit exceeded on route {routes} for IP {request.remote_addr}")
                return response_handler(serv_exceptions.TooManyRequestsException())
            except Exception as e:
                rollback = db.needs_commit if db is not None else False
                if runtime.app.debug and response_handler.__name__ != "_htmx_handler":
                    raise e
                _default_logger(blueprint, routes, args, kwargs, e, "Exception", "error")
                return response_handler(e)
            finally:
                if db is not None:
                    if db.close_session(commit=True, rollback=rollback):
                        route_cache.clear()

                if (msgs := runtime.app.consume_flashes(runtime.session)):
                    if runtime.session.sid:
                        flash_cache.add(runtime.session.sid, msgs)

                log_buffer.flush()

        if debug:
            logger.debug(routes)

        for r, defaults in routes:
            blueprint.route(r, methods=methods, defaults=defaults, strict_slashes=strict_slashes)(wrapper)

        return wrapper  # type: ignore
    return decorator


def _page_handler(e: Exception):
    if isinstance(e, serv_exceptions.OpeNGSyncServerException):
        msg = e.message
    elif isinstance(e, db_exceptions.OpeNGSyncDBException):
        msg = e.message
    else:
        msg = "An error occurred while processing your request. Please notify us."

    match type(e):
        case serv_exceptions.NoPermissionsException:
            flash(msg, category="error")
            return render_template("errors/page.html", msg=msg, code=403), 403
        case serv_exceptions.NotFoundException | db_exceptions.LinkDoesNotExist | db_exceptions.ElementDoesNotExist:
            flash(msg, category="error")
            return render_template("errors/page.html", msg=msg, code=404), 404
        case serv_exceptions.BadRequestException:
            flash(msg, category="error")
            return render_template("errors/page.html", msg=msg, code=400), 400
        case serv_exceptions.MethodNotAllowedException:
            flash(msg, category="error")
            return render_template("errors/page.html", msg=msg, code=405), 405
        case serv_exceptions.TooManyRequestsException:
            flash(msg, category="error")
            return render_template("errors/page.html", msg=msg, code=429), 429
        case _:
            flash(__get_flash_msg(msg), category="error")
            return render_template("errors/page.html", msg=msg, code=500), 500


def _htmx_handler(e: Exception):
    if isinstance(e, serv_exceptions.OpeNGSyncServerException):
        msg = e.message
    elif isinstance(e, db_exceptions.OpeNGSyncDBException):
        msg = e.message
    else:
        msg = "An error occurred while processing your request. Please notify us."

    match type(e):
        case serv_exceptions.NoPermissionsException:
            flash(msg, category="error")
        case serv_exceptions.NotFoundException | db_exceptions.LinkDoesNotExist | db_exceptions.ElementDoesNotExist:
            flash(msg, category="error")
        case serv_exceptions.BadRequestException:
            flash(msg, category="error")
        case serv_exceptions.MethodNotAllowedException:
            flash(msg, category="error")
        case serv_exceptions.TooManyRequestsException:
            flash(msg, category="error")
        case _:
            msg = __get_flash_msg(msg)
            flash(msg, category="error")

    return make_response(render_template("errors/htmx/alert.html"), 200, retarget="#alert-container")


def _api_handler(e: Exception):
    if isinstance(e, serv_exceptions.OpeNGSyncServerException):
        msg = e.message
    elif isinstance(e, db_exceptions.OpeNGSyncDBException):
        msg = e.message
    else:
        msg = "An error occurred while processing your request. Please notify us."

    match type(e):
        case serv_exceptions.NoPermissionsException:
            return msg, HTTPResponse.FORBIDDEN.id
        case serv_exceptions.NotFoundException | db_exceptions.LinkDoesNotExist | db_exceptions.ElementDoesNotExist:
            return msg, HTTPResponse.NOT_FOUND.id
        case serv_exceptions.BadRequestException:
            return msg, HTTPResponse.BAD_REQUEST.id
        case serv_exceptions.MethodNotAllowedException:
            return msg, HTTPResponse.METHOD_NOT_ALLOWED.id
        case serv_exceptions.TooManyRequestsException:
            return msg, HTTPResponse.TOO_MANY_REQUESTS.id
        case _:
            return msg, HTTPResponse.INTERNAL_SERVER_ERROR.id


def _resource_handler(e: Exception):
    if isinstance(e, serv_exceptions.OpeNGSyncServerException):
        msg = e.message
    elif isinstance(e, db_exceptions.OpeNGSyncDBException):
        msg = e.message
    else:
        msg = "An error occurred while processing your request. Please notify us."

    match type(e):
        case serv_exceptions.NoPermissionsException:
            flash(msg, category="error")
            return render_template("errors/error.html", msg=msg, code=403), 403
        case serv_exceptions.NotFoundException | db_exceptions.LinkDoesNotExist | db_exceptions.ElementDoesNotExist:
            flash(msg, category="error")
            return render_template("errors/error.html", msg=msg, code=404), 404
        case serv_exceptions.BadRequestException:
            flash(msg, category="error")
            return render_template("errors/error.html", msg=msg, code=400), 400
        case serv_exceptions.MethodNotAllowedException:
            flash(msg, category="error")
            return render_template("errors/error.html", msg=msg, code=405), 405
        case serv_exceptions.TooManyRequestsException:
            flash(msg, category="error")
            return render_template("errors/error.html", msg=msg, code=429), 429
        case _:
            flash(__get_flash_msg(msg), category="error")
            return render_template("errors/error.html", msg=msg, code=500), 500


def page_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: Sequence[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    arg_params: list[str] = [],
    form_params: list[str] = [],
    json_params: list[str] = [],
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "global"] = "user",
    strict_slashes: bool = True,
    limit: str | None = None,
    limit_exempt: Literal["all", "insider", "user", None] = "insider",
    limit_override: bool = False,
) -> Callable[[Callable[..., Any]], Response]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        arg_params=arg_params,
        form_params=form_params,
        json_params=json_params,
        login_required=login_required,
        debug=debug,
        api_token_required=False,
        strict_slashes=strict_slashes,
        response_handler=_page_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
        limit=limit,
        limit_exempt=limit_exempt,
        limit_override=limit_override,
    )


def htmx_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: Sequence[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    arg_params: list[str] = [],
    form_params: list[str] = [],
    json_params: list[str] = [],
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
    limit: str | None = None,
    limit_exempt: Literal["all", "insider", "user", None] = "insider",
    limit_override: bool = False,
) -> Callable[[Callable[..., Any]], Response]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        arg_params=arg_params,
        form_params=form_params,
        json_params=json_params,
        login_required=login_required,
        debug=debug,
        api_token_required=False,
        strict_slashes=strict_slashes,
        response_handler=_htmx_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
        limit=limit,
        limit_exempt=limit_exempt,
        limit_override=limit_override,
    )


def api_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: Sequence[Literal["GET", "POST", "PUT", "DELETE", "PROPFIND", "OPTIONS", "HEAD"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = False,
    debug: bool = False,
    arg_params: list[str] = [],
    form_params: list[str] = [],
    json_params: list[str] = [],
    api_token_required: bool = True,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
    limit: str | None = None,
    limit_exempt: Literal["all", "insider", "user", None] = "insider",
    limit_override: bool = False,
) -> Callable[[Callable[..., Any]], Response]:
    if api_token_required and "api_token" not in json_params:
        json_params.append("api_token")
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        arg_params=arg_params,
        form_params=form_params,
        json_params=json_params,
        login_required=login_required,
        debug=debug,
        api_token_required=api_token_required,
        strict_slashes=strict_slashes,
        response_handler=_api_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
        limit=limit,
        limit_exempt=limit_exempt,
        limit_override=limit_override,
    )


def resource_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: Sequence[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    arg_params: list[str] = [],
    form_params: list[str] = [],
    json_params: list[str] = [],
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
    limit: str | None = None,
    limit_exempt: Literal["all", "insider", "user", None] = "insider",
    limit_override: bool = False,
) -> Callable[[Callable[..., Any]], Response]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        arg_params=arg_params,
        form_params=form_params,
        json_params=json_params,
        login_required=login_required,
        debug=debug,
        api_token_required=False,
        strict_slashes=strict_slashes,
        response_handler=_resource_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
        limit=limit,
        limit_exempt=limit_exempt,
        limit_override=limit_override,
    )
