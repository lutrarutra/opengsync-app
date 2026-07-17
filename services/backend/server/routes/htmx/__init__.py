from fastapi import APIRouter, Depends


from . import (
    auth,
    actions,
    seq_requests,
    events,
    workflows,
    lab_preps,
    projects,
    samples,
    experiments,
    share_tokens,
    users,
    sequencers,
    affiliations,
    pools,
    groups,
    files,
    libraries,
    comments,
    flow_cell_design,
    pool_design,
    dilutions,
    protocols,
    kits,
)

router = APIRouter(prefix="/htmx", tags=["pages", "htmx"])
router.include_router(auth.router)
router.include_router(files.router, dependencies=[])
router.include_router(workflows.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(actions.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(seq_requests.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(lab_preps.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(events.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(projects.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(pools.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(samples.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(experiments.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(sequencers.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(share_tokens.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(users.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(affiliations.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(groups.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(libraries.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(comments.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(flow_cell_design.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(pool_design.router, dependencies=[Depends(auth.dependencies.require_insider)])
router.include_router(dilutions.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(protocols.router, dependencies=[Depends(auth.dependencies.require_user)])
router.include_router(kits.router, dependencies=[Depends(auth.dependencies.require_user)])
