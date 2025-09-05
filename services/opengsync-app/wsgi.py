from opengsync_server.core.App import App


def create_app(config_path: str) -> App:
    app = App(config_path=config_path)
    return app