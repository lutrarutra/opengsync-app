"""Flowcell loading, read statistics and the run folder scanner."""
from ._common import *  # noqa: F401,F403
from ._common import collect

LOAD_FLOWCELL = operation(
    "experiment.load_flowcell", "Load flowcell", K.ACTION, E.EXPERIMENT,
    effect(E.EXPERIMENT, ANY, EX.LOADED, when="every lane is loaded",
           gap="no status check: re-submitting can move a SEQUENCED or DEMULTIPLEXED experiment back to LOADED"),
    where=[B + "forms/actions/load_flowcell/LoadFlowCellCombinedAction.py", B + "forms/actions/load_flowcell/LoadFlowCellSeparateAction.py"],
)

LANE_READS = operation(
    "api.lane_reads", "Set library lane reads (API)", K.API, E.EXPERIMENT,
    effect(E.LIBRARY, below(LB.SEQUENCED), LB.SEQUENCED, via="libraries"),
    effect(E.POOL, below(PL.SEQUENCED), PL.SEQUENCED, via="pools"),
    effect(E.EXPERIMENT, below(EX.DEMULTIPLEXED), EX.DEMULTIPLEXED, when="every sequenced library of the experiment has read qualities"),
    where=[B + "routes/api/stats.py:set_library_lane_reads", DB + "core/actions.py:set_library_seq_quality"],
)

_SEQUENCED_CASCADE = (
    effect(E.POOL, below(PL.SEQUENCED), PL.SEQUENCED, via="experiment.pools"),
    effect(E.LIBRARY, below(LB.SEQUENCED), LB.SEQUENCED, via="experiment.pools.libraries"),
)
_RF = [W + "tasks/rf_scanner.py:process_run_folder"]

RF_FOLDER_MISSING = operation(
    "worker.rf_folder_missing", "Run folder removed", K.WORKER, E.SEQ_RUN,
    effect(E.SEQ_RUN, [RN.FINISHED, RN.RUNNING], RN.ARCHIVED),
    effect(E.EXPERIMENT, ANY, EX.ARCHIVED, via="experiment"),
    *_SEQUENCED_CASCADE,
    reason="run folder {folder} no longer exists", where=_RF,
)

RF_RUN_FINISHED = operation(
    "worker.rf_run_finished", "Finished run cascade", K.WORKER, E.SEQ_RUN,
    effect(E.EXPERIMENT, ANY, [EX.SEQUENCED, EX.DEMULTIPLEXED], via="experiment", when="DEMULTIPLEXED if it has read qualities",
           gap="runs on every scan and overwrites manual experiment statuses (FAILED, ARCHIVED)"),
    *_SEQUENCED_CASCADE,
    reason="run {run} is FINISHED (RTAComplete.txt found in {folder})", where=_RF,
)

RF_RUN_RUNNING = operation(
    "worker.rf_run_running", "Running run cascade", K.WORKER, E.SEQ_RUN,
    effect(E.EXPERIMENT, below(EX.SEQUENCING), EX.SEQUENCING, via="experiment"),
    reason="run {run} is RUNNING (no RTAComplete.txt in {folder})", where=_RF,
)

RF_FOLDER_BACK = operation(
    "worker.rf_folder_back", "Run folder reappeared", K.WORKER, E.SEQ_RUN,
    effect(E.SEQ_RUN, RN.ARCHIVED, RN.FINISHED),
    effect(E.EXPERIMENT, ANY, [EX.SEQUENCED, EX.DEMULTIPLEXED], via="experiment"),
    *_SEQUENCED_CASCADE,
    reason="run folder {folder} reappeared", where=_RF,
)

RF_RUN_STATUS = operation(
    "worker.rf_run_status", "Run status from run folder", K.WORKER, E.SEQ_RUN,
    effect(E.SEQ_RUN, ANY, [RN.RUNNING, RN.FINISHED], when="FINISHED if RTAComplete.txt exists; a renamed folder only moves forward"),
    reason="status read from run folder {folder} ({marker})", where=_RF,
)

RF_NEW_RUN = operation(
    "worker.rf_new_run", "New run folder", K.WORKER, E.SEQ_RUN,
    effect(E.SEQ_RUN, NEW, [RN.RUNNING, RN.FINISHED]),
    reason="new run folder {folder} detected ({marker})", where=_RF,
)

ALL = collect(globals())
