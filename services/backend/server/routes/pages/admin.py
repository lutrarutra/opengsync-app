from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/")
def admin_page():
    return responses.html_response("admin_page.html", title="Admin")