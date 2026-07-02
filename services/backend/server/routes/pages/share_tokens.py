from fastapi import APIRouter, Depends

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/share_tokens", tags=["share_tokens"])


@router.get("/")
def share_tokens():
    return responses.html_response("share_tokens_page.html", title="Share Tokens")


@router.get("/{share_token_id}")
def share_token(share_token_id: str):
    # NOTE: Share token lookup and breadcrumb resolution handled client-side.
    return responses.html_response(
        "share_token_page.html",
        share_token_id=share_token_id,
        title=f"Token {share_token_id}",
    )