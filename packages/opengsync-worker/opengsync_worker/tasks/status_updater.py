import sqlalchemy as sa

from opengsync_db import categories as C, models, SyncDBHandler, queries as Q
from opengsync_db.transitions import run_operation, worker as ops

from . import logger


def __find_stored_samples(q):
    return q.where(
        ~sa.exists().where(
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status < C.LibraryStatus.STORED)
        )
    )

def __find_seq_requests_with_stored_samples(q):
    return q.filter(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.links.SampleLibraryLink.library_id == models.Library.id) &
            (models.Sample.id == models.links.SampleLibraryLink.sample_id)
        )
    ).filter(
        sa.and_(
            ~sa.exists().where(
                (models.Library.seq_request_id == models.SeqRequest.id) &
                (models.links.SampleLibraryLink.library_id == models.Library.id) &
                (models.Sample.id == models.links.SampleLibraryLink.sample_id) &
                (models.Sample.status < C.SampleStatus.STORED)
            ),
            ~sa.exists().where(
                (models.Library.seq_request_id == models.SeqRequest.id) &
                (models.links.SampleLibraryLink.library_id == models.Library.id) &
                (models.Library.pool_id == models.Pool.id) &
                (models.Pool.status < C.PoolStatus.STORED)
            )
        )
    )

def __find_seq_requests_with_pooled_libraries(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status == C.LibraryStatus.POOLED)
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status < C.LibraryStatus.POOLED)
        )
    )


def __find_finished_experiments(q):
    return q.join(
        models.SeqRun,
        models.SeqRun.experiment_name == models.Experiment.name,
    ).where(
        models.SeqRun.status.in_([
            C.RunStatus.FINISHED, C.RunStatus.ARCHIVED,
        ])
    )


def __find_finished_libraries(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Library.experiment_id,
    ).where(
        models.Experiment.status.in_([
            C.ExperimentStatus.SEQUENCED,
            C.ExperimentStatus.DEMULTIPLEXED,
            C.ExperimentStatus.ARCHIVED,
        ])
    )


def __find_sequenced_pools(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Pool.experiment_id,
    ).where(
        models.Experiment.status.in_([
            C.ExperimentStatus.SEQUENCED,
            C.ExperimentStatus.DEMULTIPLEXED,
            C.ExperimentStatus.ARCHIVED,
        ])
    )


def __find_sequenced_seq_requests(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status.in_([
                C.LibraryStatus.SEQUENCED,
                C.LibraryStatus.SHARED,
                C.LibraryStatus.ARCHIVED,
            ]))
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status < C.LibraryStatus.SEQUENCED)
        )
    )


# Libraries that still have lab/sequencing work ahead of them. DRAFT/SUBMITTED are not counted,
# so a customer drafting a new request does not re-open a project before staff accept it.
# QC_PENDING is not counted either: QC_COMPLETED is never set, so QC-only work would re-open forever.
OPEN_LIBRARY_STATUSES = [
    C.LibraryStatus.ACCEPTED,
    C.LibraryStatus.PREPARING,
    C.LibraryStatus.STORED,
    C.LibraryStatus.POOLED,
]

SEQUENCED_LIBRARY_STATUSES = [
    C.LibraryStatus.SEQUENCED,
    C.LibraryStatus.SHARED,
    C.LibraryStatus.ARCHIVED,
]


def __project_has_library(statuses: list[C.LibraryStatus]):
    return sa.exists().where(
        (models.Sample.project_id == models.Project.id) &
        (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
        (models.Library.id == models.links.SampleLibraryLink.library_id) &
        (models.Library.status.in_(statuses))
    )


def __find_reopened_seq_requests(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status.in_(OPEN_LIBRARY_STATUSES))
        )
    )


def __find_reopened_projects(q):
    return q.where(__project_has_library(OPEN_LIBRARY_STATUSES))


def __find_sequenced_projects(q):
    return q.where(
        __project_has_library(SEQUENCED_LIBRARY_STATUSES)
    ).where(
        ~__project_has_library(OPEN_LIBRARY_STATUSES)
    )


def __find_finished_seq_requests(q):
    return q.where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status < C.LibraryStatus.SHARED)
        )
    )


def update_statuses(db: SyncDBHandler):
    """Applies the status worker rules in order. Each rule runs as its own operation
    (opengsync_db.transitions.operations.worker), so every change is recorded with the rule as reason.
    Leaving each `run_operation` block flushes, so later rules see the earlier changes."""
    logs = ["Checking statuses.."]

    with run_operation(db.session, ops.EXPERIMENT_SEQUENCING) as op:
        for run in db.session.get_all(Q.seq_run.select(status=C.RunStatus.RUNNING), limit=None):
            if run.experiment is not None:
                run.experiment.status = C.ExperimentStatus.SEQUENCING
                op.detail(run.experiment, f"seq run {run.run_folder}")
                logs.append(f"Updating experiment {run.experiment.id} status to {run.experiment.status}")
                db.session.save(run)

    with run_operation(db.session, ops.EXPERIMENT_RUN_FINISHED) as op:
        for experiment in db.session.get_all(__find_finished_experiments(Q.experiment.select(
            status_in=[
                C.ExperimentStatus.DRAFT,
                C.ExperimentStatus.LOADED,
                C.ExperimentStatus.SEQUENCING,
            ],
        )), limit=None):
            if experiment.seq_run is None:
                experiment.status = C.ExperimentStatus.SEQUENCED
            else:
                if experiment.seq_run.status == C.RunStatus.FINISHED:
                    experiment.status = C.ExperimentStatus.SEQUENCED
                elif experiment.seq_run.status == C.RunStatus.ARCHIVED:
                    experiment.status = C.ExperimentStatus.ARCHIVED
                else:
                    continue
                op.detail(experiment, f"seq run {experiment.seq_run.run_folder} is {experiment.seq_run.status.name}")
                logs.append(f"Updating experiment {experiment.id} status to {experiment.status}")
                db.session.save(experiment)

    with run_operation(db.session, ops.LIBRARY_SEQUENCED) as op:
        for library in db.session.get_all(__find_finished_libraries(Q.library.select(
            status_in=[
                C.LibraryStatus.POOLED, C.LibraryStatus.STORED, C.LibraryStatus.PREPARING,
                C.LibraryStatus.ACCEPTED, C.LibraryStatus.SUBMITTED, C.LibraryStatus.DRAFT,
            ]
        )), limit=None):
            if library.experiment is not None:
                library.status = C.LibraryStatus.SEQUENCED
                op.detail(library, f"experiment {library.experiment.name} is {library.experiment.status.name}")
                logs.append(f"Updating library {library.id} status to {library.status}")
                db.session.save(library)

    with run_operation(db.session, ops.SAMPLE_STORED):
        for sample in db.session.get_all(__find_stored_samples(Q.sample.select(
            status=C.SampleStatus.WAITING_DELIVERY,
        )), limit=None):
            sample.status = C.SampleStatus.STORED
            logs.append(f"Updating sample {sample.id} status to {sample.status}")
            db.session.save(sample)

    with run_operation(db.session, ops.POOL_SEQUENCED) as op:
        for pool in db.session.get_all(__find_sequenced_pools(Q.pool.select(
            status_in=[C.PoolStatus.ACCEPTED, C.PoolStatus.STORED],
        )), limit=None):
            pool.status = C.PoolStatus.SEQUENCED
            if pool.experiment is not None:
                op.detail(pool, f"experiment {pool.experiment.name} is {pool.experiment.status.name}")
            logs.append(f"Updating pool {pool.id} status to {pool.status}")
            db.session.save(pool)

    # Re-sequencing adds libraries to finished requests; send them back so the forward rules below re-apply.
    with run_operation(db.session, ops.REQUEST_REOPEN):
        for seq_request in db.session.get_all(__find_reopened_seq_requests(Q.seq_request.select(
            status_in=[C.SeqRequestStatus.DATA_PROCESSING, C.SeqRequestStatus.FINISHED, C.SeqRequestStatus.ARCHIVED],
        )), limit=None):
            seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
            logs.append(f"Re-opening seq_request {seq_request.id}, status to {seq_request.status}")
            db.session.save(seq_request)

    with run_operation(db.session, ops.REQUEST_SAMPLES_RECEIVED):
        for seq_request in db.session.get_all(__find_seq_requests_with_stored_samples(Q.seq_request.select(
            status=C.SeqRequestStatus.ACCEPTED,
        )), limit=None):
            seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
            logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
            db.session.save(seq_request)

    with run_operation(db.session, ops.REQUEST_PREPARED):
        for seq_request in db.session.get_all(__find_seq_requests_with_pooled_libraries(Q.seq_request.select(
            status=C.SeqRequestStatus.SAMPLES_RECEIVED,
        )), limit=None):
            seq_request.status = C.SeqRequestStatus.PREPARED
            logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
            db.session.save(seq_request)

    with run_operation(db.session, ops.REQUEST_DATA_PROCESSING):
        for seq_request in db.session.get_all(__find_sequenced_seq_requests(Q.seq_request.select(
            status_in=[C.SeqRequestStatus.ACCEPTED, C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED],
        )), limit=None):
            seq_request.status = C.SeqRequestStatus.DATA_PROCESSING
            logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
            db.session.save(seq_request)

    with run_operation(db.session, ops.PROJECT_REOPEN):
        for project in db.session.get_all(__find_reopened_projects(Q.project.select(
            status_in=[C.ProjectStatus.SEQUENCED, C.ProjectStatus.DELIVERED, C.ProjectStatus.ARCHIVED],
        )), limit=None):
            project.status = C.ProjectStatus.PROCESSING
            db.session.save(project)
            logs.append(f"Re-opening project {project.id}, status to {project.status}")

    with run_operation(db.session, ops.PROJECT_SEQUENCED):
        for project in db.session.get_all(__find_sequenced_projects(Q.project.select(
            status=C.ProjectStatus.PROCESSING,
        )), limit=None):
            project.status = C.ProjectStatus.SEQUENCED
            db.session.save(project)
            logs.append(f"Updating project {project.id} status to {project.status}")

    with run_operation(db.session, ops.REQUEST_FINISHED):
        for seq_request in db.session.get_all(__find_finished_seq_requests(Q.seq_request.select(
            status=C.SeqRequestStatus.DATA_PROCESSING,
        )), limit=None):
            seq_request.status = C.SeqRequestStatus.FINISHED
            db.session.save(seq_request)
            logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")

    logger.info("\n".join(logs))
