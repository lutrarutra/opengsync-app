from __future__ import annotations

from typing import Literal
from fastapi import Request, Query, Depends
from fastapi.responses import Response
from sqlalchemy import select as sa_select

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import HTMXForm


class CommentForm(HTMXForm):
    template_path = "components/popups/comment-form.html"

    comment = inputs.string.TextAreaInputField("Comment", required=True, max_length=4096)

    def __init__(
        self,
        request: Request,
        *,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ) -> None:
        super().__init__(request)
        self.seq_request_id = seq_request_id
        self.experiment_id = experiment_id
        self.lab_prep_id = lab_prep_id

    @staticmethod
    async def check_permissions(
        current_user: models.User,
        session: AsyncSession,
        *,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ) -> None:
        if seq_request_id is not None:
            if await session.get_access_level(
                Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)
            ) < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to comment on this sequencing request.")
        elif experiment_id is not None or lab_prep_id is not None:
            if not current_user.is_insider():
                raise exc.NoPermissionsException("You do not have permission to comment on this resource.")
        else:
            raise exc.BadRequestException("At least one of seq_request_id, experiment_id, or lab_prep_id must be provided.")

    @staticmethod
    async def submit_form(
        request: Request,
        current_user: models.User = Depends(dependencies.require_user),
        session: AsyncSession = Depends(dependencies.db_session),
        seq_request_id: int | None = Query(None),
        experiment_id: int | None = Query(None),
        lab_prep_id: int | None = Query(None),
    ) -> Response:
        """Process the comment form submission."""
        await CommentForm.check_permissions(
            current_user=current_user,
            session=session,
            seq_request_id=seq_request_id,
            experiment_id=experiment_id,
            lab_prep_id=lab_prep_id,
        )

        form = CommentForm(
            request,
            seq_request_id=seq_request_id,
            experiment_id=experiment_id,
            lab_prep_id=lab_prep_id,
        )
        await form.validate()

        comment = Q.comment.create(
            text=form.comment.data,
            author=current_user,
            seq_request=await session.get_one(Q.seq_request.select(id=seq_request_id)) if seq_request_id else None,
            experiment=await session.get_one(Q.experiment.select(id=experiment_id)) if experiment_id else None,
            lab_prep=await session.get_one(Q.lab_prep.select(id=lab_prep_id)) if lab_prep_id else None,
        )
        session.add(comment)

        # Determine redirect URL based on context
        if seq_request_id is not None:
            redirect = responses.url_for("seq_request_page", seq_request_id=seq_request_id, tab="request-comments-tab")
        elif experiment_id is not None:
            redirect = responses.url_for("experiment_page", experiment_id=experiment_id, tab="experiment-comments-tab")
        elif lab_prep_id is not None:
            redirect = responses.url_for("lab_prep", lab_prep_id=lab_prep_id, tab="comments-tab")
        else:
            redirect = responses.url_for("dashboard")

        return await responses.htmx_response(
            redirect=redirect,
            flash=responses.flash("Comment added successfully.", "success"),
        )