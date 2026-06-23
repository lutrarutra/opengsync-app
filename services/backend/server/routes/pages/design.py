from fastapi import APIRouter, Depends

from opengsync_db import models, categories as C, AsyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/design", tags=["design"])


@router.get("/")
async def design(session: AsyncSession = Depends(dependencies.db_session)):
    num_flowcell_designs = await session.count(Q.flow_cell_design.select().where(
        models.FlowCellDesign.task_status_id < C.TaskStatus.COMPLETED.id
    ))
    num_archived_flowcell_designs = await session.count(Q.flow_cell_design.select().where(
        models.FlowCellDesign.task_status_id >= C.TaskStatus.COMPLETED.id
    ))

    return await responses.html_response(
        "design_page.html", title="Design",
        num_flowcell_designs=num_flowcell_designs,
        num_archived_flowcell_designs=num_archived_flowcell_designs,
    )