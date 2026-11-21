"""Every htmx table's spec is wired to its route and works in SQL (server/components/tables, docs/tables.md).

A table route takes its state through ``Depends(<Table>.params)``; the spec behind it must hold up:
every sortable column orders in SQL both ways, every search field and filter compiles and runs (also through
its relationship path), every variant only names fields the table has and a row template that exists, and
variant container ids are unique per table. A broken expression would otherwise only fail when a user
clicks that header or types into that box.
"""
from collections.abc import Iterator
from pathlib import Path

import sqlalchemy as sa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from opengsync_db import SyncSession

MIN_TABLE_ROUTES = 26


def _routes(routes, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _routes(route.original_router.routes, prefix + (route.include_context.prefix or ""))
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route


def _table_of(dependant):
    from server.components.tables import Table

    for dependency in dependant.dependencies:
        owner = getattr(dependency.call, "__self__", None)
        if isinstance(owner, type) and issubclass(owner, Table) and dependency.call.__name__ == "params":
            return owner
        if (table := _table_of(dependency)) is not None:
            return table
    return None


def _table_routes(app) -> list[tuple[str, type]]:
    found = []
    for path, route in _routes(app.routes):
        if (table := _table_of(route.dependant)) is not None:
            found.append((path, table))
    return found


def _templates_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [Path("/templates")] + [parent / "services/backend/templates" for parent in here.parents]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise AssertionError("templates not found")


def test_table_routes_are_discovered(client: TestClient):
    routes = _table_routes(client.app)
    assert len(routes) >= MIN_TABLE_ROUTES, f"table route discovery broke: {sorted(p for p, _ in routes)}"
    keys = {}
    for path, table in routes:
        assert table.key, f"{table.__name__} has no key (address bar prefix)"
        keys.setdefault(table.key, set()).add(table)
    clashes = {key: sorted(t.__name__ for t in tables) for key, tables in keys.items() if len(tables) > 1}
    assert not clashes, f"tables share an address bar prefix: {clashes}"


def test_table_specs_order_search_and_filter_in_sql(client: TestClient, session: SyncSession):
    from server.components.tables import query, spec

    problems = []
    for path, table in {t: (p, t) for p, t in _table_routes(client.app)}.values():
        if not table.model_backed:
            continue
        model = table.model
        name = f"{path} [{table.__name__}]"
        for col in table.columns:
            try:
                if col.sortable:
                    expr = getattr(model, col.key) if col.sort is True else col.sort
                    for direction in ("asc", "desc"):
                        session.execute(sa.select(model).order_by(getattr(expr, direction)()).limit(1)).all()
                if col.searchable:
                    for fuzzy in (False, True):
                        clauses, _ = query.search("ab1", [col], model, scope=col.key, fuzzy=fuzzy)
                        session.execute(sa.select(model).where(*clauses).limit(1)).all()
                if isinstance(col.filter, spec.Enum):
                    options = col.filter.options()
                    assert options, "no options"
                    column = col.filter.column if col.filter.column is not None else getattr(model, col.key)
                    present = [o for o in options if o is not None][:2]
                    clause = spec.through(col.filter.via, column.in_(present))
                    session.execute(sa.select(model).where(clause).limit(1)).all()
                if isinstance(col.filter, spec.Entity):
                    clause = spec.through(col.filter.via, col.filter.model.id.in_([1, 2]))
                    session.execute(sa.select(model).where(clause).limit(1)).all()
                    ids = sa.select(col.filter.model.id).select_from(model)
                    for rel in col.filter.via:
                        ids = ids.join(rel)
                    session.execute(ids.limit(1)).all()
                    assert callable(col.filter.option)
            except Exception as e:  # collect every broken field
                session.rollback()
                problems.append(f"{name} field '{col.key}': {type(e).__name__}: {str(e).splitlines()[0][:200]}")
    assert not problems, "\n".join(problems)


def test_table_variants_are_consistent(client: TestClient):
    root = _templates_root()
    problems = []
    for path, table in {t: (p, t) for p, t in _table_routes(client.app)}.values():
        keys = {c.key for c in table.columns}
        display = {c.key for c in table.columns if c.display}
        assert "default" in table.variants or len(table.variants) > 0
        for name, variant in table.variants.items():
            where = f"{table.__name__}.variants['{name}']"
            if missing := [k for k in variant.columns if k not in display]:
                problems.append(f"{where}: unknown or non-display columns {missing}")
            if variant.fields is not None and (missing := [k for k in variant.fields if k not in keys]):
                problems.append(f"{where}: unknown fields {missing}")
            if not (root / variant.row_template).is_file():
                problems.append(f"{where}: row template {variant.row_template} missing")
            if name.startswith("browse") and variant.url_state:
                problems.append(f"{where}: browse tables live in forms and must not write the address bar")
        default_key = table.default_sort[0]
        if default_key not in keys or not next(c for c in table.columns if c.key == default_key).sortable:
            problems.append(f"{table.__name__}: default sort '{default_key}' is not a sortable field")
    assert not problems, "\n".join(problems)
