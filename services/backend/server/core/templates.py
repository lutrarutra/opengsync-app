from uuid import uuid4
from pathlib import Path
from datetime import datetime

import pandas as pd
import jinja2
from fastapi.templating import Jinja2Templates

from opengsync_db import categories as C, models
from opengsync_db import units

from . import context
from .config import settings

j2 = Jinja2Templates(directory="/templates", enable_async=True, undefined=jinja2.StrictUndefined if settings.ENVIRONMENT != "prod" else jinja2.Undefined)

def format_timestamp(value: float, format: str = "%Y-%m-%d %H:%M"):
    """Convert timestamp to readable string"""
    return datetime.fromtimestamp(value).strftime(format)

def format_datetime(value: datetime, format: str = "%Y-%m-%d %H:%M"):
    """Convert datetime to readable string"""
    return value.astimezone(settings.TIMEZONE).strftime(format)

def weekday_name(value: int):
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][value]


def filesize(value: int | float):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if value < 1024.0:
            if unit == 'B':
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"

def format_markdown(value: str) -> str:
    from markupsafe import Markup
    import markdown  #type: ignore
    return Markup(markdown.markdown(value))

j2.env.filters["format_timestamp"] = format_timestamp
j2.env.filters["format_datetime"] = format_datetime
j2.env.filters["format_markdown"] = format_markdown
j2.env.filters["weekday_name"] = weekday_name
j2.env.filters["filesize"] = filesize


def format_iso(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value).astimezone(settings.TIMEZONE)
    except ValueError:
        return "<error formatting time>"
    return dt.strftime(fmt)

def from_timestamp(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromtimestamp(float(value)).astimezone(settings.TIMEZONE)
    except ValueError:
        return "<error formatting time>"
    return dt.strftime(fmt)

def bytes_to_human(size: int | None) -> str:
    if size is None or size < 0:
        return ""
    
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:  #type: ignore
            if unit == "B":
                return f"{size} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024  #type: ignore
    return f"{size:.2f} PB"

def highlight_py(code: str) -> str:
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import HtmlFormatter
    formatter = HtmlFormatter(style="friendly", noclasses=True)
    return highlight(code, PythonLexer(), formatter)

def highlight_sh(code: str) -> str:
    from pygments import highlight
    from pygments.lexers import BashLexer
    from pygments.formatters import HtmlFormatter
    formatter = HtmlFormatter(
        style="friendly", noclasses=True,
        prestyles="white-space: pre-wrap; word-break: break-all; word-wrap: break-word; background-color: #e7e7e7; padding: 5px 0; border-radius: 4px;"
    )
    return highlight(code, BashLexer(), formatter)

def highlight_r(code: str) -> str:
    from pygments import highlight
    from pygments.lexers import RLexer
    from pygments.formatters import HtmlFormatter
    formatter = HtmlFormatter(style="friendly", noclasses=True)
    return highlight(code, RLexer(), formatter)

def replace_substrings(s: str, replacements: dict[str, str]) -> str:
    for old, new in sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True):
        s = s.replace(old, new)
    return s

def root_name(path: str | Path) -> str:
    return Path(path).parts[0] if Path(path).parts else ""

j2.env.filters["format_iso"] = format_iso
j2.env.filters["from_timestamp"] = from_timestamp
j2.env.filters["bytes_to_human"] = bytes_to_human
j2.env.filters["highlight_py"] = highlight_py
j2.env.filters["highlight_sh"] = highlight_sh
j2.env.filters["highlight_r"] = highlight_r
j2.env.filters["replace_substrings"] = replace_substrings
j2.env.filters["root_name"] = root_name

# ─── Globals ported from add_context ───
j2.env.globals["app_version"] = "dev"
j2.env.globals["api_version"] = "dev"
j2.env.globals["db_version"] = "dev"
j2.env.globals["debug"] = settings.ENVIRONMENT == "dev"

# Categories — whole module injected so templates use C.EnumName
j2.env.globals["C"] = C

# Utilities
j2.env.globals["isna"] = pd.isna
j2.env.globals["notna"] = pd.notna
j2.env.globals["units"] = units
j2.env.globals["uuid4"] = uuid4
j2.env.globals["SpreadSheetErrors"] = [
    # ssc.InvalidCellValue(""),
    # ssc.MissingCellValue(""),
    # ssc.DuplicateCellValue(""),
]

def prioritize_current_user(users: list[models.User], current_user: models.User) -> list[models.User]:
    return sorted(
        users,
        key=lambda user: 0 if user == current_user else 1
    )

j2.env.filters["prioritize_current_user"] = prioritize_current_user


@jinja2.pass_context
def url_for(ctx: jinja2.runtime.Context, name: str, **path_params) -> str:
    """Custom url_for that handles static files without needing request.url_for.
    
    Unlike Flask, Starlette's url_for only substitutes path parameters and
    ignores extra kwargs. This wrapper appends leftover kwargs as query params.
    """
    request = ctx.get("request")
    if request is not None:
        route_param_names = _get_route_param_names(request.app.router, name)
        url_kwargs = {k: v for k, v in path_params.items() if k in route_param_names}
        query_kwargs = {k: v for k, v in path_params.items() if k not in route_param_names}

        try:
            url = request.url_for(name, **url_kwargs)
        except Exception:
            if name == "static":
                filename = path_params.get("filename", "")
                return f"/static/{filename.lstrip('/')}"
            raise

        if query_kwargs:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query_kwargs)}"

        return url.__str__()
    raise RuntimeError(f"Cannot generate URL for '{name}' without a request context")


def _get_route_param_names(router, name: str) -> set:
    """Extract path parameter names from a route by its name."""
    for route in router.routes:
        if getattr(route, 'name', None) == name:
            if hasattr(route, 'param_convertors'):
                return set(route.param_convertors.keys())
            return set()
    return set()

j2.env.globals["url_for"] = url_for

async def render_template(template_name: str, include_request_context: bool = True, **kwargs) -> str:
    template = j2.get_template(template_name)
    if include_request_context:
        kwargs |= context.get_request_context()
    return await template.render_async(**kwargs)
