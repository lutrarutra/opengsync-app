import json
import io
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from starlette.datastructures import URL
from pydantic import BaseModel

from . import templates, config
from .. import utils
from .context import ctx

class FlashMessage(BaseModel):
    message: str
    category: Literal["info", "success", "warning", "error"] = "info"

def flash(message: str, category: Literal["info", "success", "warning", "error"] = "info") -> FlashMessage:
    return FlashMessage(message=message, category=category)

def raw_json_response(data: str | bytes, encapsulate: str | None = None) -> Response:
    if encapsulate:
        data = utils.parsing.json_encapsulate(encapsulate, data)

    return JSONResponse(content=data, media_type="application/json")
    

def html_response(
    template: str | None = None, 
    redirect: URL | None = None, 
    status: int = 200, 
    response: Response | None = None,
    **context
) -> Response:
    if redirect:
        resp = RedirectResponse(url=redirect, status_code=303)
    else:
        content = ""
        if template is not None:
            content = templates.render_template(template, **context)
        
        resp = HTMLResponse(
            content=content,
            status_code=status,
            headers={"Content-Type": "text/html; charset=utf-8"}
        )

    if response:
        for header, value in response.raw_headers:
            if header.lower() == b"set-cookie":
                resp.raw_headers.append((header, value))
    
    return resp

def htmx_response(
    template: str | None = None,
    content: str | None = None,
    status: int = 200, 
    redirect: URL | None = None, 
    re_target: str | None = None, 
    re_swap: str | None = None,
    response: Response | None = None,
    flash: FlashMessage | str | None = None,
    refresh_table: str | None = None,
    **context
) -> Response:
    if template and content:
        raise ValueError("Cannot provide both template and content for HTMX response.")

    # Build composable HX-Trigger events
    events: dict[str, object] = {}

    if flash:
        flash_data = flash.model_dump() if isinstance(flash, FlashMessage) else {"message": flash, "category": "info"}
        if redirect:
            headers = {"HX-Redirect": redirect.__str__()}
            resp = HTMLResponse(status_code=204, headers=headers)
            resp.set_cookie(
                key="flash_message",
                value=quote(json.dumps(flash_data)),
                max_age=60,
                httponly=False,
                samesite="lax",
                path="/",
            )
            if response:
                for header, value in response.raw_headers:
                    if header.lower() == b"set-cookie":
                        resp.raw_headers.append((header, value))
            return resp
        else:
            events["flash"] = flash_data

    if refresh_table:
        events["refreshTable"] = refresh_table

    if events:
        headers = {"HX-Trigger": json.dumps(events)}
    else:
        headers = {"HX-Trigger": "contentUpdated"}

    if re_target:
        headers["HX-Target"] = re_target
    if re_swap:
        headers["HX-Swap"] = re_swap
    
    if redirect:
        headers["HX-Redirect"] = redirect.__str__()
        resp = HTMLResponse(status_code=204, headers=headers)
    elif template is not None:
        content = templates.render_template(template, **context)
        resp = HTMLResponse(content=content, status_code=status, headers=headers)
    elif content is not None:
        resp = HTMLResponse(content=content, status_code=status, headers=headers)
    else:
        resp = HTMLResponse(status_code=status if status != 200 else 204, headers=headers)

    if response:
        for header, value in response.raw_headers:
            if header.lower() == b"set-cookie":
                resp.raw_headers.append((header, value))
    
    return resp

def _x_accel_redirect(path: Path) -> str | None:
    share_root = Path(config.settings.app_config.share_root).as_posix()
    media_folder = Path(config.settings.app_config.media_folder).as_posix()
    posix = path.as_posix()
    if posix == share_root or posix.startswith(share_root.rstrip("/") + "/"):
        return quote(posix.replace(share_root, "/nginx-share/", 1), safe="/")
    if posix == media_folder or posix.startswith(media_folder.rstrip("/") + "/"):
        return quote(posix.replace(media_folder, "/nginx-media/", 1), safe="/")
    return None


def file_response(
    path: str | Path,
    filename: str | None = None,
    content_type: str | None = None,
    disposition: Literal["inline", "attachment"] | None = "attachment",
    extra_headers: dict[str, str] | None = None,
    send_body: bool = True,
) -> Response:
    path = Path(path)
    if not path.is_file():
        return HTMLResponse(content="File not found", status_code=404)

    if filename is None:
        filename = path.name

    headers = dict(extra_headers or {})
    if disposition is not None:
        headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'

    media_type = content_type or "application/octet-stream"

    if send_body and config.settings.ENVIRONMENT == "prod" and (accel := _x_accel_redirect(path)):
        headers["X-Accel-Redirect"] = accel
        return Response(content=b"", media_type=media_type, headers=headers)

    if not send_body:
        return Response(content=b"", media_type=media_type, headers=headers)

    with open(path, "rb") as f:
        return Response(
            content=f.read(),
            media_type=media_type,
            headers=headers,
        )


def bytes_response(data: bytes | io.BytesIO, filename: str, content_type: str | None = None, disposition: Literal["inline", "attachment"] = "attachment") -> Response:
    if isinstance(data, io.BytesIO):
        data.seek(0)
        raw = data.read()
    else:
        raw = data

    headers = {
        "Content-Disposition": f'{disposition}; filename="{filename}"'
    }
    response = Response(
        content=raw,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
    return response


def url_for(name: str, **path_params) -> URL:
    request = ctx.request
    normalized: dict = {}
    for key, value in path_params.items():
        if isinstance(value, Path):
            value = value.as_posix() if value.parts else ""
        if value is None or value == "" or value == ".":
            continue
        normalized[key] = value
    return request.url_for(name, **normalized)