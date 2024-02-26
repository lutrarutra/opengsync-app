import argparse

from flask import Flask

from limbless_server.app import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--static", type=str, default="/usr/src/app/static")
    parser.add_argument("--tempaltes", type=str, default="/usr/src/app/templates")
    args = parser.parse_args()

    app: Flask = create_app(static_folder=args.static, template_folder=args.tempaltes)

    ssl_context = ("cert/server.crt", "cert/server.key")
    app.run(host=args.host, port=args.port, debug=True, ssl_context=ssl_context)

exit(0)
