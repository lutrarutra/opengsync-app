from typing import cast, TYPE_CHECKING

from flask import current_app as flask_app, session as fsession
from flask_session.base import ServerSideSession

if TYPE_CHECKING:
    from .App import App


class RunTime:
    @property
    def current_app(self) -> "App":
        from .App import App
        return cast(App, flask_app)
    
    @property
    def session(self) -> ServerSideSession:
        return fsession  # type: ignore


runtime = RunTime()
    