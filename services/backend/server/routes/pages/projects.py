from fastapi import APIRouter, Depends

from opengsync_db import categories as C, queries as Q, AsyncSession

from ...core import dependencies, responses

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/")
async def projects_page():  
    return await responses.html_response("projects_page.html", title="Projects")


@router.get("/{project_id}")
async def project_page(
    project_id: int,
    access_level: C.AccessLevel = Depends(dependencies.project_permissions),
    session: AsyncSession = Depends(dependencies.db_session)
):
    project = await session.get_one(Q.project.select(id=project_id))
    return await responses.html_response("project_page.html", project=project, title=project.identifier or f"Project #{project.id:04d}", access_level=access_level)