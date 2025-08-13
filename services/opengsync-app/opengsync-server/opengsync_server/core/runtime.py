from typing import cast, TYPE_CHECKING

from flask import current_app as flask_app

if TYPE_CHECKING:
    from .App import App


class RunTime:
    @property
    def current_app(self) -> "App":
        from .App import App
        return cast(App, flask_app)


runtime = RunTime()
    