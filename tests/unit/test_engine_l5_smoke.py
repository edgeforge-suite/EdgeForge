from __future__ import annotations

from pathlib import Path

import pytest

from scripts.smoke import engine_l5_smoke


def test_engine_l5_entrypoints_are_suite_callable() -> None:
    assert callable(engine_l5_smoke.run_engine_l5_runtime)
    assert callable(engine_l5_smoke.run_engine_l5_regen)
    assert callable(engine_l5_smoke.run_engine_l5_change_plan)


def test_engine_l5_runtime_skip_guard_when_docker_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(engine_l5_smoke, "_docker_available", lambda: False)

    result = engine_l5_smoke.run_engine_l5_runtime()

    assert result.status == "skipped"
    assert result.name == "engine-l5-runtime"
    assert "Docker is unavailable" in result.warnings[0]


def test_engine_l5_runtime_require_services_turns_skip_into_failure(monkeypatch) -> None:
    monkeypatch.setattr(engine_l5_smoke, "_docker_available", lambda: False)

    result = engine_l5_smoke.run_engine_l5_runtime(require_services=True)

    assert result.status == "failed"
    assert "Docker is unavailable" in (result.error or "")


def test_engine_l5_runtime_probes_xxe_and_entity_expansion_at_ws(monkeypatch) -> None:
    requests: list[tuple[str, str]] = []

    monkeypatch.setattr(engine_l5_smoke, "_docker_exec", lambda *args, **kwargs: "")

    def reject_unsafe_envelope(method, url, *, body=None, headers=None):
        if method == "GET":
            assert url.endswith("/actuator/health")
            return 200, '{"status":"UP"}'
        assert method == "POST" and url.endswith("/ws")
        assert headers["SOAPAction"] == "urn:getCustomer"
        envelope = body.decode("utf-8")
        requests.append((method, envelope))
        if "<!DOCTYPE" in envelope or len(body) > engine_l5_smoke.SOAP_ENVELOPE_MAX_BYTES:
            return 400, (
                '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
                "<soapenv:Body><soapenv:Fault><faultstring>Malformed SOAP/XML request: "
                "Rejected unsafe SOAP/XML envelope.</faultstring></soapenv:Fault>"
                "</soapenv:Body></soapenv:Envelope>"
            )
        return 200, f"<GetCustomerResponse>{engine_l5_smoke.SOAP_PROBE_CUSTOMER_ID}</GetCustomerResponse>"

    monkeypatch.setattr(engine_l5_smoke, "_http_request", reject_unsafe_envelope)

    engine_l5_smoke._assert_inbound_soap_envelope_security(
        engine_l5_smoke.SOAP_PROBE_CUSTOMER_ID
    )

    assert len(requests) == 4
    assert '<!ENTITY xxe SYSTEM "file:///tmp/edgeforge-soap-xxe-sentinel.txt">' in requests[0][1]
    assert "<!ENTITY e " in requests[1][1]
    assert "&e;" in requests[1][1]
    assert len(requests[2][1].encode("utf-8")) > engine_l5_smoke.SOAP_ENVELOPE_MAX_BYTES
    assert engine_l5_smoke.SOAP_PROBE_CUSTOMER_ID in requests[3][1]


def test_engine_l5_runtime_rejects_generic_500_as_soap_hardening_success(
    monkeypatch,
) -> None:
    monkeypatch.setattr(engine_l5_smoke, "_docker_exec", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        engine_l5_smoke,
        "_http_request",
        lambda *args, **kwargs: (500, "<SOAP-ENV:Fault/>"),
    )

    with pytest.raises(AssertionError, match="expected deterministic HTTP 400"):
        engine_l5_smoke._assert_inbound_soap_envelope_security(
            engine_l5_smoke.SOAP_PROBE_CUSTOMER_ID
        )


def test_engine_l5_writes_transport_header_regression_test(tmp_path: Path) -> None:
    generated_app = tmp_path / "generated-app"
    config_path = (
        generated_app
        / "src/main/java/com/appbuilder/smoke/adapter/soap/SoapEndpointConfig.java"
    )
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "package com.appbuilder.smoke.adapter.soap;\n"
        "public class SoapEndpointConfig {}\n",
        encoding="utf-8",
    )

    test_path = engine_l5_smoke._write_soap_transport_header_regression_test(
        generated_app
    )
    source = test_path.read_text(encoding="utf-8")

    assert "extends TransportInputStream" in source
    assert 'assertEquals("\\\"urn:getCustomer\\\"", message.getSoapAction())' in source
    assert 'getHeader("Content-Type")' in source


def test_engine_l5_combined_fixture_contains_required_contract_families(tmp_path: Path) -> None:
    fixture = engine_l5_smoke._prepare_combined_edge_contract_fixture(tmp_path / "combined")

    manifest = (fixture / "app-definition.yaml").read_text(encoding="utf-8")

    assert "type: rest-json" in manifest
    assert "type: file-fixed-width" in manifest
    assert "type: file-csv" in manifest
    assert "type: xml-xsd" in manifest
    assert "type: soap-wsdl" in manifest
    assert "account-inbound-file" in manifest
    assert "account-csv-inbound-file" in manifest
    assert "account-xml-inbound" in manifest
    assert "account-xml-outbound" in manifest
    assert "customer-soap-service" in manifest
    assert "customer-sync-client" in manifest


def test_engine_l5_change_plan_entrypoint_passes_without_external_services() -> None:
    result = engine_l5_smoke.run_engine_l5_change_plan()

    assert result.status == "passed"
    assert result.name == "engine-l5-change-plan"
    assert any("dry-run plan stable" in step for step in result.steps)
    assert any("edge-contract impact surfaced" in step for step in result.steps)
    assert result.artifacts["plan_hash"]
