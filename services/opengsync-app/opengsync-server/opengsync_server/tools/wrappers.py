from typing import Callable, Literal
from functools import wraps
import traceback

from flask import Blueprint
from flask import abort, render_template, flash, current_app
from flask_htmx import make_response
from flask_login import login_required as login_required_f

from opengsync_db import DBHandler, db_session
from opengsync_db.categories import HTTPResponse
from opengsync_db import exceptions as db_exceptions

from .. import logger
from ..tools import utils
from . import exceptions as serv_exceptions


def page_route(
    blueprint: Blueprint,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True
):
    def decorator(fnc: Callable):
        effective_route = route or utils.infer_route(fnc)
        effective_route = "/" + effective_route.lstrip("/")

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
                logger.error(e)
                return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
            except db_exceptions.OpeNGSyncDBException as e:
                logger.error(e)
                return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
            finally:
                if db is not None and db._session:
                    db.close_session(commit=False)

        return blueprint.route(effective_route, methods=methods)(wrapper)
    return decorator


def htmx_route(
    blueprint: Blueprint,
    route: str | None = None,
    methods: list[Literal["GET", "POST", "PUT", "DELETE"]] = ["GET"],
    db: DBHandler | None = None,
    login_required: bool = True
):
    def decorator(fnc: Callable):
        effective_route = route or utils.infer_route(fnc)
        effective_route = "/" + effective_route.lstrip("/")

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
                logger.error(f"\n-------- OpeNGSyncServerException --------\n\tBlueprint: {blueprint}\n\tRoute: {effective_route}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}n\tMessage: {e}\n-------- END ERROR --------")
                flash("An error occured while processing your request. Please notify us.", category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            except db_exceptions.OpeNGSyncDBException as e:
                logger.error(f"\n-------- OpeNGSyncDBException --------\n\tBlueprint: {blueprint}\n\tRoute:{effective_route}\n\targs: {args}\n\tkwargs: {kwargs}]\n\tError: {e.__repr__()}n\tMessage: {e}\n-------- END ERROR --------")
                flash("An error occured while processing your request. Please notify us.", category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            except Exception as e:
                if current_app.debug:
                    raise e
                logger.error(f"\n-------- Exception --------\n\tBlueprint: {blueprint}\n\tRoute: {effective_route}\n\targs: {args}\n\tkwargs: {kwargs}\n\tError: {e.__repr__()}\n\tMessage: {e}\n\tTraceback: {traceback.format_exc()}\n-------- END ERROR --------")
                flash("An error occured while processing your request. Please notify us.", category="error")
                return make_response(render_template("errors/htmx_alert.html"), 200, retarget="#alert-container")
            finally:
                if db is not None and db._session:
                    db.close_session(commit=False)

        return blueprint.route(effective_route, methods=methods)(wrapper)
    return decorator
