from . import logger

import sqlalchemy as sa

from opengsync_db.core import DBHandler
from opengsync_db import categories, models


def __find_stored_samples(q):
    return q.where(
        ~sa.exists().where(
            (models.links.SampleLibraryLink.sample_id == models.Sample.id) &
            (models.Library.id == models.links.SampleLibraryLink.library_id) &
            (models.Library.status_id < categories.LibraryStatus.PREPARING.id)
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
    ).join(
        models.SeqRun,
        models.SeqRun.experiment_name == models.Experiment.name,
    ).where(
        models.SeqRun.status_id.in_([
            categories.RunStatus.FINISHED.id, categories.RunStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_pools(q):
    return q.join(
        models.Experiment,
        models.Experiment.id == models.Pool.experiment_id,
    ).join(
        models.SeqRun,
        models.SeqRun.experiment_name == models.Experiment.name,
    ).where(
        models.SeqRun.status_id.in_([
            categories.RunStatus.FINISHED.id, categories.RunStatus.ARCHIVED.id,
        ])
    )


def __find_sequenced_seq_requests(q):
    return q.join(
        models.Library,
        models.Library.seq_request_id == models.SeqRequest.id,
    ).where(
        models.Library.status_id >= categories.LibraryStatus.SEQUENCED.id
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

    for run in db.get_seq_runs(
        status=categories.RunStatus.RUNNING, limit=None
    )[0]:
        if run.experiment is not None:
            run.experiment.status = categories.ExperimentStatus.SEQUENCING
            logs.append(f"Updating experiment {run.experiment.id} status to {run.experiment.status}")
            run = db.update_seq_run(run)

    db.flush()

    for experiment in db.get_experiments(
        limit=None, custom_query=__find_finished_experiments,
        status_in=[
            categories.ExperimentStatus.DRAFT,
            categories.ExperimentStatus.LOADED,
            categories.ExperimentStatus.SEQUENCING,
        ],
    )[0]:
        if experiment.seq_run is None:
            experiment.status = categories.ExperimentStatus.FINISHED
        else:
            if experiment.seq_run.status == categories.RunStatus.FINISHED:
                experiment.status = categories.ExperimentStatus.FINISHED
            elif experiment.seq_run.status == categories.RunStatus.ARCHIVED:
                experiment.status = categories.ExperimentStatus.ARCHIVED
            else:
                continue
            logs.append(f"Updating experiment {experiment.id} status to {experiment.status}")
            experiment = db.update_experiment(experiment)

    db.flush()

    for library in db.get_libraries(
        status_in=[
            categories.LibraryStatus.POOLED, categories.LibraryStatus.STORED, categories.LibraryStatus.PREPARING,
            categories.LibraryStatus.ACCEPTED, categories.LibraryStatus.SUBMITTED, categories.LibraryStatus.DRAFT,
        ], custom_query=__find_finished_libraries, limit=None
    )[0]:
        if library.experiment is not None:
            library.status = categories.LibraryStatus.SEQUENCED
            logs.append(f"Updating library {library.id} status to {library.status}")
            library = db.update_library(library)
    
    db.flush()

    for sample in db.get_samples(
        status=categories.SampleStatus.WAITING_DELIVERY, limit=None,
        custom_query=__find_stored_samples,
    )[0]:
        sample.status = categories.SampleStatus.STORED
        logs.append(f"Updating sample {sample.id} status to {sample.status}")
        sample = db.update_sample(sample)

    db.flush()

    for pool in db.get_pools(
        status_in=[categories.PoolStatus.ACCEPTED, categories.PoolStatus.STORED],
        custom_query=__find_sequenced_pools, limit=None
    )[0]:
        pool.status = categories.PoolStatus.SEQUENCED
        logs.append(f"Updating pool {pool.id} status to {pool.status}")
        pool = db.update_pool(pool)

    db.flush()

    for seq_request in db.get_seq_requests(
        status=categories.SeqRequestStatus.PREPARED, custom_query=__find_sequenced_seq_requests, limit=None
    )[0]:
        seq_request.status = categories.SeqRequestStatus.DATA_PROCESSING
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")
        seq_request = db.update_seq_request(seq_request)

    db.flush()

    for project in db.get_projects(
        status=categories.ProjectStatus.PROCESSING, custom_query=__find_sequenced_projects, limit=None
    )[0]:
        project.status = categories.ProjectStatus.SEQUENCED
        project = db.update_project(project)
        logs.append(f"Updating project {project.id} status to {project.status}")

    db.flush()

    for seq_request in db.get_seq_requests(
        status=categories.SeqRequestStatus.DATA_PROCESSING, custom_query=__find_finished_seq_requests, limit=None
    )[0]:
        seq_request.status = categories.SeqRequestStatus.FINISHED
        seq_request = db.update_seq_request(seq_request)
        logs.append(f"Updating seq_request {seq_request.id} status to {seq_request.status}")

    logger.info("\n".join(logs))