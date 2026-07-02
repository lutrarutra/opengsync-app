from fastapi import APIRouter, Depends, Query
from sqlalchemy import orm

from opengsync_db import categories as C, queries as Q, SyncSession, models

from ...core import dependencies, responses

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/")
def projects_page(path_list: list = Depends(dependencies.parse_from_page)):
    return responses.html_response("projects_page.html", title="Projects", path_list=path_list)


@router.get("/{project_id}")
def project_page(
    project_id: int,
    access_level: C.AccessLevel = Depends(dependencies.project_permissions),
    session: SyncSession = Depends(dependencies.db_session),
    path_list: list = Depends(dependencies.parse_from_page),
):
    project = session.get_one(Q.project.select(id=project_id).options(
        orm.with_expression(models.Project._num_samples, models.Project.num_samples.expression),
        orm.with_expression(models.Project._num_seq_requests, models.Project.num_seq_requests.expression),
        orm.with_expression(models.Project._num_experiments, models.Project.num_experiments.expression),
        orm.with_expression(models.Project._num_assignees, models.Project.num_assignees.expression),
        orm.with_expression(models.Project._num_data_paths, models.Project.num_data_paths.expression),
        orm.selectinload(models.Project.owner),
        orm.selectinload(models.Project.group),
        orm.selectinload(models.Project.share_token),
    ))

    return responses.html_response("project_page.html", project=project, title=project.identifier or f"Project #{project.id:04d}", access_level=access_level, path_list=path_list)