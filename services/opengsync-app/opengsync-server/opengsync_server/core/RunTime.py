from typing import cast, TYPE_CHECKING

from flask import current_app as flask_app, session as fsession, url_for as furl_for
from flask_session.base import ServerSideSession

if TYPE_CHECKING:
    from .App import App


class RunTime:
    @property
    def app(self) -> "App":
        from .App import App
        return cast(App, flask_app)
    
    @property
    def session(self) -> ServerSideSession:
        return fsession  # type: ignore
    
    def url_for(self, endpoint: str, **values) -> str:
        if not self.app.external_base_url:
            return furl_for(endpoint, **values)
        
        external = values.pop("_external", False)
        internal_path = furl_for(endpoint, **values)

        if external:
            return f"{self.app.external_base_url}{internal_path}"
        
        return internal_path
            


runtime = RunTime()
    