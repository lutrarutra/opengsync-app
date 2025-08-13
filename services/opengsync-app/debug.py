import argparse

from opengsync_server.core.App import App


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--static", type=str, default="/usr/src/app/static")
    parser.add_argument("--templates", type=str, default="/usr/src/app/templates")
    parser.add_argument("--config", type=str, default="/usr/src/app/opengsync-server/opengsync.yaml")
    args = parser.parse_args()

    app = App(
        static_folder=args.static,
        template_folder=args.templates,
        config_path=args.config
    )

    # ssl_context = ("cert/server.crt", "cert/server.key")
    ssl_context = None
    app.run(host=args.host, port=args.port, debug=True, ssl_context=ssl_context, threaded=False)

exit(0)
