from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("/")
def experiments():
    return responses.html_response("experiments_page.html", title="Experiments")


@router.get("/{experiment_id}")
def experiment(experiment_id: int):
    # NOTE: Experiment lookup, lane data, checklist, and breadcrumb
    # resolution are handled client-side via API calls.
    return responses.html_response(
        "experiment_page.html",
        experiment_id=experiment_id,
        title=f"Experiment {experiment_id}",
    )