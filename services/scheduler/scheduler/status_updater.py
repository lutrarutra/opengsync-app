from . import logger

from limbless_db.core import DBHandler
from limbless_db import categories


def update_statuses(db: DBHandler):
    logger.info("Updating statuses..")
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
                        library.status = categories.LibraryStatus.SEQUENCED
            elif run.status == categories.RunStatus.RUNNING:
                run.experiment.status = categories.ExperimentStatus.SEQUENCING

            run = db.update_seq_run(run)

    for seq_request in db.get_seq_requests(limit=20, status_in=[categories.SeqRequestStatus.PREPARED, categories.SeqRequestStatus.DATA_PROCESSING])[0]:
        sequenced = True
        for library in seq_request.libraries:
            sequenced = sequenced and library.status == categories.LibraryStatus.SEQUENCED

        if sequenced:
            seq_request.status = categories.SeqRequestStatus.DATA_PROCESSING

        seq_request = db.update_seq_request(seq_request)