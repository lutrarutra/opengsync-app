from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, categories as C, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/samples", tags=["samples"])


@router.get("/")
def samples_page():
    return responses.html_response(template="samples_page.html", title="Samples")


@router.get("/{sample_id}")
def sample_page(
    sample_id: int,
    access_level: C.AccessLevel = Depends(dependencies.sample_permissions),
    session: SyncSession = Depends(dependencies.db_session),
):
    sample = session.get_one(Q.sample.select(id=sample_id).options(
        orm.selectinload(models.Sample.owner),
        orm.selectinload(models.Sample.project),
        orm.selectinload(models.Sample.ba_report).selectinload(models.MediaFile.uploader),
        orm.with_expression(models.Sample._num_libraries, models.Sample.num_libraries.expression),
    ))
    
    return responses.html_response(
        template="sample_page.html",
        sample=sample,
        access_level=access_level,
        title=f"Sample {sample.name}",
    )