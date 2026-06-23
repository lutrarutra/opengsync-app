from fastapi import APIRouter, Depends

from ....core import dependencies

from . import (
    add_kits_to_protocol,
    ba_report,
    check_barcode_clashes,
    check_barcode_constraints,
    dilute_pools,
    dist_reads,
    lane_pools,
    lane_qc,
    library_annotation,
    library_pooling,
    library_prep,
    library_remux,
    load_flow_cell,
    merge_pools,
    merge_projects,
    mux_prep,
    qubit_measure,
    reindex,
    relib,
    reseq,
    select_experiment_pools,
    select_library_protocols,
    select_pool_libraries,
    store_samples,
    share_project_data,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])

# All workflow routes require insider access
insider = [Depends(dependencies.require_insider)]

router.include_router(add_kits_to_protocol.router, dependencies=insider)
router.include_router(ba_report.router, dependencies=insider)
router.include_router(check_barcode_clashes.router)
router.include_router(check_barcode_constraints.router, dependencies=insider)
router.include_router(dilute_pools.router, dependencies=insider)
router.include_router(dist_reads.router, dependencies=insider)
router.include_router(lane_pools.router, dependencies=insider)
router.include_router(lane_qc.router, dependencies=insider)
router.include_router(library_annotation.router)
router.include_router(library_pooling.router, dependencies=insider)
router.include_router(library_prep.router, dependencies=insider)
router.include_router(library_remux.router)
router.include_router(load_flow_cell.router, dependencies=insider)
router.include_router(merge_pools.router, dependencies=insider)
router.include_router(merge_projects.router, dependencies=insider)
router.include_router(mux_prep.router, dependencies=insider)
router.include_router(qubit_measure.router, dependencies=insider)
router.include_router(reindex.router, dependencies=insider)
router.include_router(relib.router, dependencies=insider)
router.include_router(reseq.router, dependencies=insider)
router.include_router(select_experiment_pools.router, dependencies=insider)
router.include_router(select_library_protocols.router, dependencies=insider)
router.include_router(select_pool_libraries.router, dependencies=insider)
router.include_router(store_samples.router, dependencies=insider)
router.include_router(share_project_data.router, dependencies=insider)

