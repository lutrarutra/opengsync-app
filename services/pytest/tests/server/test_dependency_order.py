"""Permission dependencies must run before a form is validated.

A form's ``Validate()`` re-renders the form (202) on invalid input, with whatever its ``Init`` loaded.
If the permission check comes later, any logged-in user gets that render: in the customer test
2026-11-04 an empty POST to ``/htmx/projects/{id}/edit-sample-attributes`` returned another customer's
sample sheet. FastAPI solves dependencies depth-first in declaration order (sub-dependencies before the
dependency, each callable once), so the check is on that order.
"""
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from server.core import dependencies

NOT_PERMISSIONS = {dependencies.require_user, dependencies.require_user_id}


def _is_permission(call) -> bool:
    """require_insider/admin/data_assigner, *_permissions, and workflow-local require_* checks."""
    name = getattr(call, "__name__", "")
    return call not in NOT_PERMISSIONS and (name.startswith("require_") or name.endswith("_permissions"))


# Forms validated without any permission dependency: public auth forms, and forms that check access
# in their route body on objects named in the form data (not in the path).
NO_PERMISSION_DEPENDENCY = {
    "/htmx/auth/login", "/htmx/auth/register", "/htmx/auth/activate/{token}",
    "/htmx/auth/complete-registration/{token}", "/htmx/auth/reset-password/{token}",
    "/htmx/auth/change-password", "/htmx/auth/forgot-password",
    "/htmx/comments/comment",  # checks access to the commented object after reading its id
    "/htmx/kits/check-barcode-constraints", "/htmx/kits/query-barcode-sequences",  # read-only lookups on public kits
    "/htmx/seq_requests/create",  # anyone logged in may create a request
    "/htmx/projects/create", "/htmx/pools/create", "/htmx/groups/create",  # create forms for any logged-in user
}

# Forms whose Init raises NoPermissionsException in its body (before Validate), on objects given in the
# query string; verified by the stranger sweep in test_route_sweep.py.
CHECKED_IN_INIT_PREFIXES = (
    "/htmx/files/upload",  # MediaFileForm.check_permissions
    "/htmx/workflows/reindex/", "/htmx/workflows/merge-pools/", "/htmx/workflows/library-remux/",
    "/htmx/workflows/index-check/",
    "/htmx/actions/reseq-action", "/htmx/actions/edit-library-properties-action",
)


def _routes(routes, prefix: str = "", router_calls: tuple = ()):
    """(path, route, calls of the enclosing routers' dependencies), which FastAPI solves first."""
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            context, router = route.include_context, route.original_router
            calls = tuple(d.dependency for d in [*(context.dependencies or []), *(router.dependencies or [])])
            yield from _routes(router.routes, prefix + (context.prefix or ""), router_calls + calls)
        elif isinstance(route, APIRoute):
            yield prefix + route.path, route, router_calls


def _solve_order(dependant, router_calls: tuple = ()) -> list:
    order: list = list(dict.fromkeys(router_calls))

    def visit(dep):
        for sub in dep.dependencies:
            visit(sub)
        if dep.call is not None and dep.call not in order:
            order.append(dep.call)

    for dep in dependant.dependencies:
        visit(dep)
    return order


def _is_validate(call) -> bool:
    return ".Validate." in getattr(call, "__qualname__", "")


def _form_routes(app):
    for path, route, router_calls in _routes(app.routes):
        order = _solve_order(route.dependant, router_calls)
        if (index := next((i for i, call in enumerate(order) if _is_validate(call)), None)) is not None:
            yield path, route, order, index


def test_permission_dependencies_run_before_form_validation(client: TestClient):
    late = []
    for path, route, order, validate_index in _form_routes(client.app):
        for i, call in enumerate(order):
            if _is_permission(call) and i > validate_index:
                late.append(f"{sorted(route.methods)} {path}: {call.__name__} after Validate")
    assert late == []


def test_validated_forms_have_a_permission_dependency(client: TestClient):
    missing = []
    for path, route, order, validate_index in _form_routes(client.app):
        if path in NO_PERMISSION_DEPENDENCY or path.startswith(CHECKED_IN_INIT_PREFIXES):
            continue
        if not any(_is_permission(call) for call in order[:validate_index]):
            missing.append(f"{sorted(route.methods)} {path}")
    assert missing == []
