import os
import mimetypes

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import orm

from opengsync_db import models, AsyncSession, queries as Q, categories as C, utils

from ...core import dependencies, responses, exceptions as exc, config
from ...components.tables import HTMXTable, TableCol
from ... import forms


router = APIRouter(prefix="/comments", tags=["comments"])

@router.get("/render-thread")
async def render_comment_thread(
    seq_request_id: int | None = Query(None, description="Optional seq request ID to filter comments"),
    experiment_id: int | None = Query(None, description="Optional experiment ID to filter comments"),
    lab_prep_id: int | None = Query(None, description="Optional lab prep ID to filter comments"),
    current_user: models.User = Depends(dependencies.require_user),
    session: AsyncSession = Depends(dependencies.db_session)
) -> Response:
    
    if seq_request_id is not None:
        if await session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.READ:
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(seq_request_id=seq_request_id))
    elif experiment_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(experiment_id=experiment_id))
    elif lab_prep_id is not None:
        if not current_user.is_insider():
            raise exc.NoPermissionsException("You do not have permission to view this resource.")
        comments = await session.get_all(Q.comment.select(lab_prep_id=lab_prep_id))
    else:
        raise exc.BadRequestException("At least one of seq_request_id, experiment_id, or lab_prep_id must be provided.")

    return await responses.htmx_response("components/comment-thread.html", comments=comments)