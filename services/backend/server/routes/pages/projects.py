from fastapi import APIRouter, Depends

from ...core import dependencies, responses

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/")
async def projects_page():  
    return await responses.html_response("projects_page.html", title="Projects")


@router.get("/{project_id}", dependencies=[Depends(dependencies.project_permissions)] )
async def project_page(project_id: int):
    return await responses.html_response(
        "project_page.html",
        project_id=project_id,
        title=f"Project {project_id}",
    )