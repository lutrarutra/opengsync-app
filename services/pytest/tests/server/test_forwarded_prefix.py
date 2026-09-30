from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from server.core.middleware import XForwardedPrefixMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(XForwardedPrefixMiddleware)

    @app.get("/target", name="target")
    async def target(request: Request):
        return PlainTextResponse(f"{request.url_for('target')}|{request.scope['root_path']}")

    return app


def test_forwarded_prefix_is_used_for_url_generation():
    with TestClient(_app()) as client:
        response = client.get("/target", headers={"X-Forwarded-Prefix": "/opengsync/"})

    assert response.text == "http://testserver/opengsync/target|/opengsync"


def test_forwarded_prefix_is_visible_to_unhandled_exception_handler():
    app = _app()

    @app.exception_handler(Exception)
    async def handler(request: Request, e: Exception):
        return PlainTextResponse(request.url_for("target"), status_code=500)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Forwarded-Prefix": "/opengsync/v2"})

    assert response.status_code == 500
    assert response.text == "http://testserver/opengsync/v2/target"


def test_missing_forwarded_prefix_keeps_root_deployment_urls():
    with TestClient(_app()) as client:
        response = client.get("/target")

    assert response.text == "http://testserver/target|"
