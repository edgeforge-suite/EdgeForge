import pytest

from scripts.smoke.generated_app_health import healthy_response


@pytest.mark.parametrize("response", [
    {"status": "UP"},
    {"groups": ["liveness", "readiness"], "status": "UP"},
    {"status": "UP", "components": {"db": {"status": "UP", "details": {"database": "H2"}}}},
])
def test_health_requires_up_while_accepting_actuator_metadata(response):
    assert healthy_response(response)


@pytest.mark.parametrize("response", [
    None, [], {}, {"status": "DOWN"}, {"status": "UNKNOWN"},
    {"status": "UP", "components": []},
    {"status": "UP", "components": {"db": {"status": "DOWN"}}},
    {"status": "UP", "components": {"db": {}}},
    {"status": "UP", "components": {"nested": {"status": "UP", "components": {"db": {"status": "OUT_OF_SERVICE"}}}}},
])
def test_unhealthy_or_malformed_health_response_is_refused(response):
    assert not healthy_response(response)
