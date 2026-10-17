from opengsync_db import SyncSession, models
from opengsync_db.categories import (
    LibraryStatus as LB, PoolStatus as PL, SeqRequestStatus as RQ, ExperimentWorkFlow,
)
from opengsync_db.transitions import entities as E, kanban, run_operation

from ..create_units import (
    create_user, create_seq_request, create_library, create_lab_prep, create_pool, create_project, create_sample,
    create_experiment,
)


def _columns(board):
    return {(c.status.name if c.status else "OTHER"): c for c in board.columns}


def test_lab_prep_board(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)
    pool = create_pool(session, user, seq_request)
    libraries = [create_library(session, user, seq_request) for _ in range(3)]
    for library, status in zip(libraries, (LB.PREPARING, LB.POOLED, LB.FAILED)):
        library.lab_prep_id = lab_prep.id
        library.status = status
    libraries[1].pool_id = pool.id
    create_library(session, user, seq_request)  # not in the prep
    session.commit()

    board = kanban.build(session, lab_prep, E.LAB_PREP)
    assert board is not None and board.child == E.LIBRARY and board.total == 3
    columns = _columns(board)
    # columns start at PREPARING (nothing earlier is occupied) and run through the main statuses
    assert [c.status for c in board.columns if c.status] == [s for s in LB.as_list() if LB.PREPARING.id <= s.id < 10]
    assert [c.id for c in columns["PREPARING"].cards] == [libraries[0].id]
    pooled = columns["POOLED"].cards[0]
    assert pooled.group == f"BSR_{seq_request.id:04d}"
    assert pooled.details == [f"pool {pool.name}"]
    # side states share one column
    assert [c.id for c in columns["OTHER"].cards] == [libraries[2].id]
    assert columns["STORED"].total == 0


def test_project_board_counts_library_progress(session: SyncSession):
    user = create_user(session)
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    seq_request = create_seq_request(session, user)
    seq_request.status = RQ.SAMPLES_RECEIVED
    libraries = [create_library(session, user, seq_request) for _ in range(3)]
    libraries[0].status = LB.SEQUENCED
    libraries[1].status = LB.FAILED
    for library in libraries:
        session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))
    create_seq_request(session, user)  # not in the project
    session.commit()

    board = kanban.build(session, project, E.PROJECT)
    assert board.total == 1
    card = _columns(board)["SAMPLES_RECEIVED"].cards[0]
    assert card.id == seq_request.id
    assert card.details == ["1/3 libraries sequenced", "1 failed"]
    assert card.next_step  # from the request's status report
    # earlier statuses from SUBMITTED on get a column even when empty
    assert board.columns[0].status == RQ.SUBMITTED


def test_experiment_board_shows_lanes(session: SyncSession):
    user = create_user(session)
    experiment = create_experiment(session, user, ExperimentWorkFlow.NOVASEQ_6K_S4_XP)
    seq_request = create_seq_request(session, user)
    laned, unlaned = create_pool(session, user, seq_request), create_pool(session, user, seq_request)
    for pool in (laned, unlaned):
        pool.experiment_id = experiment.id
        pool.status = PL.STORED
    library = create_library(session, user, seq_request)
    library.pool_id = laned.id
    lane = next(lane for lane in experiment.lanes if lane.number == 2)
    session.add(models.links.LanePoolLink(lane_id=lane.id, pool_id=laned.id, experiment_id=experiment.id, lane_num=lane.number))
    session.commit()

    board = kanban.build(session, experiment, E.EXPERIMENT)
    cards = {c.id: c for c in _columns(board)["STORED"].cards}
    assert cards[laned.id].details == ["1 libraries", "lane 2"]
    assert cards[unlaned.id].details == ["0 libraries", "no lane"]


def test_age_ignores_the_migration_baseline(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)
    tracked, baseline = create_library(session, user, seq_request), create_library(session, user, seq_request)
    for library in (tracked, baseline):
        library.lab_prep_id = lab_prep.id
    session.commit()
    tracked.status = LB.PREPARING
    with run_operation(session, "migration.baseline", reason="status at migration"):
        baseline.status = LB.PREPARING
    session.commit()

    cards = {c.id: c for c in _columns(kanban.build(session, lab_prep, E.LAB_PREP))["PREPARING"].cards}
    assert cards[tracked.id].days_in_status == 0
    assert cards[baseline.id].since is None and cards[baseline.id].days_in_status is None


def test_card_limit_counts_the_rest(session: SyncSession):
    user = create_user(session)
    seq_request = create_seq_request(session, user)
    lab_prep = create_lab_prep(session, user)
    for _ in range(3):
        library = create_library(session, user, seq_request)
        library.lab_prep_id = lab_prep.id
        library.status = LB.PREPARING
    session.commit()

    column = _columns(kanban.build(session, lab_prep, E.LAB_PREP, limit=2))["PREPARING"]
    assert (len(column.cards), column.total, column.hidden) == (2, 3, 1)


def test_no_board_for_requests(session: SyncSession):
    user = create_user(session)
    assert kanban.build(session, create_seq_request(session, user), E.SEQ_REQUEST) is None
