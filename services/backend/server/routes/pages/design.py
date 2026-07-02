from fastapi import APIRouter, Depends

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/design", tags=["design"])


@router.get("/")
def design(session: SyncSession = Depends(dependencies.db_session)):
    num_flowcell_designs = session.count(Q.flow_cell_design.select().where(
        models.FlowCellDesign.task_status_id < C.TaskStatus.COMPLETED.id
    ))
    num_archived_flowcell_designs = session.count(Q.flow_cell_design.select().where(
        models.FlowCellDesign.task_status_id >= C.TaskStatus.COMPLETED.id
    ))

    return responses.html_response(
        "design_page.html", title="Design",
        num_flowcell_designs=num_flowcell_designs,
        num_archived_flowcell_designs=num_archived_flowcell_designs,
    )