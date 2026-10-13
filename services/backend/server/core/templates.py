import shlex
from uuid import uuid4
from pathlib import Path
from datetime import datetime

import pandas as pd
import jinja2
from markupsafe import Markup, escape
from fastapi.routing import iter_route_contexts
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from opengsync_db import categories as C, models, units

from . import context
from .search import SEARCH_KINDS
from .config import settings
from ..utils import barcodes

j2 = Jinja2Templates(env=jinja2.Environment(
    loader=jinja2.FileSystemLoader("/templates"),
    autoescape=jinja2.select_autoescape(),
    undefined=jinja2.StrictUndefined if settings.ENVIRONMENT != "prod" else jinja2.Undefined,
))

def format_timestamp(value: float, format: str = "%Y-%m-%d %H:%M"):
    """Convert timestamp to readable string"""
    return datetime.fromtimestamp(value).strftime(format)

def format_datetime(value: datetime | None, format: str = "%Y-%m-%d %H:%M"):
    """Convert datetime to readable string. Empty when the value is missing."""
    if value is None:
        return ""
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
    from ..utils.io import render_markdown
    return Markup(render_markdown(value))

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

def shell_quote(s) -> str:
    return shlex.quote(str(s))

j2.env.filters["format_iso"] = format_iso
j2.env.filters["from_timestamp"] = from_timestamp
j2.env.filters["bytes_to_human"] = bytes_to_human
j2.env.filters["highlight_py"] = highlight_py
j2.env.filters["highlight_sh"] = highlight_sh
j2.env.filters["highlight_r"] = highlight_r
j2.env.filters["replace_substrings"] = replace_substrings
j2.env.filters["root_name"] = root_name
j2.env.filters["shell_quote"] = shell_quote

def tab_count(count, total=None) -> Markup:
    """Badge for counts in tab handles: ``tab_count(n)`` or ``tab_count(done, total)`` for checklists."""
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 0
    if total is not None:
        state = "done" if n >= int(total) else "pending"
        return Markup(f'<span class="tab-count tab-count-{state}">{n}/{escape(total)}</span>')
    zero = " tab-count-zero" if n == 0 else ""
    return Markup(f'<span class="tab-count{zero}">{n}</span>')


j2.env.globals["tab_count"] = tab_count

# ─── Globals ported from add_context ───
j2.env.globals["app_version"] = "dev"
j2.env.globals["api_version"] = "dev"
j2.env.globals["db_version"] = "dev"
j2.env.globals["debug"] = settings.ENVIRONMENT == "dev"

# Categories — whole module injected so templates use C.EnumName
j2.env.globals["C"] = C
j2.env.globals["SEARCH_KINDS"] = SEARCH_KINDS

# Utilities
j2.env.globals["isna"] = pd.isna
j2.env.globals["notna"] = pd.notna
j2.env.globals["index_badge_class"] = barcodes.index_badge_class
j2.env.globals["units"] = units
j2.env.globals["uuid4"] = uuid4
j2.env.globals["hasattr"] = hasattr
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


def middle_truncate(path: str, max_len: int = 100, tail_len: int = 50) -> tuple[str, str]:
    """Split a path into (beginning, end) for middle-ellipsis rendering.

    If the path fits within *max_len*, the second element is empty.
    Otherwise the first element is everything except the last *tail_len*
    characters, and the second element is those last *tail_len* characters.
    The tail is kept long so the filename/child side dominates.
    """
    if len(path) <= max_len:
        return (path, "")
    return (path[:-tail_len], path[-tail_len:])


j2.env.filters["middle_truncate"] = middle_truncate


@jinja2.pass_context
def url_for(ctx: jinja2.runtime.Context, name: str, **path_params) -> str:
    """Custom url_for that handles static files without needing request.url_for.
    
    Unlike Flask, Starlette's url_for only substitutes path parameters and
    ignores extra kwargs. This wrapper appends leftover kwargs as query params.
    """
    request = ctx.get("request")
    if request is not None:
        external = bool(path_params.pop("_external", False))
        for key in ("_scheme", "_anchor"):
            path_params.pop(key, None)

        normalized: dict = {}
        for key, value in path_params.items():
            if isinstance(value, Path):
                value = value.as_posix() if value.parts else ""
            if value is None or value == "" or value == ".":
                continue
            normalized[key] = value
        path_params = normalized

        route_param_names = _get_route_param_names(request.app.router, name, set(path_params.keys()))
        url_kwargs = {k: v for k, v in path_params.items() if k in route_param_names}
        query_kwargs = {k: v for k, v in path_params.items() if k not in route_param_names}

        # Version static assets by modification time so browsers fetch them again after they change
        if name == "static" and "v" not in query_kwargs:
            if (version := _static_version(request, str(path_params.get("filename", "")))) is not None:
                query_kwargs["v"] = version

        try:
            url = absolute_url_for(request, name, external=external, **url_kwargs)
        except Exception:
            if name == "static":
                filename = path_params.get("filename", "")
                root_path = request.scope.get("root_path", "").rstrip("/")
                url = f"{root_path}/static/{filename.lstrip('/')}"
                if "v" in query_kwargs:
                    url = f"{url}?v={query_kwargs['v']}"
                return url
            raise

        if query_kwargs:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query_kwargs)}"

        return url
    raise RuntimeError(f"Cannot generate URL for '{name}' without a request context")

def _static_version(request, filename: str) -> int | None:
    """Modification time of a file served by the `static` mount, or None if it cannot be found."""
    for route in request.app.routes:
        if getattr(route, "name", None) == "static" and (directory := getattr(getattr(route, "app", None), "directory", None)):
            try:
                return int((Path(directory) / filename.lstrip("/")).stat().st_mtime)
            except OSError:
                return None
    return None

def absolute_url_for(request, name: str, *, external: bool = False, **path_params) -> URL:
    """Absolute URL of a route.

    With ``external`` (links that leave the app: emails, copy-paste commands) the configured
    ``external_base_url`` is used instead of the request's Host header, which the client
    controls. Without that setting it falls back to the request.
    """
    base = settings.app_config.external_base_url if external else None
    if base:
        return URL(base.rstrip("/") + request.app.url_path_for(name, **path_params))
    return request.url_for(name, **path_params)

def _get_route_param_names(router, name: str, provided: set[str] | None = None) -> set:
    """Extract path parameter names from a route by its name."""
    matches: list[set] = []
    for route in iter_route_contexts(router.routes):
        if route.name != name:
            continue
        params = set(getattr(route, "param_convertors", {}).keys())
        matches.append(params)
    if not matches:
        return set()
    if provided is None:
        return matches[0]
    exact = [params for params in matches if params == provided]
    if exact:
        return exact[0]
    subsets = [params for params in matches if params <= provided]
    if subsets:
        return max(subsets, key=len)
    return matches[0]

j2.env.globals["url_for"] = url_for

def render_template(template_name: str, include_request_context: bool = True, **kwargs) -> str:
    template: jinja2.Template = j2.get_template(template_name)
    if include_request_context:
        kwargs |= context.get_request_context()
    return template.render(**kwargs)
