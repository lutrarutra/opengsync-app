from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/login", tags=["login"])

@router.get("/")
async def login(
    current_user: models.User | None = Depends(dependencies.get_user)
):
    if current_user:
        return RedirectResponse(url="/dashboard")
    
    return await responses.html_response("auth_page.html")