from fastapi import APIRouter

from ...forms import actions

router = APIRouter(prefix="/actions", tags=["actions"])
router.include_router(actions.StoreSamplesAction.Router())
router.include_router(actions.CheckBarcodeClashesAction.Router())
router.include_router(actions.BillingAction.Router())
router.include_router(actions.SelectPoolLibrariesAction.Router())