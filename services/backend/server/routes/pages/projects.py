from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/")
async def projects():  
    return await responses.html_response("projects_page.html", title="Projects")


@router.get("/{project_id}")
async def project(
    project_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Project lookup, access checks, and breadcrumb resolution
    # are handled client-side via API calls.
    return await responses.html_response(
        "project_page.html",
        project_id=project_id,
        title=f"Project {project_id}",
    )