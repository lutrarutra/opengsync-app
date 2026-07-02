from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/seq_requests", tags=["seq_requests"])

@router.get("/")
def seq_requests_page():  
    return responses.html_response("seq_requests_page.html", title="Requests")


@router.get("/{seq_request_id}")
def seq_request_page(
    seq_request_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    session: dependencies.SyncSession = Depends(dependencies.db_session),
):
    seq_request = session.get_one(
        Q.seq_request.select(id=seq_request_id).options(
            orm.selectinload(models.SeqRequest.requestor),
            orm.selectinload(models.SeqRequest.group),
            orm.selectinload(models.SeqRequest.contact_person),
            orm.selectinload(models.SeqRequest.organization_contact),
            orm.selectinload(models.SeqRequest.bioinformatician_contact),
            orm.selectinload(models.SeqRequest.billing_contact),
            orm.selectinload(models.SeqRequest.seq_auth_form_file),
            orm.selectinload(models.SeqRequest.delivery_email_links),
            orm.with_expression(models.SeqRequest._num_samples, models.SeqRequest.num_samples.expression),
            orm.with_expression(models.SeqRequest._num_projects, models.SeqRequest.num_projects.expression),
            orm.with_expression(models.SeqRequest._num_libraries, models.SeqRequest.num_libraries.expression),
            orm.with_expression(models.SeqRequest._num_pools, models.SeqRequest.num_pools.expression),
            orm.with_expression(models.SeqRequest._num_files, models.SeqRequest.num_files.expression),
            orm.with_expression(models.SeqRequest._num_comments, models.SeqRequest.num_comments.expression),
            orm.with_expression(models.SeqRequest._num_delivery_email_links, models.SeqRequest.num_delivery_email_links.expression),
            orm.with_expression(models.SeqRequest._num_assignees, models.SeqRequest.num_assignees.expression),
            orm.with_expression(models.SeqRequest._num_data_paths, models.SeqRequest.num_data_paths.expression),
        )
    )
    submit_checklist = seq_request.get_submit_checklist()
    submit_steps = [
        submit_checklist["samples_added"],
        submit_checklist["authorization_form_added"],
        submit_checklist["request_submitted"],
    ]

    review_checklist = seq_request.get_review_checklist()

    return responses.html_response(
        "seq_request_page.html",
        seq_request=seq_request,
        submit_checklist_steps_completed=sum(1 for item in submit_steps if item),
        submit_checklist_steps_total=len(submit_steps),
        review_checklist_steps_completed=sum(1 for item in review_checklist.values() if item),
        review_checklist_steps_total=len(review_checklist),
        title=seq_request.identifier,
    )