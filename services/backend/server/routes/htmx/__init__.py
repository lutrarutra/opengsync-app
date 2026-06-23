from fastapi import APIRouter, Depends


from . import (
    auth,
    seq_requests,
    events,
    workflows,
    lab_preps,
    projects,
    samples,
    experiments,
    share_tokens,
    users,
    affiliations,
    pools,
    groups,
    files,
    libraries,
    comments,
)

router = APIRouter(prefix="/htmx", tags=["pages", "htmx"])
router.include_router(auth.router)
router.include_router(seq_requests.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(lab_preps.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(events.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(workflows.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(projects.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(pools.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(samples.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(experiments.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(share_tokens.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(users.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(affiliations.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(groups.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(files.router, dependencies=[])
router.include_router(libraries.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(comments.router, dependencies=[Depends(auth.dependencies.require_user)])
