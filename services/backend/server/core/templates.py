from pathlib import Path
from datetime import datetime

import pandas as pd
import jinja2
from fastapi.templating import Jinja2Templates

from opengsync_db import categories as cats
from opengsync_db import units

from .config import settings

j2 = Jinja2Templates(directory="/templates", enable_async=True, undefined=jinja2.StrictUndefined if settings.ENVIRONMENT != "prod" else jinja2.Undefined)

def format_timestamp(value: float, format: str = "%Y-%m-%d %H:%M"):
    """Convert timestamp to readable string"""
    return datetime.fromtimestamp(value).strftime(format)

def format_datetime(value: datetime, format: str = "%Y-%m-%d %H:%M"):
    """Convert datetime to readable string"""
    return value.astimezone(settings.TIMEZONE).strftime(format)


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
    import markdown
    return Markup(markdown.markdown(value))

j2.env.filters["format_timestamp"] = format_timestamp
j2.env.filters["format_datetime"] = format_datetime
j2.env.filters["format_markdown"] = format_markdown

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

# Categories
j2.env.globals["ExperimentStatus"] = cats.ExperimentStatus
j2.env.globals["SeqRequestStatus"] = cats.SeqRequestStatus
j2.env.globals["LibraryStatus"] = cats.LibraryStatus
j2.env.globals["UserRole"] = cats.UserRole
j2.env.globals["DataDeliveryMode"] = cats.DataDeliveryMode
j2.env.globals["GenomeRef"] = cats.GenomeRef
j2.env.globals["LibraryType"] = cats.LibraryType
j2.env.globals["PoolStatus"] = cats.PoolStatus
j2.env.globals["ServiceType"] = cats.ServiceType
j2.env.globals["SampleStatus"] = cats.SampleStatus
j2.env.globals["RunStatus"] = cats.RunStatus
j2.env.globals["SubmissionType"] = cats.SubmissionType
j2.env.globals["AttributeType"] = cats.AttributeType
j2.env.globals["IndexType"] = cats.IndexType
j2.env.globals["EventType"] = cats.EventType
j2.env.globals["PrepStatus"] = cats.PrepStatus
j2.env.globals["LabChecklistType"] = cats.LabChecklistType
j2.env.globals["PoolType"] = cats.PoolType
j2.env.globals["KitType"] = cats.KitType
j2.env.globals["AffiliationType"] = cats.AffiliationType
j2.env.globals["ProjectStatus"] = cats.ProjectStatus
j2.env.globals["MediaFileType"] = cats.MediaFileType
j2.env.globals["MUXType"] = cats.MUXType
j2.env.globals["DataPathType"] = cats.DataPathType
j2.env.globals["ExperimentWorkFlow"] = cats.ExperimentWorkFlow
j2.env.globals["DeliveryStatus"] = cats.DeliveryStatus
j2.env.globals["TaskStatus"] = cats.TaskStatus
j2.env.globals["FlowCellType"] = cats.FlowCellType

# Utilities
j2.env.globals["isna"] = pd.isna
j2.env.globals["notna"] = pd.notna
j2.env.globals["units"] = units
j2.env.globals["SpreadSheetErrors"] = [
    # ssc.InvalidCellValue(""),
    # ssc.MissingCellValue(""),
    # ssc.DuplicateCellValue(""),
]


@jinja2.pass_context
def url_for(ctx: jinja2.runtime.Context, name: str, **path_params) -> str:
    """Custom url_for that handles static files without needing request.url_for."""
    request = ctx.get("request")
    if request is not None:
        try:
            return request.url_for(name, **path_params)
        except Exception:
            if name == "static":
                filename = path_params.get("filename", "")
                return f"/static/{filename.lstrip('/')}"
            raise
    raise RuntimeError(f"Cannot generate URL for '{name}' without a request context")

j2.env.globals["url_for"] = url_for

async def render_template(template_name: str, **context) -> str:
    template = j2.get_template(template_name)
    return await template.render_async(**context)
