from fastapi import APIRouter, Depends, Request

from opengsync_db import models, SyncSession
from opengsync_db.categories import LabChecklistType, LibraryType

from ....core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/library_prep", tags=["library_prep"])


@router.get("/begin/{lab_prep_id}")
def begin_library_prep_workflow(
    request: Request,
    lab_prep_id: int,
    current_user: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
):
    """Begin the library prep workflow."""
    # TODO: Port SelectSamplesForm to FastAPI HTMXForm
    # lab_prep = session.first(Q.lab_prep.select(id=lab_prep_id))
    # if lab_prep is None:
    #     raise exc.NotFoundException()
    # library_type_filter = None
    # if lab_prep.checklist_type != LabChecklistType.CUSTOM:
    #     library_type_filter = LibraryType.get_check_list_library_types(lab_prep.checklist_type) or None
    # form = SelectSamplesForm(
    #     workflow="library_prep",
    #     select_libraries=True,
    #     select_all_libraries=True,
    #     library_type_filter=library_type_filter,
    #     context={"lab_prep": lab_prep},
    # )
    # return form.make_response()
    pass