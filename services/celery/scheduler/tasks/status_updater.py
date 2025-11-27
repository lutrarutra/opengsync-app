import sqlalchemy as sa

from opengsync_db.core import DBHandler
from opengsync_db import categories, models

from . import logger


def __find_stored_samples(q):
    return q.where(
        ~sa.exists().where(
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id < categories.LibraryStatus.STORED.id)
        )
    )

def __find_seq_requests_with_stored_samples(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.links.SampleLibraryLink.library_id == models.Library.id) &
            (models.Sample.id == models.links.SampleLibraryLink.sample_id)
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.links.SampleLibraryLink.library_id == models.Library.id) &
            (models.Sample.id == models.links.SampleLibraryLink.sample_id) &
            (models.Sample.status_id < categories.SampleStatus.STORED.id)
        )
    )


def __find_finished_experiments(q):
    return q.join(
        models.SeqRun,
        models.SeqRun.experiment_name == models.Experiment.name,
    ).where(
        models.SeqRun.status_id.in_([
            categories.RunStatus.FINISHED.id, categories.RunStatus.ARCHIVED.id,
        ])
    )


def __find_finished_libraries(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Library.experiment_id,
    ).where(
        models.Experiment.status_id.in_([
            categories.ExperimentStatus.SEQUENCED.id,
            categories.ExperimentStatus.DEMULTIPLEXED.id,
            categories.ExperimentStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_pools(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Pool.experiment_id,
    ).where(
        models.Experiment.status_id.in_([
            categories.ExperimentStatus.SEQUENCED.id,
            categories.ExperimentStatus.DEMULTIPLEXED.id,
            categories.ExperimentStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_seq_requests(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id)
        )
    ).where(
        ~sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.Library.status_id < categories.LibraryStatus.SEQUENCED.id)
        )
    )


def __find_sequenced_projects(q):
    return q.where(
        sa.exists().where(
            (models.Sample.project_id == models.Project.id) &
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id >= categories.LibraryStatus.SEQUENCED.id)
        )
    )


def __find_finished_seq_requests(q):
    return q.where(
        sa.exists().where(
            (models.Library.seq_request_id == models.SeqRequest.id) &
            (models.links.SampleLibraryLink.library_id == models.Library.id) &
            (models.Sample.id == models.links.SampleLibraryLink.sample_id) &
            (models.Project.id == models.Sample.project_id) &
            (models.Project.status_id.in_([
                categories.ProjectStatus.DELIVERED.id, categories.ProjectStatus.ARCHIVED.id
            ]))
        )
    )


def update_statuses(db: DBHandler):
    logs = ["Checking statuses.."]

    for run in db.seq_runs.find(
        status=categories.RunStatus.RUNNING, limit=None
    )[0]:
        if run.experiment is not None:
            run.experiment.status = categories.ExperimentStatus.SEQUENCING
            logs.append(f"Updating experiment {run.experiment.id} status to {run.experiment.status}")
            db.seq_runs.update(run)

    db.flush()

    for experiment in db.experiments.find(
        limit=None, custom_query=__find_finished_experiments,
        status_in=[
            categories.ExperimentStatus.DRAFT,
            categories.ExperimentStatus.LOADED,
            categories.ExperimentStatus.SEQUENCING,
        ],
    )[0]:
        if experiment.seq_run is None:
            experiment.status = categories.ExperimentStatus.SEQUENCED
        else:
            if experiment.seq_run.status == categories.RunStatus.FINISHED:
                experiment.status = categories.ExperimentStatus.SEQUENCED
            elif experiment.seq_run.status == categories.RunStatus.ARCHIVED:
                experiment.status = categories.ExperimentStatus.ARCHIVED
            else:
                continue
            logs.append(f"Updating experiment {experiment.id} status to {experiment.status}")
            db.experiments.update(experiment)

    db.flush()

    for library in db.libraries.find(
        status_in=[
            categories.LibraryStatus.POOLED, categories.LibraryStatus.STORED, categories.LibraryStatus.PREPARING,
            categories.LibraryStatus.ACCEPTED, categories.LibraryStatus.SUBMITTED, categories.LibraryStatus.DRAFT,
        ], custom_query=__find_finished_libraries, limit=None
    )[0]:
        if library.experiment is not None:
            library.status = categories.LibraryStatus.SEQUENCED
            logs.append(f"Updating library {library.id} status to {library.status}")
            db.libraries.update(library)
    
    db.flush()

    for sample in db.samples.find(
        status=categories.SampleStatus.WAITING_DELIVERY, limit=None,
        custom_query=__find_stored_samples,
    )[0]:
        sample.status = categories.SampleStatus.STORED
        logs.append(f"Updating sample {sample.id} status to {sample.status}")
        db.samples.update(sample)

    db.flush()

    for pool in db.pools.find(
        status_in=[categories.PoolStatus.ACCEPTED, categories.PoolStatus.STORED],
        custom_query=__find_sequenced_pools, limit=None
    )[0]:
        pool.status = categories.PoolStatus.SEQUENCED
        logs.append(f"Updating pool {pool.id} status to {pool.status}")
        db.pools.update(pool)

    db.flush()

    for seq_request in db.seq_requests.find(
        status=categories.SeqRequestStatus.ACCEPTED,
        custom_query=__find_seq_requests_with_stored_samples, limit=None
    )[0]:
        seq_request.status = categories.SeqRequestStatus.SAMPLES_RECEIVED
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        db.seq_requests.update(seq_request)

    db.flush()

    for seq_request in db.seq_requests.find(
        status_in=[categories.SeqRequestStatus.ACCEPTED, categories.SeqRequestStatus.SAMPLES_RECEIVED, categories.SeqRequestStatus.PREPARED],
        custom_query=__find_sequenced_seq_requests, limit=None
    )[0]:
        seq_request.status = categories.SeqRequestStatus.DATA_PROCESSING
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        db.seq_requests.update(seq_request)

    db.flush()

    for project in db.projects.find(
        status=categories.ProjectStatus.PROCESSING, custom_query=__find_sequenced_projects, limit=None
    )[0]:
        project.status = categories.ProjectStatus.SEQUENCED
        db.projects.update(project)
        logs.append(f"Updating project {project.id} status to {project.status}")

    db.flush()

    for seq_request in db.seq_requests.find(
        status=categories.SeqRequestStatus.DATA_PROCESSING, custom_query=__find_finished_seq_requests, limit=None
    )[0]:
        seq_request.status = categories.SeqRequestStatus.FINISHED
        db.seq_requests.update(seq_request)
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")

    logger.info("\n".join(logs))