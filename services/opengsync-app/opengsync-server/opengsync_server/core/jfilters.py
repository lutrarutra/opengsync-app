from datetime import datetime

from .. import logger
from .App import App


def inject_jinja_format_filters(app: App):
    @app.template_filter()
    def format_iso(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
        """Format a datetime string to a given format."""
        if not value:
            return ""
        try:
            dt = datetime.fromisoformat(value).astimezone(app.timezone)
        except ValueError as e:
            logger.error(f"Error formatting date: {e}")
            return "<error formatting time>"

        return dt.strftime(fmt)
    
    @app.template_filter()
    def from_timestamp(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
        """Convert a timestamp to a formatted string."""
        if not value:
            return ""
        try:
            dt = datetime.fromtimestamp(float(value)).astimezone(app.timezone)
        except ValueError as e:
            logger.error(f"Error converting timestamp: {e}")
            return "<error formatting time>"

        return dt.strftime(fmt)
    
    @app.template_filter()
    def format_datetime(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
        """Format a datetime object to a given format."""
        if value is None:
            return ""
        if not isinstance(value, datetime):
            raise TypeError(f"Expected datetime, got {type(value)}")
        return value.astimezone(app.timezone).strftime(fmt)
    
    @app.template_filter()
    def bytes_to_human(size: int | None) -> str:
        if size is None or size < 0:
            return ""
        
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:  # type: ignore
                if unit == "B":
                    return f"{size} {unit}"
                return f"{size:.2f} {unit}"
            size /= 1024  # type: ignore
        return f"{size:.2f} PB"
    
    @app.template_filter()
    def highlight_py(code: str) -> str:
        from pygments import highlight
        from pygments.lexers import PythonLexer
        from pygments.formatters import HtmlFormatter

        formatter = HtmlFormatter(style="friendly", noclasses=True)
        return highlight(code, PythonLexer(), formatter)
    
    @app.template_filter()
    def highlight_sh(code: str) -> str:
        from pygments import highlight
        from pygments.lexers import BashLexer
        from pygments.formatters import HtmlFormatter

        formatter = HtmlFormatter(style="friendly", noclasses=True)
        return highlight(code, BashLexer(), formatter)
    
    @app.template_filter()
    def highlight_r(code: str) -> str:
        from pygments import highlight
        from pygments.lexers import RLexer
        from pygments.formatters import HtmlFormatter

        formatter = HtmlFormatter(style="friendly", noclasses=True)
        return highlight(code, RLexer(), formatter)