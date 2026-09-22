"""HTMXWorkflow / HTMXWorkflowStep: Redis state, isolation, expiry, and step gating."""

import types
import uuid as uuid_mod

import pandas as pd
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from starlette.datastructures import URL

from server.components import inputs
from server.core import context, dependencies, redis
from server.forms.HTMXForm import HTMXForm
from server.forms.workflows.HTMXWorkflow import HTMXWorkflow
from server.forms.workflows.HTMXWorkflowStep import HTMXWorkflowStep


class FirstStep(HTMXWorkflowStep):
    name = inputs.string.StringInputField("Name", required=False)


class SecondStep(HTMXWorkflowStep):
    note = inputs.string.StringInputField("Note", required=False)


class InapplicableStep(HTMXWorkflowStep):
    @classmethod
    def is_applicable(cls, workflow: "DummyWorkflow") -> bool:
        return False


class DummyWorkflow(HTMXWorkflow):
    @classmethod
    def Init(cls):
        def dependency(
            uuid: str | None = None,
            r: redis.RedisClient = Depends(dependencies.redis),
        ) -> "DummyWorkflow":
            return cls(uuid=uuid, r=r)

        return dependency


@pytest.fixture
def r(client: TestClient) -> redis.RedisClient:
    return redis.RedisClient(pool=client.app.state.redis_pool)


def _workflow(r: redis.RedisClient, uuid: str | None = None) -> DummyWorkflow:
    return DummyWorkflow(uuid=uuid, r=r)


def test_uuid_is_generated_when_missing_and_preserved_when_given(r: redis.RedisClient):
    first = _workflow(r)
    second = _workflow(r)

    assert uuid_mod.UUID(first.uuid)
    assert first.uuid != second.uuid

    fixed = _workflow(r, uuid="fixed-uuid")
    assert fixed.uuid == "fixed-uuid"
    assert fixed.key_prefix == "DummyWorkflow:fixed-uuid"
    assert fixed.step_tracker.prefix == "DummyWorkflow:fixed-uuid:steps"


def test_current_step_defaults_to_the_class_name(r: redis.RedisClient):
    assert _workflow(r).current_step == "DummyWorkflow"


def test_init_returns_a_callable_dependency():
    assert callable(DummyWorkflow.Init())


def test_step_tracker_round_trip_and_deduplication(r: redis.RedisClient):
    workflow_uuid = str(uuid_mod.uuid4())
    workflow = _workflow(r, uuid=workflow_uuid)

    workflow.add_step("A")
    workflow.add_step("A")
    workflow.add_step("B")

    assert workflow.step_tracker.steps == ["A", "B"]

    resumed = _workflow(r, uuid=workflow_uuid)

    assert resumed.current_step == "B"
    assert resumed.step_tracker.steps == ["A", "B"]
    assert resumed.pop_step() == "B"
    assert resumed.step_tracker.steps == ["A"]


def test_state_round_trip_and_cross_workflow_isolation(r: redis.RedisClient):
    workflow_uuid = str(uuid_mod.uuid4())
    workflow = _workflow(r, uuid=workflow_uuid)
    table = pd.DataFrame({"a": [1, 2]})

    workflow.tables["t"] = table
    workflow.metadata["k"] = "v"
    workflow.header["h"] = "header-value"
    workflow.save()

    resumed = _workflow(r, uuid=workflow_uuid)

    assert resumed.metadata["k"] == "v"
    assert resumed.header["h"] == "header-value"
    pd.testing.assert_frame_equal(resumed.tables["t"], table)

    other = _workflow(r)
    assert other.tables.keys() == []
    assert other.metadata.get("k") is None
    assert other.header.get("h") is None
    assert r.get_keys(f"DummyWorkflow:{other.uuid}:*") == []


def test_state_keys_expire(r: redis.RedisClient):
    workflow = _workflow(r)
    workflow.metadata["k"] = "v"
    workflow.tables["t"] = pd.DataFrame({"a": [1]})
    workflow.save()

    keys = r.get_keys(f"{workflow.key_prefix}:*")
    assert keys
    for key in keys:
        ttl = r.ttl(key)
        assert 0 < ttl <= r.ttl_hours * 3600


def test_complete_removes_only_its_own_keys(r: redis.RedisClient):
    first = _workflow(r)
    second = _workflow(r)
    first.metadata["k"] = "first"
    first.save()
    second.metadata["k"] = "second"
    second.save()

    assert r.get_keys(f"DummyWorkflow:{first.uuid}:*")

    first.complete()

    assert r.get_keys(f"DummyWorkflow:{first.uuid}:*") == []
    assert r.get_keys(f"DummyWorkflow:{second.uuid}:*")


def test_previous_url_accepts_url_string_and_none(r: redis.RedisClient):
    workflow = _workflow(r)

    assert workflow.previous_url is None

    workflow.previous_url = URL("http://example.com/projects/1?tab=data")
    assert workflow.previous_url == "http://example.com/projects/1?tab=data"

    workflow.previous_url = "/relative/path"
    assert workflow.previous_url == "/relative/path"

    workflow.previous_url = None
    assert workflow.previous_url is None


def test_step_switch_copies_state_into_empty_destination(r: redis.RedisClient):
    workflow = _workflow(r)
    table = pd.DataFrame({"a": [1]})
    workflow.tables["t"] = table
    workflow.metadata["k"] = "v"

    workflow.init_step("NextStep")

    assert workflow.current_step == "NextStep"
    pd.testing.assert_frame_equal(workflow.tables["t"], table)
    assert workflow.metadata["k"] == "v"


def test_forward_navigation_replaces_stale_destination_state(r: redis.RedisClient):
    workflow = _workflow(r)
    workflow.metadata["k"] = "stale"
    workflow.tables["t"] = pd.DataFrame({"a": [1]})
    workflow.save()

    workflow.init_step("NextStep")
    assert workflow.metadata["k"] == "stale"

    workflow.metadata["k"] = "fresh"
    workflow.tables["t"] = pd.DataFrame({"a": [2, 3]})
    workflow.save()

    with context.bind(types.SimpleNamespace(method="POST")):
        workflow.init_step("DummyWorkflow")

    assert workflow.current_step == "DummyWorkflow"
    assert workflow.metadata["k"] == "fresh"
    pd.testing.assert_frame_equal(workflow.tables["t"], pd.DataFrame({"a": [2, 3]}))


def test_previous_step_returns_the_last_tracked_step(r: redis.RedisClient):
    workflow = _workflow(r)
    workflow.add_step("A")
    workflow.init_step("B")

    assert workflow.current_step == "B"
    assert workflow.previous_step == "A"


def test_is_applicable_defaults_to_true_and_can_be_overridden(r: redis.RedisClient):
    workflow = _workflow(r)

    assert HTMXWorkflowStep.is_applicable(workflow) is True
    assert FirstStep.is_applicable(workflow) is True
    assert InapplicableStep.is_applicable(workflow) is False


def test_instantiating_a_step_sets_the_active_step(r: redis.RedisClient):
    workflow = _workflow(r)

    step = FirstStep(workflow)

    assert isinstance(step, HTMXForm)
    assert step.workflow is workflow
    assert workflow.current_step == "FirstStep"
    assert isinstance(SecondStep(workflow), HTMXForm)
    assert workflow.current_step == "SecondStep"
