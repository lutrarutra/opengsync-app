from typing import Any
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse

from .templates import render_template

from . import utils, runtime
from .context import ctx

async def get_request_context() -> dict[str, Any]:
    request = ctx.request
    
    if (current_user := getattr(request.state, "current_user", runtime.NOT_CHECKED)) == runtime.NOT_CHECKED:
        current_user = None
    return {
        "request": request,
        "current_user": current_user
    }

def raw_json_response(data: str | bytes, encapsulate: str | None = None) -> Response:
    if encapsulate:
        data = utils.json_encapsulate(encapsulate, data)

    return JSONResponse(content=data, media_type="application/json")
    

async def html_response(
    template: str | None = None, 
    redirect: str | None = None, 
    status: int = 200, 
    response: Response | None = None,
    **context
) -> Response:
    if redirect:
        resp = RedirectResponse(url=ctx.request.url_for(redirect), status_code=303)
    else:
        content = ""
        if template is not None:
            content = await render_template(template, **context | await get_request_context())
        
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
    status: int = 200, 
    redirect: str | None = None, 
    re_target: str | None = None, 
    re_swap: str | None = None,
    response: Response | None = None,
    **context
) -> Response:
    headers = {"HX-Trigger": "contentUpdated"}
    
    if redirect:
        headers["HX-Redirect"] = ctx.request.url_for(redirect).__str__()
        resp = HTMLResponse(status_code=204, headers=headers)
    elif template is not None:
        content = await render_template(template, **context | await get_request_context())
        resp = HTMLResponse(content=content, status_code=status, headers=headers)
    else:
        resp = HTMLResponse(status_code=status if status != 200 else 204, headers=headers)

    if response:
        for header, value in response.raw_headers:
            if header.lower() == b"set-cookie":
                resp.raw_headers.append((header, value))
    
    return resp