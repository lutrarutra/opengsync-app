from fastapi import APIRouter, Depends


from . import (
    auth, seq_requests, events, workflows, lab_preps
)

router = APIRouter(tags=["pages", "htmx"])
router.include_router(auth.router)
router.include_router(seq_requests.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(lab_preps.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(events.router)
router.include_router(workflows.router)