import argparse

from flask import Flask

from opengsync_server.app import create_app
from opengsync_server import logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--static", type=str, default="/usr/src/app/static")
    parser.add_argument("--tempaltes", type=str, default="/usr/src/app/templates")
    args = parser.parse_args()

    app: Flask = create_app(static_folder=args.static, template_folder=args.tempaltes)

    # ssl_context = ("cert/server.crt", "cert/server.key")
    ssl_context = None
    logger.debug(f"Running on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True, ssl_context=ssl_context, threaded=False)

exit(0)
