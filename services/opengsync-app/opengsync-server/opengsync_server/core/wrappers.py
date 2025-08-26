from typing import Callable, Literal, TypeVar, Any
from functools import wraps
import traceback

from flask import Blueprint, Flask, render_template, flash, request
from flask_htmx import make_response
from flask_login import login_required as login_required_f, current_user

from opengsync_db import DBHandler
from opengsync_db.categories import HTTPResponse
from opengsync_db import exceptions as db_exceptions

from .. import logger
from ..core.LogBuffer import log_buffer
from ..tools import utils, textgen
from . import exceptions as serv_exceptions
from .RunTime import runtime

F = TypeVar("F", bound=Callable[..., Any])  # generic for wrapped functions


def __get_flash_msg(msg: str) -> str:
    if textgen is None:
        return msg
    return textgen.generate(
        "You need to write in 1-2 sentences make a joke about error/bug..."
    ) or msg


def _default_logger(blueprint: Blueprint | Flask, routes, args, kwargs, e: Exception, exc_type: str) -> None:
    logger.error(
        f"\n-------- {exc_type} --------"
        f"\n\tBlueprint: {blueprint}"
        f"\n\tRoute: {routes}"
        f"\n\targs: {args}"
        f"\n\tkwargs: {kwargs}"
        f"\n\tError: {e.__repr__()}"
        f"\n\tMessage: {e}"
        f"\n\tTraceback: {traceback.format_exc()}"
        f"\n-------- END ERROR --------"
    )


def _route_decorator(
    blueprint: Blueprint | Flask,
    route: str | None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]],
    db: DBHandler | None,
    login_required: bool,
    debug: bool,
    strict_slashes: bool,
    response_handler: Callable[[Exception], Any],
    cache_timeout_seconds: int | None,
    cache_query_string: bool,
    cache_type: Literal["user", "insider", "global"],
    cache_kwargs: dict[str, Any] | None,
) -> Callable[[F], F]:
    """Base decorator for all route types."""
    from .. import route_cache, flash_cache

    def decorator(fnc: F) -> F:
        routes, current_user_required = utils.infer_route(fnc, base=route)

        match current_user_required:
            case "required":
                if not login_required:
                    logger.error(f"Route {fnc.__name__} requires current_user but login_required is False.")

            case "optional":
                if login_required:
                    logger.error(f"Route {fnc.__name__} current_user is optional but login_required is True.")

        if login_required and db is None:
            raise ValueError("db must be provided if login_required is True")

        if cache_timeout_seconds is not None:
            def user_cache_key() -> str:
                query_string = ""
                user_id = current_user.id if current_user.is_authenticated else "anon"
                if cache_query_string and request.args:
                    args = request.args
                    sorted_args = sorted((k, v) for k, v in args.items())
                    query_string = "?" + "&".join(f"{k}={v}" for k, v in sorted_args)
                key = f"view/{user_id}{request.path}{query_string}"
                return key
            
            def insider_cache_key() -> str:
                if current_user.is_authenticated and not current_user.is_insider():
                    return user_cache_key()
                query_string = ""
                if cache_query_string and request.args:
                    args = request.args
                    sorted_args = sorted((k, v) for k, v in args.items())
                    query_string = "?" + "&".join(f"{k}={v}" for k, v in sorted_args)
                key = f"view/insider{request.path}{query_string}"
                return key
            
            fnc = route_cache.cached(
                timeout=cache_timeout_seconds,
                query_string=cache_query_string if cache_type == "global" else False,
                key_prefix=user_cache_key if cache_type == "user" else insider_cache_key if cache_type == "insider" else "view/%s",  # type: ignore
                **(cache_kwargs or {})
            )(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            if debug:
                log_buffer.start(str(request.url_rule))
            else:
                log_buffer.start()
            if db is not None:
                db.open_session()

            _fnc = login_required_f(fnc) if login_required else fnc
            
            if current_user_required != "no":
                kwargs["current_user"] = current_user if current_user.is_authenticated else None

            try:
                return _fnc(*args, **kwargs)
            except serv_exceptions.OpeNGSyncServerException as e:
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncServerException")
                return response_handler(e)
            except db_exceptions.OpeNGSyncDBException as e:
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncDBException")
                return response_handler(e)
            except Exception as e:
                if runtime.app.debug and response_handler.__name__ != "_htmx_handler":
                    raise e
                _default_logger(blueprint, routes, args, kwargs, e, "Exception")
                return response_handler(e)
            finally:
                if db is not None:
                    if db.close_session():
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
        case _:
            flash(__get_flash_msg(msg), category="error")
            return render_template("errors/error.html", msg=msg, code=500), 500


def page_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "global"] = "user",
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        login_required=login_required,
        debug=debug,
        strict_slashes=strict_slashes,
        response_handler=_page_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
    )


def htmx_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        login_required=login_required,
        debug=debug,
        strict_slashes=strict_slashes,
        response_handler=_htmx_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
    )


def api_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = False,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        login_required=login_required,
        debug=debug,
        strict_slashes=strict_slashes,
        response_handler=_api_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
    )


def resource_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = True,
    cache_kwargs: dict[str, Any] | None = None,
    cache_type: Literal["user", "insider", "global"] = "user",
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(
        blueprint=blueprint,
        route=route,
        methods=methods,
        db=db,
        login_required=login_required,
        debug=debug,
        strict_slashes=strict_slashes,
        response_handler=_resource_handler,
        cache_timeout_seconds=cache_timeout_seconds,
        cache_query_string=cache_query_string,
        cache_type=cache_type,
        cache_kwargs=cache_kwargs,
    )
