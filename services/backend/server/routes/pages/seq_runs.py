from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/seq_runs", tags=["seq_runs"])


@router.get("/")
def seq_runs_page():
    return responses.html_response("seq_runs_page.html")


@router.get("/{seq_run_id}")
def seq_run_page(seq_run_id: int):
    # NOTE: Seq run lookup, experiment lookup, and breadcrumb resolution
    # are handled client-side via API calls.
    return responses.html_response(
        "seq_run_page.html",
        seq_run_id=seq_run_id,
        title=f"Run {seq_run_id}",
    )