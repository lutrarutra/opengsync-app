"""LibraryAnnotationWorkflow: 'Back' works from every step of every scenario.

Re-runs each scenario in this package with ``AnnotationWorkflow.back_and_resubmit`` on:
after every successful step the driver goes back to it (its ``Previous`` route must
re-render that step) and submits the same data again, which must lead to the same next
step. The scenario's own assertions on the created records then also check that nothing
was applied twice.

Scenarios that need parameters, the two ``test_simple_*`` files (which post without the
driver), and the negative tests on access, step order, state and rollback are not re-run.
"""

import importlib
import inspect
from pathlib import Path

import pytest

from ._workflow import AnnotationWorkflow

SKIP = {
    Path(__file__).stem,
    "test_simple_raw_bulk_rna_seq",
    "test_simple_pooled_bulk_rna_seq",
    "test_access_submitted_request",
    "test_step_order",
    "test_workflow_state",
    "test_completion_rollback",
}


def _scenarios():
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        if path.stem in SKIP:
            continue
        module = importlib.import_module(f"{__package__}.{path.stem}")
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("test_") and func.__module__ == module.__name__ and not hasattr(func, "pytestmark"):
                yield pytest.param(func, id=f"{path.stem}::{name}")


@pytest.mark.parametrize("scenario", list(_scenarios()))
def test_back_and_resubmit_every_step(request, monkeypatch, scenario):
    monkeypatch.setattr(AnnotationWorkflow, "back_and_resubmit", True)
    scenario(**{name: request.getfixturevalue(name) for name in inspect.signature(scenario).parameters})
