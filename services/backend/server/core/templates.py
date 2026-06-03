from datetime import datetime
from fastapi.templating import Jinja2Templates

from .config import settings

j2 = Jinja2Templates(directory="/templates", enable_async=True)

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

async def render_template(template_name: str, **context) -> str:
    template = j2.get_template(template_name)
    return await template.render_async(**context)