from fastapi import APIRouter, Depends

from ...core import dependencies, responses

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(dependencies.require_admin)])


@router.get("/")
def admin_page():
    return responses.html_response("admin_page.html", title="Admin")