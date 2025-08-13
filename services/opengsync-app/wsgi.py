from opengsync_server.core.App import App


def create_app(
    static_folder: str,
    template_folder: str,
    config_path: str
) -> App:
    app = App(
        static_folder=static_folder,
        template_folder=template_folder,
        config_path=config_path
    )
    return app