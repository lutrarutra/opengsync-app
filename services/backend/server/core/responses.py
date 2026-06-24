import os
import json
import io
from typing import Literal
from urllib.parse import quote

from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from starlette.datastructures import URL
from pydantic import BaseModel

from .templates import render_template
from . import utils
from .context import ctx

class FlashMessage(BaseModel):
    message: str
    category: Literal["info", "success", "warning", "error"] = "info"

def flash(message: str, category: Literal["info", "success", "warning", "error"] = "info") -> FlashMessage:
    return FlashMessage(message=message, category=category)

def raw_json_response(data: str | bytes, encapsulate: str | None = None) -> Response:
    if encapsulate:
        data = utils.json_encapsulate(encapsulate, data)

    return JSONResponse(content=data, media_type="application/json")
    

async def html_response(
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
            content = await render_template(template, **context)
        
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

async def htmx_response(
    template: str | None = None,
    content: str | None = None,
    status: int = 200, 
    redirect: URL | None = None, 
    re_target: str | None = None, 
    re_swap: str | None = None,
    response: Response | None = None,
    flash: FlashMessage | str | None = None,
    **context
) -> Response:
    headers = {"HX-Trigger": "contentUpdated"}

    if template and content:
        raise ValueError("Cannot provide both template and content for HTMX response.")

    if flash:
        flash_data = flash.model_dump() if isinstance(flash, FlashMessage) else {"message": flash, "category": "info"}
        if redirect:
            headers["HX-Redirect"] = redirect.__str__()
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
            headers["HX-Trigger"] = json.dumps({"flash": flash_data})

    if re_target:
        headers["HX-Target"] = re_target
    if re_swap:
        headers["HX-Swap"] = re_swap
    
    if redirect:
        headers["HX-Redirect"] = redirect.__str__()
        resp = HTMLResponse(status_code=204, headers=headers)
    elif template is not None:
        content = await render_template(template, **context)
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

async def file_response(path: str, filename: str | None = None, content_type: str | None = None) -> Response:
    if not os.path.isfile(path):
        return HTMLResponse(content="File not found", status_code=404)

    if filename is None:
        filename = os.path.basename(path)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    response = Response(
        content=open(path, "rb").read(),  # TODO: use nginx to serve files directly instead of reading them into memory
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
    return response


async def bytes_response(data: bytes | io.BytesIO, filename: str, content_type: str | None = None) -> Response:
    if isinstance(data, io.BytesIO):
        data.seek(0)
        raw = data.read()
    else:
        raw = data

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    response = Response(
        content=raw,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
    return response


def url_for(name: str, **path_params) -> URL:
    request = ctx.request
    return request.url_for(name, **path_params)