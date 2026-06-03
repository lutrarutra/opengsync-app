from fastapi import APIRouter, Depends

from ...core import dependencies

from . import (
    admin,
    auth,
    browser,
    dashboard,
    design,
    devices,
    experiments,
    groups,
    kits,
    lab_preps,
    libraries,
    pools,
    projects,
    protocols,
    samples,
    seq_requests,
    seq_runs,
    share_tokens,
    users,
)

router = APIRouter(tags=["pages"])

# Public routes (no auth required)
router.include_router(auth.router)

# Authenticated routes (require_user)
router.include_router(dashboard.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(projects.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(seq_requests.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(groups.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(kits.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(libraries.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(pools.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(samples.router, dependencies=[Depends(dependencies.require_user)])
router.include_router(users.router, dependencies=[Depends(dependencies.require_user)])

# Insider-only routes
router.include_router(browser.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(design.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(experiments.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(lab_preps.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(protocols.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(seq_runs.router, dependencies=[Depends(dependencies.require_insider)])
router.include_router(share_tokens.router, dependencies=[Depends(dependencies.require_insider)])

# Admin-only routes
router.include_router(admin.router, dependencies=[Depends(dependencies.require_admin)])
router.include_router(devices.router, dependencies=[Depends(dependencies.require_admin)])