from typing import TYPE_CHECKING

from flask import Blueprint, render_template, url_for, abort, request

from opengsync_db.models import User
from opengsync_db.categories import HTTPResponse
from ... import db, page_route

if TYPE_CHECKING:
    current_user: User = None   # type: ignore
else:
    from flask_login import current_user

share_tokens_page_bp = Blueprint("share_tokens_page", __name__)


@page_route(share_tokens_page_bp, db=db)
def share_tokens():
    return render_template("share_tokens_page.html")


@page_route(share_tokens_page_bp, db=db)
def share_token(share_token_id):
    if not current_user.is_insider():
        return abort(HTTPResponse.FORBIDDEN.id)
    
    if (share_token := db.get_share_token(share_token_id)) is None:
        return abort(HTTPResponse.NOT_FOUND.id)

    path_list = [
        ("share_tokens", url_for("share_tokens_page.share_tokens")),
        (f"Share {share_token_id}", ""),
    ]
    if (_from := request.args.get("from", None)) is not None:
        page, id = _from.split("@")
        if page == "library":
            path_list = [
                ("Libraries", url_for("libraries_page.libraries")),
                (f"Library {id}", url_for("libraries_page.library", library_id=id)),
                (f"share_token {share_token_id}", ""),
            ]
        elif page == "project":
            path_list = [
                ("Projects", url_for("projects_page.projects")),
                (f"Project {id}", url_for("projects_page.project", project_id=id)),
                (f"share_token {share_token_id}", ""),
            ]
        elif page == "seq_request":
            path_list = [
                ("Requests", url_for("seq_requests_page.seq_requests")),
                (f"Request {id}", url_for("seq_requests_page.seq_request", seq_request_id=id)),
                (f"share_token {share_token_id}", ""),
            ]

    return render_template(
        "share_token_page.html",
        path_list=path_list, share_token=share_token,
    )
