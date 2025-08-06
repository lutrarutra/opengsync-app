from typing import Callable, Literal
from functools import wraps
import traceback

from flask import Blueprint, Flask
from flask import abort, render_template, flash, current_app
from flask_htmx import make_response
from flask_login import login_required as login_required_f

from opengsync_db import DBHandler, db_session
from opengsync_db.categories import HTTPResponse
from opengsync_db import exceptions as db_exceptions

from .. import logger
from ..tools import utils, textgen
from . import exceptions as serv_exceptions


def __get_flash_msg(msg: str) -> str:
    if textgen is None:
        return msg
    return textgen.generate(
        "You need to write in 1-2 sentences make a joke about error/bug that will be incorporated to my app. \
        Only raw text, no special characters, no markdown, no code blocks, no quotes, no emojis, no links, no hashtags, no mentions. \
        Just the joke text."
    ) or msg
    

def page_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
    strict_slashes: bool = True
):
    def decorator(fnc: Callable):
        routes = utils.infer_route(fnc, base=route)

        if debug:
            logger.debug(routes)

        if login_required and db is None:
            raise ValueError("db must be provided if login_required is True")
                
        if login_required:
            fnc = login_required_f(fnc)
        if db is not None:
            fnc = db_session(db)(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            try:
                return fnc(*args, **kwargs)
            except serv_exceptions.OpeNGSyncServerException as e:
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
            except db_exceptions.OpeNGSyncDBException as e:
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
            except Exception as e:
                if current_app.debug:
                    raise e
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
            finally:
                if db is not None and db._session:
                    db.close_session(commit=False)
        
        for r, defaults in routes:
            blueprint.route(r, methods=methods, defaults=defaults, strict_slashes=strict_slashes)(wrapper)

        return wrapper
    return decorator


def htmx_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
):
    def decorator(fnc: Callable):
        routes = utils.infer_route(fnc, base=route)

        if login_required and db is None:
            raise ValueError("db must be provided if login_required is True")

        if login_required:
            fnc = login_required_f(fnc)
        if db is not None:
            fnc = db_session(db)(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            try:
                res = fnc(*args, **kwargs)
                return res
            except serv_exceptions.OpeNGSyncServerException as e:
                logger.error(f"\n-------- OpeNGSyncServerException --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            except db_exceptions.OpeNGSyncDBException as e:
                logger.error(f"\n-------- OpeNGSyncDBException --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            except Exception as e:
                if current_app.debug:
                    raise e
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                flash(__get_flash_msg("An error occured while processing your request. Please notify us."), category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            finally:
                if db is not None and db._session:
                    db.close_session(commit=False)

        for r, defaults in routes:
            blueprint.route(r, methods=methods, defaults=defaults)(wrapper)

        if debug:
            logger.debug(routes)
        return wrapper
    return decorator


def api_route(
    blueprint: Blueprint | Flask,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True,
    debug: bool = False,
):
    def decorator(fnc: Callable):
        routes = utils.infer_route(fnc, base=route)

        if login_required and db is None:
            raise ValueError("db must be provided if login_required is True")
                
        if login_required:
            fnc = login_required_f(fnc)
        if db is not None:
            fnc = db_session(db)(fnc)

        @wraps(fnc)
        def wrapper(*args, **kwargs):
            try:
                return fnc(*args, **kwargs)
            except serv_exceptions.OpeNGSyncServerException as e:
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                return "An error occurred while processing your request. Please notify us.", HTTPResponse.INTERNAL_SERVER_ERROR.id
            except db_exceptions.OpeNGSyncDBException as e:
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                return "An error occurred while processing your request. Please notify us.", HTTPResponse.INTERNAL_SERVER_ERROR.id
            except Exception as e:
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {routes}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                return "An error occurred while processing your request. Please notify us.", HTTPResponse.INTERNAL_SERVER_ERROR.id
            finally:
                if db is not None and db._session:
                    db.close_session(commit=False)
        
        if debug:
            logger.debug(routes)
        
        for r, defaults in routes:
            blueprint.route(r, methods=methods, defaults=defaults)(wrapper)

        return wrapper
    return decorator