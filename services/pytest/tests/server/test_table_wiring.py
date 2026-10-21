"""Every HTMX table route accepts what its column headers send (fastapi-table.js).

A searchable column sends ``<label>=<value>``, a column with choices ``<label>_in=[ids]`` and a
sortable column ``order_by=<sort_by>:asc|desc``. A route that does not declare the parameter
silently ignores it, so the search box / filter / sort button does nothing; a ``sort_by`` the
route's ``parse_order_by`` model lacks answers 400.
"""

import inspect
import re
from collections.abc import Iterator

import sqlalchemy as sa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from opengsync_db import SyncSession

TABLE_INSTANTIATION = re.compile(r"\b(\w+Table)\(")


def _routes(routes, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _routes(route.original_router.routes, prefix + (route.include_context.prefix or ""))
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route


def _wire_params(dependant) -> Iterator[str]:
    for param in dependant.query_params:
        yield param.alias
    for dependency in dependant.dependencies:
        yield from _wire_params(dependency)


def _order_model(dependant):
    for dependency in dependant.dependencies:
        if getattr(dependency.call, "__qualname__", "").startswith("parse_order_by."):
            return inspect.getclosurevars(dependency.call).nonlocals["model"]
        if (model := _order_model(dependency)) is not None:
            return model
    return None


def _table_routes(app):
    from server.components.tables import HTMXTable

    for path, route in _routes(app.routes):
        source = inspect.getsource(route.endpoint)
        for name in sorted(set(TABLE_INSTANTIATION.findall(source))):
            table = route.endpoint.__globals__.get(name)
            if isinstance(table, type) and issubclass(table, HTMXTable) and table.columns:
                yield path, route, table


def test_table_columns_reach_their_route(client: TestClient):
    table_routes = list(_table_routes(client.app))
    assert len(table_routes) >= 24, "table route discovery broke"

    problems = []
    for path, route, table in table_routes:
        params = set(_wire_params(route.dependant))
        for col in table.columns:
            if col.searchable and col.label not in params:
                problems.append(f"{path} [{table.__name__}]: search '{col.label}' is not a query param")
            if col.choices and f"{col.label}_in" not in params:
                problems.append(f"{path} [{table.__name__}]: filter '{col.label}_in' is not a query param")
            if col.sortable and "order_by" not in params:
                problems.append(f"{path} [{table.__name__}]: sort '{col.sort_by}' but no order_by param")
    assert not problems, "\n".join(problems)


def test_table_sort_columns_order_in_sql(client: TestClient, session: SyncSession):
    problems = []
    for path, route, table in _table_routes(client.app):
        if (model := _order_model(route.dependant)) is None:
            continue
        for col in table.columns:
            if not col.sortable:
                continue
            attr = getattr(model, col.sort_by, None)  # type: ignore[arg-type]
            if attr is None:
                problems.append(f"{path} [{table.__name__}]: {model.__name__} has no '{col.sort_by}'")
                continue
            for direction in ("asc", "desc"):
                session.execute(sa.select(model).order_by(getattr(attr, direction)()).limit(1)).all()
    assert not problems, "\n".join(problems)
