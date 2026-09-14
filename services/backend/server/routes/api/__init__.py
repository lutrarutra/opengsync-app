from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from . import barcodes, projects, shares, stats, tokens, webdav

router = APIRouter(prefix="/api", tags=["api", "json"])
router.include_router(barcodes.router)
router.include_router(projects.router)
router.include_router(stats.router)
router.include_router(shares.router)
router.include_router(tokens.router)
router.include_router(webdav.router)


@router.get("/status")
def status():
    return PlainTextResponse("OK")


__all__ = [
    "router",
    "barcodes",
    "projects",
    "stats",
    "shares",
    "tokens",
    "webdav",
]
