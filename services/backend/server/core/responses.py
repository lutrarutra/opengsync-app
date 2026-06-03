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
    **context
) -> Response:
    if redirect:
        return RedirectResponse(url=redirect, status_code=303)
    
    from loguru import logger
    logger.debug(f"Rendering template '{template}' with context: {context}")
    content = ""
    if template is not None:
        content = await render_template(template, **context | await get_request_context())
    
    return HTMLResponse(
        content=content,
        status_code=status,
        headers={"Content-Type": "text/html; charset=utf-8"}
    )

async def htmx_response(
    template: str | None = None, 
    status: int = 200, 
    redirect: str | None = None, 
    re_target: str | None = None, 
    re_swap: str | None = None, # Added for completeness
    **context
) -> Response:
    headers = {"HX-Trigger": "contentUpdated"}
    
    if redirect:
        headers["HX-Redirect"] = redirect
        return HTMLResponse(status_code=204, headers=headers)

    if re_target:
        headers["HX-Retarget"] = re_target
    
    if re_swap:
        headers["HX-Reswap"] = re_swap
    
    content = ""
    if template is not None:
        content = await render_template(template, **context | await get_request_context())
    elif status == 200:
        status = 204

    return HTMLResponse(
        content=content,
        status_code=status,
        headers=headers
    )