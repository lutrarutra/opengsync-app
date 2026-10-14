"""Every request a template makes to a named route uses a method the route accepts (§5).

Covers ``hx-get/post/put/delete/patch="{{ url_for('name', ...) }}"``, context-menu entries
(``"type": "hxdelete", "config": {"url": url_for(...)}``) and ``htmx.ajax("POST", "{{ url_for(...) }}")``.
URLs held in variables (``form.post_url``, ``form.previous_url``) come from ``htmx_route`` and are
exercised by the form tests. Legacy and FastAPI share the templates folder; a name FastAPI does
not know belongs to a legacy-only template and is skipped.
"""

import re
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient

from .test_route_sweep import _routes

_REFERENCES = [
    re.compile(r"""hx-(get|post|put|delete|patch)="\{\{\s*url_for\(\s*['"]([\w.]+)['"]""", re.I),
    re.compile(r"""["']type["']:\s*["']hx(get|post|put|delete|patch)["'][^{}]*?\{[^{}]*?url_for\(\s*['"]([\w.]+)['"]""", re.I | re.S),
    re.compile(r"""htmx\.ajax\(\s*['"](get|post|put|delete|patch)['"]\s*,\s*['"`]?\{\{\s*url_for\(\s*['"]([\w.]+)['"]""", re.I),
]


def test_template_requests_use_the_route_method(client: TestClient):
    from server.core.templates import j2

    methods: dict[str, set[str]] = defaultdict(set)
    for _, route in _routes(client.app.routes):
        methods[route.name] |= route.methods

    root = Path(j2.env.loader.searchpath[0])  # type: ignore[union-attr]
    checked, mismatches = 0, []
    for path in sorted(root.rglob("*.htm*")):
        text = path.read_text()
        for pattern in _REFERENCES:
            for match in pattern.finditer(text):
                method, name = match.group(1).upper(), match.group(2)
                if name not in methods:
                    continue
                checked += 1
                if method not in methods[name]:
                    mismatches.append(f"{path.relative_to(root)}: {method} {name} (route accepts {sorted(methods[name])})")

    assert checked > 250
    assert mismatches == []
