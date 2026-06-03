from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/")
async def admin_page():
    return await responses.html_response("admin_page.html", title="Admin")