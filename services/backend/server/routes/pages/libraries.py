from fastapi import APIRouter, Depends

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
    library = session.get_one(Q.library.select(id=library_id))
    return responses.html_response(
        "library_page.html",
        library=library,
        access_level=access_level,
        title=f"Library #{library_id:04d}",
    )