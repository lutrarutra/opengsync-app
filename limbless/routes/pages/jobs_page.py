from flask import Blueprint, render_template, redirect, request
from sqlmodel import Session

from ... import models, forms
from ... import db

jobs_page_bp = Blueprint("jobs_page", __name__)


@jobs_page_bp.route("/jobs", methods=["GET", "POST"])
def jobs_page():
    form = forms.JobForm()

    if form.validate_on_submit():
        with Session(db.db_handler.engine) as session:
            job = models.Job(name=form.name.data)
            session.add(job)
            session.commit()
            redirect(request.url)

    with Session(db.db_handler.engine) as session:
        jobs = session.query(models.Job).all()

    return render_template("jobs_page.html", form=form, jobs=jobs)
