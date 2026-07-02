from fastapi import APIRouter, Depends
from sqlalchemy import orm

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ...core import dependencies, responses, exceptions as exc

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/")
def users_page(
    current_user: models.User = Depends(dependencies.require_insider),
):
    return responses.html_response("users_page.html", title="Users")


@router.get("/{user_id}")
def user_page(
    user_id: int,
    access_level: C.AccessLevel = Depends(dependencies.user_permissions),
    session: SyncSession = Depends(dependencies.db_session)
):
    user = session.get_one(
        Q.user.select(id=user_id).options(
            orm.with_expression(models.User._num_projects, models.User.num_projects.expression),
            orm.with_expression(models.User._num_seq_requests, models.User.num_seq_requests.expression),
            orm.with_expression(models.User._num_affiliations, models.User.num_affiliations.expression),
            orm.with_expression(models.User._num_api_tokens, models.User.num_api_tokens.expression)
        )
    )

    return responses.html_response(
        "user_page.html", user=user, title=f"{user.name}", access_level=access_level
    )