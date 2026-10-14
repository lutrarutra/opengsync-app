from fastapi import APIRouter, Depends, Query

from opengsync_db import SyncSession, queries as Q

from ...core import dependencies, responses

router = APIRouter(prefix="/seq_runs", tags=["seq_runs"])


@router.get("/")
def seq_runs_page():
    return responses.html_response(template="seq_runs_page.html")


@router.get("/{seq_run_id}")
def seq_run_page(
    seq_run_id: int,
    from_page: str | None = Query(None, alias="from"),
    session: SyncSession = Depends(dependencies.db_session),
):
    seq_run = session.get_one(Q.seq_run.select(id=seq_run_id))
    experiment = session.first(Q.experiment.select(name=seq_run.experiment_name))

    path_list = [
        ("Runs", responses.url_for("seq_runs_page")),
        (f"Run {seq_run.id}", ""),
    ]
    page, _, experiment_id = (from_page or "").partition("@")
    if page == "experiment" and experiment_id.isdigit():
        path_list = [
            ("Experiments", responses.url_for("experiments_page")),
            (f"Experiment {experiment_id}", responses.url_for("experiment_page", experiment_id=experiment_id)),
            (f"Run {seq_run.id}", ""),
        ]

    return responses.html_response(
        template="seq_run_page.html", seq_run=seq_run, experiment=experiment, path_list=path_list,
        title=f"Run: {seq_run.experiment_name}",
    )
