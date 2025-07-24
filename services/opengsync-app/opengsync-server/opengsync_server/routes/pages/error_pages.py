from flask import Blueprint, render_template

from opengsync_db import db_session

from ... import db

errors_bp = Blueprint('errors_bp', __name__)


@errors_bp.app_errorhandler(404)
@db_session(db)
def error_404(error):
    return render_template('errors/404.html'), 404


@errors_bp.app_errorhandler(403)
@db_session(db)
def error_403(error):
    return render_template('errors/403.html'), 403


@errors_bp.app_errorhandler(500)
@db_session(db)
def error_500(error):
    return render_template('errors/500.html'), 500
