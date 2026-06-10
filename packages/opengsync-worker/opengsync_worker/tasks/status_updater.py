import sqlalchemy as sa

from opengsync_db import categories as C, models, SyncDBHandler, queries as Q

from . import logger


def __find_stored_samples(q):
    return q.where(
        ~sa.exists().where(
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id < C.LibraryStatus.STORED.id)
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
                (models.Sample.status_id < C.SampleStatus.STORED.id)
            ),
            ~sa.exists().where(
                (models.Library.seq_request_id == models.SeqRequest.id) &
                (models.links.SampleLibraryLink.library_id == models.Library.id) &
                (models.Library.pool_id == models.Pool.id) &
                (models.Pool.status_id < C.PoolStatus.STORED.id)
            )
        )
    )

def __find_seq_requests_with_pooled_libraries(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id == C.LibraryStatus.POOLED.id)
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id < C.LibraryStatus.POOLED.id)
        )
    )


def __find_finished_experiments(q):
    return q.join(
        models.SeqRun,
        models.SeqRun.experiment_name == models.Experiment.name,
    ).where(
        models.SeqRun.status_id.in_([
            C.RunStatus.FINISHED.id, C.RunStatus.ARCHIVED.id,
        ])
    )


def __find_finished_libraries(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Library.experiment_id,
    ).where(
        models.Experiment.status_id.in_([
            C.ExperimentStatus.SEQUENCED.id,
            C.ExperimentStatus.DEMULTIPLEXED.id,
            C.ExperimentStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_pools(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Pool.experiment_id,
    ).where(
        models.Experiment.status_id.in_([
            C.ExperimentStatus.SEQUENCED.id,
            C.ExperimentStatus.DEMULTIPLEXED.id,
            C.ExperimentStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_seq_requests(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id.in_([
                C.LibraryStatus.SEQUENCED.id,
                C.LibraryStatus.SHARED.id,
                C.LibraryStatus.ARCHIVED.id,
            ]))
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id < C.LibraryStatus.SEQUENCED.id)
        )
    )


def __find_sequenced_projects(q):
    return q.where(
        sa.exists().where(
            (models.Sample.project_id == models.Project.id) &
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id >= C.LibraryStatus.SEQUENCED.id)
        )
    ).where(
        ~sa.exists().where(
            (models.Sample.project_id == models.Project.id) &
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id < C.LibraryStatus.SEQUENCED.id)
        )
    )


def __find_finished_seq_requests(q):
    return q.where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id < C.LibraryStatus.SHARED.id)
        )
    )


def update_statuses(db: SyncDBHandler):
    logs = ["Checking statuses.."]

    for run in db.session.get_all(Q.seq_run.select(status=C.RunStatus.RUNNING), limit=None):
        if run.experiment is not None:
            run.experiment.status = C.ExperimentStatus.SEQUENCING
            logs.append(f"Updating experiment {run.experiment.id} status to {run.experiment.status}")
            db.session.save(run)

    db.session.flush()

    for experiment in db.session.get_all(Q.experiment.select(
        status_in=[
            C.ExperimentStatus.DRAFT,
            C.ExperimentStatus.LOADED,
            C.ExperimentStatus.SEQUENCING,
        ],
    ), limit=None):
        if experiment.seq_run is None:
            experiment.status = C.ExperimentStatus.SEQUENCED
        else:
            if experiment.seq_run.status == C.RunStatus.FINISHED:
                experiment.status = C.ExperimentStatus.SEQUENCED
            elif experiment.seq_run.status == C.RunStatus.ARCHIVED:
                experiment.status = C.ExperimentStatus.ARCHIVED
            else:
                continue
            logs.append(f"Updating experiment {experiment.id} status to {experiment.status}")
            db.session.save(experiment)

    db.session.flush()

    for library in db.session.get_all(__find_finished_libraries(Q.library.select(
        status_in=[
            C.LibraryStatus.POOLED, C.LibraryStatus.STORED, C.LibraryStatus.PREPARING,
            C.LibraryStatus.ACCEPTED, C.LibraryStatus.SUBMITTED, C.LibraryStatus.DRAFT,
        ]
    )), limit=None):
        if library.experiment is not None:
            library.status = C.LibraryStatus.SEQUENCED
            logs.append(f"Updating library {library.id} status to {library.status}")
            db.session.save(library)
    
    db.session.flush()

    for sample in db.session.get_all(__find_stored_samples(Q.sample.select(
        status=C.SampleStatus.WAITING_DELIVERY,
    )), limit=None):
        sample.status = C.SampleStatus.STORED
        logs.append(f"Updating sample {sample.id} status to {sample.status}")
        db.session.save(sample)

    db.session.flush()

    for pool in db.session.get_all(__find_sequenced_pools(Q.pool.select(
        status_in=[C.PoolStatus.ACCEPTED, C.PoolStatus.STORED],
    )), limit=None):
        pool.status = C.PoolStatus.SEQUENCED
        logs.append(f"Updating pool {pool.id} status to {pool.status}")
        db.session.save(pool)

    db.session.flush()

    for seq_request in db.session.get_all(__find_seq_requests_with_stored_samples(Q.seq_request.select(
        status=C.SeqRequestStatus.ACCEPTED,
    )), limit=None):
        seq_request.status = C.SeqRequestStatus.SAMPLES_RECEIVED
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        db.session.save(seq_request)

    db.session.flush()

    for seq_request in db.session.get_all(__find_seq_requests_with_pooled_libraries(Q.seq_request.select(
        status=C.SeqRequestStatus.SAMPLES_RECEIVED,
    )), limit=None):
        seq_request.status = C.SeqRequestStatus.PREPARED
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        db.session.save(seq_request)

    db.session.flush()

    for seq_request in db.session.get_all(__find_sequenced_seq_requests(Q.seq_request.select(
        status_in=[C.SeqRequestStatus.ACCEPTED, C.SeqRequestStatus.SAMPLES_RECEIVED, C.SeqRequestStatus.PREPARED],
    )), limit=None):
        seq_request.status = C.SeqRequestStatus.DATA_PROCESSING
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        db.session.save(seq_request)

    db.session.flush()

    for project in db.session.get_all(__find_sequenced_projects(Q.project.select(
        status=C.ProjectStatus.PROCESSING,
    )), limit=None):
        project.status = C.ProjectStatus.SEQUENCED
        db.session.save(project)
        logs.append(f"Updating project {project.id} status to {project.status}")

    db.session.flush()

    for seq_request in db.session.get_all(__find_finished_seq_requests(Q.seq_request.select(
        status=C.SeqRequestStatus.DATA_PROCESSING,
    )), limit=None):
        seq_request.status = C.SeqRequestStatus.FINISHED
        db.session.save(seq_request)
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")

    logger.info("\n".join(logs))