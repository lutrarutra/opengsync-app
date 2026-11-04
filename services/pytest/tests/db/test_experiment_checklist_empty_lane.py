"""A lane without pools needs no lane QC or loading (insider test 2026-11-04).

One pool on a 2-lane flow cell: the empty lane kept 'Measure Qubit for each Lane' open and so blocked
'Load Flowcell', although the step's note says it is optional when every lane has a single pool.
"""
from opengsync_db import SyncSession, models, categories as C

from .create_units import create_user, create_experiment, create_pool, create_seq_request


def test_empty_lane_does_not_block_lane_qc_and_loading(session: SyncSession):
    user = create_user(session)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    session.refresh(experiment)
    assert len(experiment.lanes) == 2
    lane1 = next(lane for lane in experiment.lanes if lane.number == 1)

    pool = create_pool(session, user, create_seq_request(session, user))
    pool.qubit_concentration = 4.2
    pool.avg_fragment_size = 380
    pool.experiment_id = experiment.id
    session.save(pool, flush=True)
    session.add(models.links.LanePoolLink(lane_id=lane1.id, pool_id=pool.id, experiment_id=experiment.id, lane_num=1))
    session.flush()
    session.expire_all()

    checklist = session.get(models.Experiment, experiment.id).get_checklist()
    assert checklist["laning_completed"] is True
    assert checklist["lane_qubit_measured"] is True
    assert checklist["lane_fragment_size_measured"] is True
    assert checklist["missing_lane_qubits"] == set()

    lane1 = session.get(models.Lane, lane1.id)
    lane1.phi_x, lane1.sequencing_qubit_concentration, lane1.total_volume_ul = 1.0, 0.8, 50.0
    lane1.library_volume_ul, lane1.target_molarity = 15.0, 3.0
    session.flush()
    session.expire_all()
    assert session.get(models.Experiment, experiment.id).get_checklist()["flowcell_loaded"] is True


def test_pools_not_yet_laned_keep_lane_steps_closed(session: SyncSession):
    """With no lane holding a pool, lane QC and loading are not vacuously done."""
    user = create_user(session)
    experiment = create_experiment(session, user, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
    pool = create_pool(session, user, create_seq_request(session, user))
    pool.experiment_id = experiment.id
    session.save(pool, flush=True)
    session.expire_all()

    checklist = session.get(models.Experiment, experiment.id).get_checklist()
    assert checklist["laning_completed"] is False
    assert checklist["lane_qubit_measured"] is None
    assert checklist["lane_fragment_size_measured"] is None
    assert checklist["flowcell_loaded"] is None
