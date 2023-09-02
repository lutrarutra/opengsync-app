import os
from io import StringIO

from flask import Flask, render_template, redirect, request, url_for
from flask_login import current_user
from sassutils.wsgi import SassMiddleware

from . import htmx, bcrypt, login_manager, mail, db, SECRET_KEY, logger
from .routes import api, pages

def create_app():
    app = Flask(__name__)
    
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAIL_SERVER"] = "smtp-relay.sendinblue.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    # app.config["MAIL_USE_SSL"] = True
    app.config["MAIL_USERNAME"] = os.environ.get("EMAIL_USER")
    app.config["MAIL_PASSWORD"] = os.environ.get("EMAIL_PASS")
    assert app.config["MAIL_USERNAME"]
    assert app.config["MAIL_PASSWORD"]
    print(app.config["MAIL_USERNAME"])
    
    htmx.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.db_handler.get_user(user_id)

    app.wsgi_app = SassMiddleware(app.wsgi_app, {
        "limbless" : ("static/sass", "static/css", "/static/css")
    })

    @app.route("/")
    def index_page():
        return render_template("index.html")

    app.register_blueprint(api.jobs_bp)
    app.register_blueprint(api.samples_bp)
    app.register_blueprint(api.projects_bp)
    app.register_blueprint(api.experiments_bp)
    app.register_blueprint(api.runs_bp)
    app.register_blueprint(api.libraries_bp)
    app.register_blueprint(api.auth_bp)
    app.register_blueprint(api.organisms_bp)
    
    app.register_blueprint(pages.runs_page_bp)
    app.register_blueprint(pages.samples_page_bp)
    app.register_blueprint(pages.projects_page_bp)
    app.register_blueprint(pages.jobs_page_bp)
    app.register_blueprint(pages.experiments_page_bp)
    app.register_blueprint(pages.libraries_page_bp)
    app.register_blueprint(pages.auth_page_bp)
    app.register_blueprint(pages.user_page_bp)

    return app