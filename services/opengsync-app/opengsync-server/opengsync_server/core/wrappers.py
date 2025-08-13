from typing import Callable, Literal, TypeVar, Any
from functools import wraps
import traceback

from flask import Blueprint, Flask, abort, render_template, flash, request
from flask_htmx import make_response
from flask_login import login_required as login_required_f, current_user

from opengsync_db import DBHandler
from opengsync_db.categories import HTTPResponse
from opengsync_db import exceptions as db_exceptions

from .. import logger
from ..core.LogBuffer import log_buffer
from ..tools import utils, textgen
from . import exceptions as serv_exceptions
from ..core.runtime import runtime

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
    cache_kwargs: dict[str, Any] | None,
) -> Callable[[F], F]:
    """Base decorator for all route types."""
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
            from .. import cache
            fnc = cache.cached(timeout=cache_timeout_seconds, query_string=cache_query_string, **(cache_kwargs or {}))(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            if debug:
                log_buffer.start(str(request.url_rule))
            else:
                log_buffer.start()
            if db is not None:
                db.open_session()

            _fnc = login_required_f(fnc) if login_required else fnc

            try:
                if current_user_required != "no":
                    kwargs["current_user"] = current_user if current_user.is_authenticated else None
                    
                return _fnc(*args, **kwargs)
            except serv_exceptions.OpeNGSyncServerException as e:
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncServerException")
                return response_handler(e)
            except db_exceptions.OpeNGSyncDBException as e:
                _default_logger(blueprint, routes, args, kwargs, e, "OpeNGSyncDBException")
                return response_handler(e)
            except Exception as e:
                if runtime.current_app.debug and response_handler.__name__ != "_htmx_handler":
                    raise e
                _default_logger(blueprint, routes, args, kwargs, e, "Exception")
                return response_handler(e)
            finally:
                if db is not None and db._session:
                    db.close_session()
                log_buffer.flush()

        if debug:
            logger.debug(routes)

        for r, defaults in routes:
            blueprint.route(r, methods=methods, defaults=defaults, strict_slashes=strict_slashes)(wrapper)

        return wrapper  # type: ignore
    return decorator


def _page_handler(e: Exception):
    flash(__get_flash_msg("An error occurred while processing your request. Please notify us."), category="error")
    return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)


def _htmx_handler(e: Exception):
    flash(__get_flash_msg("An error occurred while processing your request. Please notify us."), category="error")
    return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")


def _api_handler(e: Exception):
    return "An error occurred while processing your request. Please notify us.", HTTPResponse.INTERNAL_SERVER_ERROR.id


def page_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = False,
    cache_kwargs: dict[str, Any] | None = None,
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(blueprint, route, methods, db, login_required, debug, strict_slashes, _page_handler, cache_timeout_seconds, cache_query_string, cache_kwargs)


def htmx_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = False,
    cache_kwargs: dict[str, Any] | None = None,
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(blueprint, route, methods, db, login_required, debug, strict_slashes, _htmx_handler, cache_timeout_seconds, cache_query_string, cache_kwargs)


def api_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = False,
    debug: bool = False,
    cache_timeout_seconds: int | None = None,
    cache_query_string: bool = False,
    cache_kwargs: dict[str, Any] | None = None,
    strict_slashes: bool = True,
) -> Callable[[F], F]:
    return _route_decorator(blueprint, route, methods, db, login_required, debug, strict_slashes, _api_handler, cache_timeout_seconds, cache_query_string, cache_kwargs)
