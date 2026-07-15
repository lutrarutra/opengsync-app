from fastapi import APIRouter, Depends

from ...core import dependencies
from ...forms import workflows as wf

router = APIRouter(prefix="/workflows", tags=["workflows"])

insider = [Depends(dependencies.require_insider)]
router.include_router(wf.library_annotation.LibraryAnnotationWorkflow.Router())
router.include_router(wf.select_library_protocols.SelectLibraryProtocolsWorkflow.Router())
router.include_router(wf.qubit_measure.QubitMeasureWorkflow.Router())
router.include_router(wf.ba_report.BAReportWorkflow.Router())
router.include_router(wf.lane_pools.LanePoolsWorkflow.Router())
router.include_router(wf.select_experiment_pools.SelectExperimentPoolsWorkflow.Router())
router.include_router(wf.dilute_pools.DilutePoolsWorkflow.Router())
router.include_router(wf.lane_qc.LaneQCWorkflow.Router())
router.include_router(wf.load_flow_cell.LoadFlowCellWorkflow.Router())
router.include_router(wf.library_pooling.LibraryPoolingWorkflow.Router())
router.include_router(wf.mux_prep.MuxPrepWorkflow.Router())
router.include_router(wf.dist_reads.DistributeReadsWorkflow.Router())
router.include_router(wf.reindex.ReindexWorkflow.Router())
router.include_router(wf.merge_pools.MergePoolsWorkflow.Router())
router.include_router(wf.library_remux.LibraryRemuxWorkflow.Router())
router.include_router(wf.relib.RelibWorkflow.Router())
router.include_router(wf.share_project_data.ShareProjectDataWorkflow.Router())
router.include_router(wf.check_barcode_constraints.CheckBarcodeConstraintsWorkflow.Router())
router.include_router(wf.add_kits_to_protocol.AddKitsToProtocolWorkflow.Router())
router.include_router(wf.select_library_protocols.SelectLibraryProtocolsWorkflow.Router())
router.include_router(wf.merge_projects.MergeProjectsWorkflow.Router())

