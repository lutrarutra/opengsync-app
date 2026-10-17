from flask import Blueprint, render_template, url_for, request

from opengsync_db import models, queries as Q
from opengsync_db.categories import AccessLevel

from ... import forms, db, logger
from ...core import wrappers, exceptions
seq_requests_page_bp = Blueprint("seq_requests_page", __name__)


@wrappers.page_route(seq_requests_page_bp, db=db, cache_timeout_seconds=360)
def seq_requests():
    return render_template("seq_requests_page.html", title="Requests")


@wrappers.page_route(seq_requests_page_bp, "seq_requests", db=db, cache_timeout_seconds=360)
def seq_request(current_user: models.User, seq_request_id: int):
    if (seq_request := db.session.first(Q.seq_request.select(id=seq_request_id))) is None:
        raise exceptions.NotFoundException()

    if db.session.get_access_level(Q.seq_request.permissions(seq_request.id, current_user.id)) < AccessLevel.READ:
        raise exceptions.NoPermissionsException()

    path_list = [
        ("Requests", url_for("seq_request_pages")),
        (f"Request {seq_request_id}", ""),
    ]
    if (_from := request.args.get("from")) is not None:
        page, id = _from.split("@")
        if page == "experiment":
            path_list = [
                ("Experiments", url_for("experiments_page.experiments")),
                (f"Experiment {id}", url_for("experiments_page.experiment", experiment_id=id)),
                (f"Request {seq_request_id}", ""),
            ]
        elif page == "user":
            path_list = [
                ("Users", url_for("user_pages")),
                (f"User {id}", url_for("user_page", user_id=id)),
                (f"Request {seq_request_id}", ""),
            ]
        elif page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"Request {seq_request_id}", ""),
            ]
        elif page == "pool":
            path_list = [
                ("Pools", url_for("pool_pages")),
                (f"Pool {id}", url_for("pool_page", pool_id=id)),
                (f"Request {seq_request_id}", ""),
            ]
        elif page == "group":
            path_list = [
                ("Groups", url_for("group_pages")),
                (f"Group {id}", url_for("group_page", group_id=id)),
                (f"Request {seq_request_id}", ""),
            ]
        elif page == "sample":
            path_list = [
                ("Samples", url_for("sample_pages")),
                (f"Sample {id}", url_for("sample_page", sample_id=id)),
                (f"Request {seq_request_id}", ""),
            ]

    submit_checklist = seq_request.get_submit_checklist()
    submit_steps = [
        submit_checklist["samples_added"],
        submit_checklist["authorization_form_added"],
        submit_checklist["request_submitted"],
    ]

    review_checklist = seq_request.get_review_checklist()

    return render_template(
        "seq_request_page.html",
        seq_request=seq_request,
        path_list=path_list,
        submit_checklist_steps_completed=sum(1 for item in submit_steps if item),
        submit_checklist_steps_total=len(submit_steps),
        review_checklist_steps_completed=sum(1 for item in review_checklist.values() if item),
        review_checklist_steps_total=len(review_checklist),
        title=seq_request.identifier
    )
