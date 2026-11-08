import ipaddress
import json
import shutil
import socket
import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler

import pytest
import yaml

from appbuilder.cli import main
from appbuilder.ingestion.openapi_fetcher import (
    MAX_RESPONSE_BYTES,
    OpenAPIFetchPolicyError,
    OpenAPIFetchUnavailableError,
    _build_pinned_opener,
    _connect_to_pinned_addresses,
    _PinnedHTTPConnection,
    _PinnedHTTPSConnection,
    _validate_openapi_fetch_url,
    fetch_openapi_spec,
)
from appbuilder.metadata.translation import build_metadata_project


class _FakeHeaders:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = {key.lower(): value for key, value in (values or {}).items()}

    def get(self, name: str, default: str | None = None) -> str | None:
        return self._values.get(name.lower(), default)

    def get_content_charset(self, default: str = "utf-8") -> str:
        return default


class _FakeResponse:
    def __init__(
        self,
        body: str,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body = body.encode("utf-8")
        self.status = status
        self.headers = _FakeHeaders(headers)

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSocket:
    def setsockopt(self, *args) -> None:
        return None


class _FakePeerSocket:
    def __init__(self, peer: str) -> None:
        self.peer = peer
        self.closed = False

    def settimeout(self, timeout) -> None:
        return None

    def connect(self, sockaddr) -> None:
        return None

    def getpeername(self):
        return self.peer, 443

    def close(self) -> None:
        self.closed = True


class _FakeSSLContext:
    verify_mode = ssl.CERT_REQUIRED
    check_hostname = True
    post_handshake_auth = False

    def __init__(self, wrapped_socket: object) -> None:
        self.wrapped_socket = wrapped_socket
        self.server_hostname: str | None = None

    def wrap_socket(self, sock, *, server_hostname: str):
        self.server_hostname = server_hostname
        return self.wrapped_socket


def _allow_public_host(monkeypatch) -> None:
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._resolved_addresses",
        lambda host, port: {ipaddress.ip_address("93.184.216.34")},
    )


def test_fetch_openapi_spec_json(monkeypatch) -> None:
    expected = {"openapi": "3.0.0", "info": {"title": "Test API"}}
    _allow_public_host(monkeypatch)

    def fake_open_url(target, timeout: int):
        assert target.url == "https://api.example.com/v3/api-docs"
        assert target.addresses == (ipaddress.ip_address("93.184.216.34"),)
        assert timeout == 10
        return _FakeResponse(json.dumps(expected))

    monkeypatch.setattr("appbuilder.ingestion.openapi_fetcher._open_url", fake_open_url)

    assert fetch_openapi_spec("https://api.example.com/v3/api-docs") == expected


def test_fetch_openapi_spec_rejects_file_scheme_before_open(monkeypatch) -> None:
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        lambda *args, **kwargs: pytest.fail("disallowed scheme reached the opener"),
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="must use http or https"):
        fetch_openapi_spec("file:///etc/passwd")


def test_fetch_openapi_spec_rejects_cloud_metadata_ip_before_open(monkeypatch) -> None:
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        lambda *args, **kwargs: pytest.fail("metadata IP reached the opener"),
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="host is not allowed"):
        fetch_openapi_spec("http://169.254.169.254/latest/meta-data")


@pytest.mark.parametrize(
    "url,allowed_host",
    [
        ("http://169.254.169.254/latest/meta-data", "169.254.169.254"),
        ("http://metadata.google.internal/computeMetadata/v1/", "metadata.google.internal"),
    ],
)
def test_fetch_openapi_spec_never_allows_cloud_metadata_exception(
    monkeypatch,
    url: str,
    allowed_host: str,
) -> None:
    monkeypatch.setenv("EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS", allowed_host)
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        lambda *args, **kwargs: pytest.fail("allowlisted metadata target reached the opener"),
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="host is not allowed"):
        fetch_openapi_spec(url)


def test_cli_assess_rejects_disallowed_openapi_target(capsys) -> None:
    exit_code = main(["assess", "--swagger", "file:///etc/passwd"])

    assert exit_code == 1
    assert "OpenAPI URL must use http or https" in capsys.readouterr().err


def test_fetch_openapi_spec_rejects_hostname_resolving_to_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._resolved_addresses",
        lambda host, port: {ipaddress.ip_address("10.20.30.40")},
    )
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        lambda *args, **kwargs: pytest.fail("private host reached the opener"),
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="host is not allowed"):
        fetch_openapi_spec("https://api.internal.example/openapi.json")


def test_fetch_openapi_spec_rejects_redirect_to_internal_target(monkeypatch) -> None:
    _allow_public_host(monkeypatch)
    opened: list[str] = []

    def fake_open_url(target, timeout: int):
        opened.append(target.url)
        return _FakeResponse(
            "",
            status=302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    monkeypatch.setattr("appbuilder.ingestion.openapi_fetcher._open_url", fake_open_url)

    with pytest.raises(OpenAPIFetchPolicyError, match="redirect target is not allowed"):
        fetch_openapi_spec("https://api.example.com/openapi.json")

    assert opened == ["https://api.example.com/openapi.json"]


def test_fetch_openapi_spec_rejects_redirect_to_allowlisted_metadata_target(
    monkeypatch,
) -> None:
    _allow_public_host(monkeypatch)
    monkeypatch.setenv("EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS", "169.254.169.254")
    opened: list[str] = []

    def fake_open_url(target, timeout: int):
        opened.append(target.url)
        return _FakeResponse(
            "",
            status=302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    monkeypatch.setattr("appbuilder.ingestion.openapi_fetcher._open_url", fake_open_url)

    with pytest.raises(OpenAPIFetchPolicyError, match="redirect target is not allowed"):
        fetch_openapi_spec("https://api.example.com/openapi.json")

    assert opened == ["https://api.example.com/openapi.json"]


def test_validated_dns_address_is_bound_to_http_connection(monkeypatch) -> None:
    public_address = ipaddress.ip_address("93.184.216.34")
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._resolved_addresses",
        lambda host, port: {public_address},
    )
    target = _validate_openapi_fetch_url("http://api.example.com/openapi.json")
    connected: dict[str, object] = {}
    sentinel_socket = object()

    def fake_connect(addresses, port, timeout, source_address):
        connected.update(
            addresses=addresses,
            port=port,
            timeout=timeout,
            source_address=source_address,
        )
        return sentinel_socket

    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._connect_to_pinned_addresses",
        fake_connect,
    )
    connection = _PinnedHTTPConnection(
        target.host,
        target.port,
        pinned_addresses=target.addresses,
    )

    result = connection._create_connection(
        ("10.20.30.40", target.port),
        10,
        None,
    )

    assert result is sentinel_socket
    assert connected["addresses"] == (public_address,)
    assert connected["port"] == 80


def test_pinned_connection_rejects_unexpected_actual_peer(monkeypatch) -> None:
    public_address = ipaddress.ip_address("93.184.216.34")
    fake_socket = _FakePeerSocket("10.20.30.40")
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher.socket.socket",
        lambda *args, **kwargs: fake_socket,
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="peer did not match"):
        _connect_to_pinned_addresses((public_address,), 443, 10, None)

    assert fake_socket.closed is True


def test_pinned_https_connection_keeps_original_host_for_sni(monkeypatch) -> None:
    public_address = ipaddress.ip_address("93.184.216.34")
    raw_socket = _FakeSocket()
    wrapped_socket = object()
    context = _FakeSSLContext(wrapped_socket)
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._connect_to_pinned_addresses",
        lambda *args, **kwargs: raw_socket,
    )
    connection = _PinnedHTTPSConnection(
        "api.example.com",
        443,
        context=context,
        pinned_addresses=(public_address,),
    )

    connection.connect()

    assert connection.sock is wrapped_socket
    assert context.server_hostname == "api.example.com"


def test_pinned_opener_disables_ambient_proxies(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal.example:8080")
    target = _validate_openapi_fetch_url("https://93.184.216.34/openapi.json")
    captured_handlers: list[object] = []
    sentinel_opener = object()

    def fake_build_opener(*handlers):
        captured_handlers.extend(handlers)
        return sentinel_opener

    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher.build_opener",
        fake_build_opener,
    )

    opener = _build_pinned_opener(target)
    proxy_handlers = [
        handler for handler in captured_handlers if isinstance(handler, ProxyHandler)
    ]

    assert opener is sentinel_opener
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}


def test_fetch_openapi_spec_rejects_oversize_response(monkeypatch) -> None:
    _allow_public_host(monkeypatch)
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        lambda url, timeout: _FakeResponse("x" * (MAX_RESPONSE_BYTES + 1)),
    )

    with pytest.raises(OpenAPIFetchPolicyError, match="maximum response size"):
        fetch_openapi_spec("https://api.example.com/openapi.json")


def test_fetch_openapi_spec_allows_explicitly_allowlisted_private_host(monkeypatch) -> None:
    expected = {"openapi": "3.0.0"}
    monkeypatch.setenv("EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS", "api.internal.example")
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._resolved_addresses",
        lambda *args: {ipaddress.ip_address("10.20.30.40")},
    )

    def fake_open_url(target, timeout: int):
        assert target.addresses == (ipaddress.ip_address("10.20.30.40"),)
        return _FakeResponse(json.dumps(expected))

    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher._open_url",
        fake_open_url,
    )

    assert fetch_openapi_spec("https://api.internal.example/openapi.json") == expected


def test_fetch_openapi_spec_invalid_url(monkeypatch) -> None:
    _allow_public_host(monkeypatch)

    def fake_open_url(target, timeout: int):
        raise URLError("unreachable")

    monkeypatch.setattr("appbuilder.ingestion.openapi_fetcher._open_url", fake_open_url)

    with pytest.raises(
        ValueError,
        match=r"Failed to fetch OpenAPI spec from https://api.example.com/v3/api-docs: URLError",
    ):
        fetch_openapi_spec("https://api.example.com/v3/api-docs")


def test_metadata_translation_does_not_fall_back_after_fetch_policy_rejection(
    monkeypatch,
) -> None:
    fixture = Path("examples/input-projects/xyz-accounts-modernization/app-definition.yaml")

    def reject_fetch(url: str) -> dict:
        raise OpenAPIFetchPolicyError("OpenAPI URL host is not allowed by Engine fetch policy.")

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", reject_fetch)

    with pytest.raises(OpenAPIFetchPolicyError, match="host is not allowed"):
        build_metadata_project(fixture)


def test_metadata_translation_falls_back_to_xyz_samples_when_dns_is_unavailable(
    monkeypatch,
) -> None:
    fixture = Path("examples/input-projects/xyz-accounts-modernization/app-definition.yaml")

    def fail_dns_lookup(*args, **kwargs):
        raise socket.gaierror("name or service not known")

    # The suite-wide network stub raises a generic ValueError. Restore the real
    # fetcher here so this test protects the production exception boundary.
    monkeypatch.setattr(
        "appbuilder.metadata.translation.fetch_openapi_spec",
        fetch_openapi_spec,
    )
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher.socket.getaddrinfo",
        fail_dns_lookup,
    )

    metadata = build_metadata_project(fixture)

    assert [entity.name for entity in metadata.entities] == ["Account"]
    assert metadata.contracts[0].ingestion_notes == [
        "spec_url fetch failed: OpenAPI URL host could not be resolved. "
        "Falling back to sample ingestion."
    ]


def test_fetch_openapi_spec_distinguishes_dns_unavailability_from_policy_denial(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "appbuilder.ingestion.openapi_fetcher.socket.getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("unresolved")),
    )

    with pytest.raises(OpenAPIFetchUnavailableError, match="could not be resolved"):
        fetch_openapi_spec("https://unresolved.example/openapi.json")


def test_passthrough_translation_rejects_fetch_policy_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "country-router"
    shutil.copytree(Path("examples/input-projects/country-router"), fixture)
    manifest_path = fixture / "app-definition.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    upstream = manifest["upstream_interfaces"][0]
    upstream.pop("spec")
    upstream["spec_url"] = "http://169.254.169.254/latest/meta-data"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    def reject_fetch(url: str) -> dict:
        raise OpenAPIFetchPolicyError("OpenAPI URL host is not allowed by Engine fetch policy.")

    monkeypatch.setattr("appbuilder.metadata.translation.fetch_openapi_spec", reject_fetch)

    with pytest.raises(ValueError, match="host is not allowed"):
        build_metadata_project(manifest_path)
