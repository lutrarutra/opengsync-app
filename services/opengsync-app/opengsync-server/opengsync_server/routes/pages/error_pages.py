from flask import Blueprint, render_template

from ... import db, page_route

errors_bp = Blueprint("errors_bp", __name__)


@errors_bp.app_errorhandler(404)
@page_route(errors_bp, db=db, login_required=False)
def error_404(error):
    return render_template('errors/404.html'), 404


@errors_bp.app_errorhandler(403)
@page_route(errors_bp, db=db, login_required=False)
def error_403(error):
    return render_template('errors/403.html'), 403


@errors_bp.app_errorhandler(500)
@page_route(errors_bp, db=db, login_required=False)
def error_500(error):
    return render_template('errors/500.html'), 500
