from . import logger

from opengsync_db.core import DBHandler
from opengsync_db import categories, models


def update_statuses(db: DBHandler):
    logger.info("Updating statuses..")

    def find_finished_libraries(q):
        return q.join(
            models.Experiment,
            models.Experiment.id == models.Library.experiment_id,
        ).where(
            models.Experiment.status_id.in_(
                [categories.ExperimentStatus.FINISHED.id, categories.ExperimentStatus.ARCHIVED.id]
            )
        )
    
    for library in db.get_libraries(
        status_in=[
            categories.LibraryStatus.POOLED, categories.LibraryStatus.STORED, categories.LibraryStatus.PREPARING,
            categories.LibraryStatus.ACCEPTED, categories.LibraryStatus.SUBMITTED, categories.LibraryStatus.DRAFT,
        ], custom_query=find_finished_libraries
    )[0]:
        if library.experiment is not None:
            if library.experiment.status == categories.ExperimentStatus.FINISHED:
                library.status = categories.LibraryStatus.SEQUENCED
            elif library.experiment.status == categories.ExperimentStatus.ARCHIVED:
                library.status = categories.LibraryStatus.ARCHIVED
            else:
                continue
            library = db.update_library(library)

    for run in db.get_seq_runs(
        limit=20, sort_by="id", descending=True,
        experiment_status_in=[categories.ExperimentStatus.DRAFT, categories.ExperimentStatus.LOADED, categories.ExperimentStatus.SEQUENCING],
        status_in=[categories.RunStatus.FINISHED, categories.RunStatus.RUNNING]
    )[0]:
        if run.experiment is not None:
            if run.status == categories.RunStatus.FINISHED:
                run.experiment.status = categories.ExperimentStatus.FINISHED
                for pool in run.experiment.pools:
                    pool.status = categories.PoolStatus.SEQUENCED
                    for library in pool.libraries:
                        db.refresh(library)
                        library.status = categories.LibraryStatus.SEQUENCED
            elif run.status == categories.RunStatus.RUNNING:
                run.experiment.status = categories.ExperimentStatus.SEQUENCING

            run = db.update_seq_run(run)

    for seq_request in db.get_seq_requests(limit=20, status_in=[categories.SeqRequestStatus.PREPARED, categories.SeqRequestStatus.DATA_PROCESSING])[0]:
        sequenced = True
        for library in seq_request.libraries:
            db.refresh(library)
            sequenced = sequenced and library.status >= categories.LibraryStatus.SEQUENCED

        if sequenced:
            seq_request.status = categories.SeqRequestStatus.DATA_PROCESSING

        seq_request = db.update_seq_request(seq_request)

    for project in db.get_projects(
        limit=20, sort_by="id", descending=True,
        status=categories.ProjectStatus.PROCESSING
    )[0]:
        sequenced = True
        for library in project.libraries:
            db.refresh(library)
            sequenced = sequenced and library.status >= categories.LibraryStatus.SEQUENCED
            if not sequenced:
                break
                
        if sequenced:
            project.status = categories.ProjectStatus.SEQUENCED
        
        project = db.update_project(project)
        


    