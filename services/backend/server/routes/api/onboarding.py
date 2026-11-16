"""Customer onboarding tour progress, read and saved with fetch() from static/js/onboarding-tour.js."""
from fastapi import APIRouter, Depends

from opengsync_db import models, queries as Q, categories as C, exceptions as db_exc, SyncSession

from ...core import dependencies, onboarding, exceptions as exc, redis as rds

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Where the tour resumes when the request it was showing is gone or no longer readable.
CREATE_STEP = "dash.create"


def require_customer(current_user: models.User = Depends(dependencies.require_user)) -> models.User:
    if current_user.is_insider:
        raise exc.NoPermissionsException("The onboarding tour is for customers only.")
    return current_user


def _can_read(session: SyncSession, seq_request_id: int, user_id: int) -> bool:
    try:
        return session.get_access_level(Q.seq_request.permissions(seq_request_id, user_id)) >= C.AccessLevel.READ
    except db_exc.NotFoundException:
        return False


@router.get("", name="onboarding_state")
def get_state(
    current_user: models.User = Depends(require_customer),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    if (state := onboarding.get_state(r, current_user.id)) is None:
        return {"status": None}

    if state.seq_request_id is not None and not _can_read(session, state.seq_request_id, current_user.id):
        state.seq_request_id = None
        if state.step is not None and state.step.startswith("request."):
            state.step = CREATE_STEP
        onboarding.save_state(r, current_user.id, state)

    return state.model_dump(mode="json")


@router.post("", name="save_onboarding_state", dependencies=[Depends(dependencies.verify_csrf_header)])
def save_state(
    body: onboarding.State,
    current_user: models.User = Depends(require_customer),
    session: SyncSession = Depends(dependencies.db_session),
    r: rds.RedisClient = Depends(dependencies.redis),
):
    if body.seq_request_id is not None and not _can_read(session, body.seq_request_id, current_user.id):
        raise exc.BadRequestException("Unknown sequencing request.")

    onboarding.save_state(r, current_user.id, body)
    return body.model_dump(mode="json")
