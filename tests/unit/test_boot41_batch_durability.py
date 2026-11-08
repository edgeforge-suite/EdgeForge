"""Crash proof must observe the committed identity, not just a running job."""

import copy
import json
from types import SimpleNamespace

import pytest

from scripts.smoke import boot41_batch_durability as proof


def boundary():
    return {
        "job": {"job_execution_id": 42, "job_instance_id": 7, "status": "STARTED"},
        "parameters": {"runId": "synthetic-abrupt", "businessDate": "2026-09-27"},
        "context": {"runId": "synthetic-abrupt", "frozenBusinessDate": "2026-09-27"},
        "serialized_context": "committed-context",
        "steps": [
            {"step_execution_id": 81, "job_execution_id": 42, "step_name": "widgetRunIdentityStep", "status": "COMPLETED"},
            {"step_execution_id": 82, "job_execution_id": 42, "step_name": "widgetEodStep", "status": "STARTED"},
        ],
    }


def ready(state, execution_id=42):
    return proof._crash_boundary_ready(state, execution_id, "synthetic-abrupt", "2026-09-27")


def test_started_job_alone_never_satisfies_crash_barrier(monkeypatch):
    state = boundary()
    state.update(context={}, steps=[])
    assert not ready(state)
    times = iter([0, 0, 1])
    monkeypatch.setattr(proof.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(proof.time, "sleep", lambda _: None)
    with pytest.raises(AssertionError, match="Timed out waiting for committed crash boundary"):
        proof._wait_for_crash_boundary(lambda: state, "synthetic-abrupt", "2026-09-27", timeout=1)


@pytest.mark.parametrize("change", [
    "missing-context", "changed-date", "wrong-context-owner", "identity-started",
    "data-not-started", "job-not-started", "wrong-step-execution", "wrong-parameter",
])
def test_barrier_requires_all_persisted_conditions(change):
    state = boundary()
    if change == "missing-context":
        state["context"] = {}
    elif change == "changed-date":
        state["context"]["frozenBusinessDate"] = "2026-09-28"
    elif change == "wrong-context-owner":
        state["context"]["runId"] = "another-owner"
    elif change == "identity-started":
        state["steps"][0]["status"] = "STARTED"
    elif change == "data-not-started":
        state["steps"][1]["status"] = "STARTING"
    elif change == "job-not-started":
        state["job"]["status"] = "COMPLETED"
    elif change == "wrong-step-execution":
        state["steps"][1]["job_execution_id"] = 43
    else:
        state["parameters"]["businessDate"] = "2026-09-28"
    assert not ready(state)


def test_wait_observes_state_transition_and_binds_exact_execution(monkeypatch):
    early = boundary()
    early["context"] = {}
    early["steps"][0]["status"] = "STARTED"
    snapshots = iter([None, early, boundary()])
    monkeypatch.setattr(proof.time, "sleep", lambda _: None)
    assert proof._wait_for_crash_boundary(lambda: next(snapshots), "synthetic-abrupt", "2026-09-27") == boundary()
    assert ready(boundary())
    assert not ready(boundary(), execution_id=43)


def test_snapshot_decodes_database_context_and_keeps_original_records():
    state = boundary()
    del state["context"]
    calls = []

    def sql(query):
        calls.append(query)
        return json.dumps([state], indent=2)

    result = proof._execution_snapshot(sql, "synthetic-abrupt", lambda value: boundary()["context"])
    assert result == boundary()
    assert "COALESCE(c.serialized_context,c.short_context)" in calls[0]
    assert "parameter_value='synthetic-abrupt'" in calls[0]
    assert proof._execution_snapshot(lambda _: "[]", "synthetic-abrupt", lambda _: {}) is None
    with pytest.raises(AssertionError, match="exactly one execution"):
        proof._execution_snapshot(lambda _: json.dumps([state, state]), "synthetic-abrupt", lambda _: {})


def test_classification_changes_only_exact_dead_owners_running_records():
    before = boundary()
    after = copy.deepcopy(before)
    after["job"]["status"] = "FAILED"
    after["steps"][1]["status"] = "FAILED"
    snapshots = iter([before, after])
    statements = []
    result = proof._classify_dead_execution(statements.append, lambda: next(snapshots), SimpleNamespace(poll=lambda: -9), before)
    assert result == after
    assert result["steps"][0] == before["steps"][0]
    assert "job_execution_id=42 AND step_execution_id=82 AND status='STARTED'" in statements[0]
    assert "job_execution_id=42 AND status='STARTED'" in statements[0]
    assert " IN " not in statements[0]


@pytest.mark.parametrize("unsafe", ["live-owner", "changed-state", "completed-identity-corrupted"])
def test_classification_rejects_unverified_or_corrupted_state(unsafe):
    before = boundary()
    changed = copy.deepcopy(before)
    changed["steps"][0]["status"] = "FAILED"
    if unsafe == "completed-identity-corrupted":
        changed["job"]["status"] = "FAILED"
        changed["steps"][1]["status"] = "FAILED"
    statements = []
    snapshots = iter([changed if unsafe == "changed-state" else before, changed])
    with pytest.raises(AssertionError):
        proof._classify_dead_execution(
            statements.append, lambda: next(snapshots),
            SimpleNamespace(poll=lambda: None if unsafe == "live-owner" else -9), before,
        )
    if unsafe != "completed-identity-corrupted":
        assert not statements
