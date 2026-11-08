"""The early barrier needs a coordinated tasklet and typed durable metadata."""

import copy

import pytest

from scripts.smoke.boot41_batch_early_crash import SEAM, SEAM_ANCHOR, early_ready


def state():
    return {
        "job": {"job_execution_id": 42, "status": "STARTED"},
        "parameter_records": [
            {"parameter_name": "runId", "parameter_value": "early-proof", "parameter_type": "java.lang.String", "identifying": "Y"},
            {"parameter_name": "businessDate", "parameter_value": "2026-09-27", "parameter_type": "java.time.LocalDate", "identifying": "N"},
        ],
        "context": {"runId": None, "frozenBusinessDate": None},
        "steps": [{"job_execution_id": 42, "step_name": "widgetRunIdentityStep", "status": "STARTED"}],
    }


@pytest.mark.parametrize("fault", ["empty", "missing-date", "string-date", "identifying-date", "frozen", "wrong-runId", "wrong-execution", "completed-step", "no-step", "data-step"])
def test_early_boundary_rejects_vacuous_or_wrong_observations(fault):
    value = copy.deepcopy(state())
    assert early_ready(value, 42, "early-proof")
    if fault == "empty":
        value = None
    elif fault == "missing-date":
        value["parameter_records"].pop()
    elif fault == "string-date":
        value["parameter_records"][1]["parameter_type"] = "java.lang.String"
    elif fault == "identifying-date":
        value["parameter_records"][1]["identifying"] = "Y"
    elif fault == "frozen":
        value["context"]["frozenBusinessDate"] = "2026-09-27"
    elif fault == "wrong-runId":
        value["parameter_records"][0]["parameter_value"] = "other"
    elif fault == "wrong-execution":
        value["job"]["job_execution_id"] = 43
    elif fault == "completed-step":
        value["steps"][0]["status"] = "COMPLETED"
    elif fault == "no-step":
        value["steps"] = []
    else:
        value["steps"].append({"step_name": "widgetEodStep", "status": "STARTED"})
    assert not early_ready(value, 42, "early-proof")


def test_seam_only_coordinates_before_original_decision_code():
    assert "authoritativeBusinessDate" not in SEAM
    assert "putString" not in SEAM
    assert "getJobExecutions" not in SEAM
    assert "CountDownLatch" in SEAM and "ATOMIC_MOVE" in SEAM
    assert "getJobExecution" in SEAM_ANCHOR
