import pytest

from opengsync_db.categories import LibraryStatus as LB, PoolStatus as PL, OperationKind as K, SeqRequestStatus as RQ
from opengsync_db.transitions import Registry, RegistryError, registry, routes
from opengsync_db.transitions import entities as E
from opengsync_db.transitions.core import ANY, NEW, Entity, Route, Step, effect, operation
from opengsync_db.transitions.operations import MODULES
from opengsync_db.transitions.rules import StatusIn


def _all_ops():
    return [op for module in MODULES for op in module.ALL]


def test_registry_is_valid():
    registry().validate()


def test_every_operation_is_registered():
    reg = registry()
    assert len(reg.operations) == len(_all_ops())


def test_duplicate_id_is_rejected():
    op = operation("request.submit", "Submit", K.ACTION, E.SEQ_REQUEST, effect(E.SEQ_REQUEST, RQ.DRAFT, RQ.SUBMITTED))
    reg = Registry(_all_ops() + [op], routes.ROUTES)
    with pytest.raises(RegistryError, match="duplicate operation id 'request.submit'"):
        reg.validate()


@pytest.mark.parametrize("bad_id", ["submit", "Request.submit", "request.", "request.submit-now", "a." + "x" * 70])
def test_invalid_operation_id(bad_id: str):
    op = operation(bad_id, "Bad", K.ACTION, E.SEQ_REQUEST)
    problems = Registry(_all_ops() + [op], routes.ROUTES).problems()
    assert any(bad_id in p and "slug" in p for p in problems)


def test_wrong_status_enum_in_effect():
    op = operation("test.wrong_enum", "Wrong", K.ACTION, E.LIBRARY, effect(E.LIBRARY, PL.DRAFT, LB.POOLED))
    problems = Registry(_all_ops() + [op], routes.ROUTES).problems()
    assert any("test.wrong_enum" in p and "is not a LibraryStatus" in p for p in problems)


def test_unresolvable_relationship_path():
    op = operation("test.bad_path", "Bad path", K.ACTION, E.SEQ_REQUEST, effect(E.LIBRARY, ANY, LB.POOLED, via="libraries.nope"))
    problems = Registry(_all_ops() + [op], routes.ROUTES).problems()
    assert any("'nope' in 'libraries.nope' is not a relationship of Library" in p for p in problems)


def test_implicit_operation_needs_reason():
    op = operation("worker.no_reason", "No reason", K.WORKER, E.LIBRARY, effect(E.LIBRARY, LB.POOLED, LB.SEQUENCED))
    problems = Registry(_all_ops() + [op], routes.ROUTES).problems()
    assert any("worker.no_reason: WORKER operations need a reason template" in p for p in problems)


def test_effect_cannot_set_null():
    op = operation("test.to_null", "Null", K.ACTION, E.SAMPLE, effect(E.SAMPLE, ANY, NEW))
    problems = Registry(_all_ops() + [op], routes.ROUTES).problems()
    assert any("test.to_null: an effect cannot set the status to NULL" in p for p in problems)


def test_unreachable_status_without_annotation():
    bare = Entity("library", "Library", "Library", LB)  # no manual_only / unused annotations
    problems = Registry(_all_ops(), routes.ROUTES, entities=[bare]).problems(resolve_relations=False)
    for status in (LB.ARCHIVED, LB.REMOVED, LB.QC_COMPLETED):
        assert f"Library {status.name} is set by no operation; declare it or list it in manual_only/unused" in problems


def test_annotated_status_that_is_reachable():
    annotated = Entity("library", "Library", "Library", LB, manual_only=frozenset([LB.POOLED, LB.ARCHIVED, LB.REMOVED, LB.QC_COMPLETED]))
    problems = Registry(_all_ops(), routes.ROUTES, entities=[annotated]).problems(resolve_relations=False)
    assert "Library POOLED is listed as manual_only/unused but set by an operation" in problems


def test_route_with_unknown_operation():
    route = Route("test_route", "Test", E.SEQ_REQUEST, StatusIn(frozenset([RQ.DRAFT])), (
        Step("x", "X", ("request.submit", "request.does_not_exist"), StatusIn(frozenset([RQ.SUBMITTED]))),
    ))
    problems = Registry(_all_ops(), list(routes.ROUTES) + [route]).problems()
    assert "route test_route, step x: unknown operation 'request.does_not_exist'" in problems


def test_manual_operations_are_not_process_edges():
    reg = registry()
    edge_ops = {edge.operation.id for entity in reg.entities for edge in reg.edges(entity)}
    assert not any(id.startswith(("manual.", "migration.", "system.")) for id in edge_ops)


def test_chosen_status_is_not_an_edge():
    reg = registry()
    assert all(edge.operation.id != "pool.create" for edge in reg.edges(E.POOL))
