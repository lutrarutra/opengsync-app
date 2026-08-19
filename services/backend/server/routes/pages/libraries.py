from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, responses

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("/")
def libraries_page():
    return responses.html_response("libraries_page.html", title="Libraries")


@router.get("/{library_id}")
def library_page(
    library_id: int,
    session: SyncSession = Depends(dependencies.db_session),
    access_level: C.AccessLevel = Depends(dependencies.library_permissions),
):
    library = session.get_one(Q.library.select(id=library_id).options(
        orm.selectinload(models.Library.seq_request),
        orm.selectinload(models.Library.pool),
        orm.selectinload(models.Library.experiment),
        orm.selectinload(models.Library.owner),
        orm.selectinload(models.Library.lab_prep),
        orm.selectinload(models.Library.protocol),
        orm.selectinload(models.Library.original_library),
        orm.selectinload(models.Library.indices).options(
            orm.selectinload(models.LibraryIndex.index_kit_i7),
            orm.selectinload(models.LibraryIndex.index_kit_i5),
        ),
        orm.selectinload(models.Library.ba_report).selectinload(models.MediaFile.uploader),
        orm.with_expression(models.Library._num_samples, models.Library.num_samples.expression),
        orm.with_expression(models.Library._num_features, models.Library.num_features.expression),
        orm.with_expression(models.Library._num_data_paths, models.Library.num_data_paths.expression),
    ))
    return responses.html_response(
        "library_page.html",
        library=library,
        access_level=access_level,
        title=f"Library #{library_id:04d}",
    )