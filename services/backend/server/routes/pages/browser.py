from pathlib import Path

from fastapi import APIRouter, Request

from ...core import responses

router = APIRouter(prefix="/browser", tags=["browser"])


@router.get("/")
@router.get("/{subpath:path}")
def browser_page(request: Request, subpath: str = ""):
    subpath_path = Path(subpath) if subpath and subpath not in (".", "/") else Path()

    sort_by = request.query_params.get("sort_by", "name")
    sort_order = request.query_params.get("sort_order", "asc" if sort_by == "name" else "desc")

    return responses.html_response(
        "files_page.html",
        current_path=subpath_path,
        parent_dir=subpath_path.parent if subpath_path != Path() else None,
        sort_by=sort_by,
        sort_order=sort_order,
        title="OpeNGSync - Files",
    )