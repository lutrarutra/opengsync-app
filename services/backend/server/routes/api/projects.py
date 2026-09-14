from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, exceptions as exc
from ...utils import parsing
from .shares import get_real_path

router = APIRouter(prefix="/projects", tags=["api", "projects"])


class AddProjectSoftwareRequest(BaseModel):
    project_id: int
    software: str
    version: str
    comment: str | None = None


class DeleteProjectSoftwareRequest(BaseModel):
    project_id: int
    software: str


@router.post("/add-software", dependencies=[Depends(dependencies.require_insider)])
def add_project_software(
    body: AddProjectSoftwareRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    if (project := session.first(Q.project.select(id=body.project_id))) is None:
        raise exc.NotFoundException(f"Project with ID '{body.project_id}' not found.")

    project.set_software(
        software=body.software,
        version=body.version,
        comment=body.comment,
    )
    session.save(project)

    return {"result": "success", "software": project.software}


@router.delete("/delete-software", dependencies=[Depends(dependencies.require_insider)])
def delete_project_software(
    body: DeleteProjectSoftwareRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    if (project := session.first(Q.project.select(id=body.project_id))) is None:
        raise exc.NotFoundException(f"Project with ID '{body.project_id}' not found.")

    try:
        project.delete_software(body.software)
    except KeyError:
        raise exc.NotFoundException(
            f"Software '{body.software.strip().lower()}' not found on project '{body.project_id}'."
        )
    session.save(project)

    return {"result": "success", "software": project.software}


@router.get("/{project_id}/data-paths", dependencies=[Depends(dependencies.require_insider)])
def get_project_data_paths(
    project_id: int,
    session: SyncSession = Depends(dependencies.db_session),
) -> list[str]:
    project = session.first(
        Q.project.select(id=project_id),
        options=[orm.selectinload(models.Project.data_paths)],
    )
    if project is None:
        raise exc.NotFoundException(f"Project with ID '{project_id}' not found.")

    paths = parsing.filter_subpaths([data_path.path for data_path in project.data_paths])
    resolved_paths: list[str] = []
    for path in paths:
        if (real_path := get_real_path(path)) is None:
            raise exc.BadRequestException(f"Data path '{path}' cannot be resolved.")
        resolved_paths.append(real_path)

    return resolved_paths
