from io import StringIO

from flask import Flask, render_template, redirect, request, url_for
from sassutils.wsgi import SassMiddleware

from sqlmodel import Session, select
import pandas as pd

from . import forms, models, logger, app, htmx
from .routes import api, pages

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "SECRET_KEY"
    htmx.init_app(app)

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
    
    app.register_blueprint(pages.runs_page_bp)
    app.register_blueprint(pages.samples_page_bp)
    app.register_blueprint(pages.projects_page_bp)
    app.register_blueprint(pages.jobs_page_bp)
    app.register_blueprint(pages.experiments_page_bp)
    app.register_blueprint(pages.libraries_page_bp)

    return app