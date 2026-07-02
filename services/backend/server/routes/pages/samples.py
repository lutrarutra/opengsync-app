from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses

router = APIRouter(prefix="/samples", tags=["samples"])


@router.get("/")
def samples_page():
    return responses.html_response("samples_page.html", title="Samples")


@router.get("/{sample_id}")
def sample_page(
    sample_id: int,
    current_user: models.User = Depends(dependencies.require_user),
):
    # NOTE: Sample lookup, access checks, and breadcrumb resolution
    # are handled client-side via API calls.
    return responses.html_response(
        "sample_page.html",
        sample_id=sample_id,
        title=f"Sample {sample_id}",
    )