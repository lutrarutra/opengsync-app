from opengsync_server.core.App import App
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app(config_path: str) -> App:
    app = App(config_path=config_path)
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_proto=1,
        x_host=1,
        x_prefix=1,
    )
    return app