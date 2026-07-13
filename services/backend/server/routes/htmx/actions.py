from fastapi import APIRouter

from ...forms import actions

router = APIRouter(prefix="/actions", tags=["actions"])
router.include_router(actions.StoreSamplesAction.Router())