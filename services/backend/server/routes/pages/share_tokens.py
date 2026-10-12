from fastapi import APIRouter

from ...core import responses

router = APIRouter(prefix="/share_tokens", tags=["share_tokens"])


@router.get("/")
def share_tokens():
    return responses.html_response(template="share_tokens_page.html", title="Share Tokens")