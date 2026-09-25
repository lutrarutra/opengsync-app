"""No route may be unreachable because an earlier route always matches first.

Starlette tries routes in registration order (unlike Flask/werkzeug, which sorts
rules so static segments win over converters). Two routes on the same method and
path, or a catch-all like ``/{subpath:path}`` registered before a literal route,
silently make the later route dead: tests that hit the URL only see whichever
route answers. This has already hidden the seq-request assignee form, the
combined-lane experiment actions, and the file-browser share/associate forms.
"""

import re

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

_PARAM = re.compile(r"\{[^}:]+(:[^}]+)?\}")


def _api_routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif isinstance(route, Mount) and getattr(route, "routes", None):
            yield from _api_routes(route.routes)


def _shadowed_routes(app) -> list[str]:
    seen: list[APIRoute] = []
    shadowed: list[str] = []
    for route in _api_routes(app.routes):
        # Concrete URLs this route should answer: params filled with a number and with a word.
        samples = {_PARAM.sub(fill, route.path) for fill in ("1", "x")}
        for method in sorted(route.methods or ()):
            for earlier in seen:
                if method not in (earlier.methods or ()):
                    continue
                if earlier.endpoint is route.endpoint:
                    continue  # same handler registered under two paths, e.g. "/" and "/{subpath:path}"
                if all(earlier.path_regex.match(sample) for sample in samples):
                    shadowed.append(
                        f"{method} {route.path} [{route.name}] is shadowed by {earlier.path} [{earlier.name}]"
                    )
                    break
        seen.append(route)
    return shadowed


def test_no_route_is_shadowed_by_an_earlier_route(client: TestClient):
    shadowed = _shadowed_routes(client.app)
    assert not shadowed, "Unreachable routes:\n" + "\n".join(shadowed)
