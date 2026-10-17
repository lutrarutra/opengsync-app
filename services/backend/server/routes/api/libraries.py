from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, exceptions as exc

router = APIRouter(prefix="/libraries", tags=["api", "libraries"])


class AddLibraryQCRequest(BaseModel):
    library_id: int
    qc: dict[str, Any]


class DeleteLibraryQCRequest(BaseModel):
    library_id: int
    keys: list[str]


@router.post("/add-qc", dependencies=[Depends(dependencies.require_insider)])
def add_library_qc(
    body: AddLibraryQCRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    if not body.qc:
        raise exc.BadRequestException("At least one QC value must be provided.")

    if (library := session.first(Q.library.select(id=body.library_id))) is None:
        raise exc.NotFoundException(f"Library with ID '{body.library_id}' not found.")

    library.set_qc(body.qc)
    session.save(library)

    return {"result": "success", "qc": library.qc or {}}


@router.delete("/delete-qc", dependencies=[Depends(dependencies.require_insider)])
def delete_library_qc(
    body: DeleteLibraryQCRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    if not body.keys:
        raise exc.BadRequestException("At least one QC key must be provided.")

    if (library := session.first(Q.library.select(id=body.library_id))) is None:
        raise exc.NotFoundException(f"Library with ID '{body.library_id}' not found.")

    try:
        library.delete_qc(body.keys)
    except KeyError as error:
        missing_key = error.args[0]
        raise exc.NotFoundException(
            f"QC key '{missing_key}' not found on library '{body.library_id}'."
        )
    session.save(library)

    return {"result": "success", "qc": library.qc or {}}
