from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q
from opengsync_db.categories import AccessLevel

from ....core import dependencies, responses, exceptions as exc
from ....forms.workflows import library_annotation as wf

router = APIRouter(prefix="/library_annotation", tags=["library_annotation"], dependencies=[Depends(dependencies.seq_request_permissions)])


@router.get("/{seq_request_id}/previous-step")
async def library_annotation_workflow_previous_step(
    request: Request,
    seq_request_id: int,
    uuid: str = Query(..., description="The UUID of the workflow state."),
    session: AsyncSession = Depends(dependencies.db_session),
):
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id).options(
        orm.joinedload(models.SeqRequest.requestor),
    ))
    form = wf.LibraryAnnotationWorkflow(request=request, seq_request=seq_request, uuid=uuid)
    await form._init_msf_state()
    return await form.previous_step()


@router.get("/{seq_request_id}/begin")
async def begin_library_annotation_workflow(
    request: Request,
    seq_request_id: int,
    session: AsyncSession = Depends(dependencies.db_session),
):
    seq_request = await session.get_one(Q.seq_request.select(id=seq_request_id).options(
        orm.joinedload(models.SeqRequest.requestor),
    ))
    form = wf.ProjectSelectForm(request=request, seq_request=seq_request)
    await form._init_msf_state()
    return await form.make_response()


@router.post("/{seq_request_id}/select-project")
async def library_annotation_workflow_select_project(response = Depends(wf.ProjectSelectForm.process_request)): return response


@router.post("/{seq_request_id}/sample-annotation")
async def library_annotation_workflow_sample_annotation(response = Depends(wf.SampleAnnotationForm.process_request)): return response