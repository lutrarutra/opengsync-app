from pathlib import Path

from fastapi import APIRouter, Depends, Request

from opengsync_db import models

from ...core import dependencies, responses, exceptions

router = APIRouter(prefix="/browser", tags=["browser"])


@router.get("/{subpath:path}")
async def browser_page(request: Request, subpath: str = "/"):
    subpath_path = Path(subpath) if subpath else Path()

    sort_by = request.query_params.get("sort_by", "name")
    sort_order = request.query_params.get("sort_order", "asc" if sort_by == "name" else "desc")

    return await responses.html_response(
        "files_page.html",
        current_path=subpath_path,
        parent_dir=subpath_path.parent if subpath_path != Path() else None,
        sort_by=sort_by,
        sort_order=sort_order,
        title="OpeNGSync - Files",
    )