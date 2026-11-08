"""OpenAPI fetch helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from functools import partial
from http.client import HTTPConnection, HTTPSConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    build_opener,
)

import yaml

ALLOWED_HOSTS_ENV = "EDGEFORGE_OPENAPI_FETCH_ALLOWED_HOSTS"
ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
BLOCKED_METADATA_HOSTS = {"metadata.google.internal"}
BLOCKED_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
}
PRIVATE_SERVICE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class OpenAPIFetchPolicyError(ValueError):
    """Raised when an OpenAPI URL violates the Engine fetch policy."""


class OpenAPIFetchUnavailableError(ValueError):
    """Raised when an allowed OpenAPI host cannot be resolved or reached."""


@dataclass(frozen=True)
class _ValidatedOpenAPIURL:
    url: str
    host: str
    port: int
    addresses: tuple[IPAddress, ...]


class _NoRedirectHandler(HTTPRedirectHandler):
    """Expose redirects to the policy loop instead of following them implicitly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _connect_to_pinned_addresses(
    addresses: tuple[IPAddress, ...],
    port: int,
    timeout,
    source_address,
):
    """Connect only to the numeric addresses approved by the policy lookup."""

    last_error: OSError | None = None
    for address in addresses:
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sockaddr = (
                (str(address), port, 0, 0)
                if address.version == 6
                else (str(address), port)
            )
            sock.connect(sockaddr)
            peer = ipaddress.ip_address(str(sock.getpeername()[0]).split("%", 1)[0])
            if peer != address:
                raise OpenAPIFetchPolicyError(
                    "OpenAPI connection peer did not match the validated address."
                )
            return sock
        except OpenAPIFetchPolicyError:
            sock.close()
            raise
        except OSError as exc:
            last_error = exc
            sock.close()
    if last_error is not None:
        raise last_error
    raise OSError("OpenAPI URL had no validated connection address.")


class _PinnedHTTPConnection(HTTPConnection):
    """HTTP connection whose socket destination is fixed by policy validation."""

    def __init__(
        self,
        host,
        port=None,
        *,
        pinned_addresses: tuple[IPAddress, ...],
        **kwargs,
    ):
        super().__init__(host, port, **kwargs)
        self._pinned_addresses = pinned_addresses
        self._create_connection = self._create_pinned_connection

    def _create_pinned_connection(self, _address, timeout, source_address):
        return _connect_to_pinned_addresses(
            self._pinned_addresses,
            self.port,
            timeout,
            source_address,
        )


class _PinnedHTTPSConnection(HTTPSConnection):
    """HTTPS connection pinned to approved IPs while retaining host/SNI checks."""

    def __init__(
        self,
        host,
        port=None,
        *,
        pinned_addresses: tuple[IPAddress, ...],
        **kwargs,
    ):
        super().__init__(host, port, **kwargs)
        self._pinned_addresses = pinned_addresses
        self._create_connection = self._create_pinned_connection

    def _create_pinned_connection(self, _address, timeout, source_address):
        return _connect_to_pinned_addresses(
            self._pinned_addresses,
            self.port,
            timeout,
            source_address,
        )


class _PinnedHTTPHandler(HTTPHandler):
    def __init__(self, addresses: tuple[IPAddress, ...]) -> None:
        super().__init__()
        self._addresses = addresses

    def http_open(self, req):
        connection = partial(
            _PinnedHTTPConnection,
            pinned_addresses=self._addresses,
        )
        return self.do_open(connection, req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, addresses: tuple[IPAddress, ...]) -> None:
        super().__init__()
        self._addresses = addresses

    def https_open(self, req):
        connection = partial(
            _PinnedHTTPSConnection,
            pinned_addresses=self._addresses,
        )
        return self.do_open(
            connection,
            req,
            context=self._context,
            check_hostname=self._check_hostname,
        )


def _normalized_host(host: str) -> str:
    return host.strip().strip("[]").rstrip(".").lower()


def _allowed_hosts_from_env() -> set[str]:
    raw = os.getenv(ALLOWED_HOSTS_ENV, "")
    return {
        normalized
        for part in raw.split(",")
        if (normalized := _normalized_host(part))
    }


def _is_private_service_address(address: IPAddress) -> bool:
    return any(address in network for network in PRIVATE_SERVICE_NETWORKS)


def _is_non_bypassable_address(address: IPAddress) -> bool:
    if address in BLOCKED_METADATA_ADDRESSES:
        return True
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    ):
        return True
    return not address.is_global and not _is_private_service_address(address)


def _resolved_addresses(
    host: str,
    port: int,
) -> set[IPAddress]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OpenAPIFetchUnavailableError("OpenAPI URL host could not be resolved") from exc

    addresses: set[IPAddress] = set()
    for result in results:
        sockaddr = result[4]
        if not sockaddr:
            continue
        try:
            addresses.add(ipaddress.ip_address(str(sockaddr[0])))
        except ValueError as exc:
            raise OpenAPIFetchPolicyError(
                "OpenAPI URL host is not allowed by Engine fetch policy."
            ) from exc
    if not addresses:
        raise OpenAPIFetchUnavailableError("OpenAPI URL host could not be resolved")
    return addresses


def _validate_openapi_fetch_url(url: str) -> _ValidatedOpenAPIURL:
    candidate = (url or "").strip()
    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise OpenAPIFetchPolicyError("OpenAPI URL must use http or https.")
    if not parsed.hostname:
        raise OpenAPIFetchPolicyError("OpenAPI URL must include a hostname.")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise OpenAPIFetchPolicyError("OpenAPI URL port is invalid.") from exc

    host = _normalized_host(parsed.hostname)
    allowed_hosts = _allowed_hosts_from_env()
    if host in BLOCKED_METADATA_HOSTS:
        raise OpenAPIFetchPolicyError(
            "OpenAPI URL host is not allowed by Engine fetch policy."
        )

    ip_host = host.split("%25", 1)[0].split("%", 1)[0]
    try:
        address = ipaddress.ip_address(ip_host)
    except ValueError:
        if ":" in host:
            raise OpenAPIFetchPolicyError(
                "OpenAPI URL host is not allowed by Engine fetch policy."
            ) from None
        addresses = _resolved_addresses(host, port)
    else:
        addresses = {address}

    if any(_is_non_bypassable_address(address) for address in addresses):
        raise OpenAPIFetchPolicyError(
            "OpenAPI URL host is not allowed by Engine fetch policy."
        )
    if host not in allowed_hosts and any(
        _is_private_service_address(address) for address in addresses
    ):
        raise OpenAPIFetchPolicyError(
            "OpenAPI URL host is not allowed by Engine fetch policy."
        )
    ordered_addresses = tuple(
        sorted(addresses, key=lambda item: (item.version, int(item)))
    )
    return _ValidatedOpenAPIURL(
        url=candidate,
        host=host,
        port=port,
        addresses=ordered_addresses,
    )


def _build_pinned_opener(target: _ValidatedOpenAPIURL):
    return build_opener(
        ProxyHandler({}),
        _NoRedirectHandler(),
        _PinnedHTTPHandler(target.addresses),
        _PinnedHTTPSHandler(target.addresses),
    )


def _open_url(target: _ValidatedOpenAPIURL, timeout: int):
    opener = _build_pinned_opener(target)
    return opener.open(target.url, timeout=timeout)


def _redirect_target(
    current_target: _ValidatedOpenAPIURL,
    response,
) -> _ValidatedOpenAPIURL:
    location = response.headers.get("Location")
    if not location:
        raise OpenAPIFetchPolicyError(
            "OpenAPI URL redirect response did not include a target."
        )
    redirect_url = urljoin(current_target.url, location)
    try:
        return _validate_openapi_fetch_url(redirect_url)
    except OpenAPIFetchPolicyError as exc:
        raise OpenAPIFetchPolicyError(
            "OpenAPI URL redirect target is not allowed."
        ) from exc


def _read_bounded_response(response) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > MAX_RESPONSE_BYTES:
            raise OpenAPIFetchPolicyError(
                f"OpenAPI URL response exceeded the maximum response size of "
                f"{MAX_RESPONSE_BYTES} bytes."
            )

    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise OpenAPIFetchPolicyError(
            f"OpenAPI URL response exceeded the maximum response size of "
            f"{MAX_RESPONSE_BYTES} bytes."
        )
    return payload


def fetch_openapi_spec(url: str) -> dict:
    """Fetch and parse an OpenAPI spec under the Engine SSRF policy.

    Policy violations raise ``OpenAPIFetchPolicyError``. Availability failures
    remain ordinary ``ValueError`` instances so callers with reviewed local
    samples can retain their existing offline fallback.
    """

    current_target = _validate_openapi_fetch_url(url)
    response = None
    for _redirect_count in range(MAX_REDIRECTS + 1):
        try:
            response = _open_url(
                current_target,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except HTTPError as exc:
            if exc.code not in REDIRECT_STATUS_CODES:
                raise ValueError(
                    f"Failed to fetch OpenAPI spec from {url}: HTTP {exc.code}"
                ) from exc
            response = exc
        except URLError as exc:
            raise ValueError(
                f"Failed to fetch OpenAPI spec from {url}: {type(exc).__name__}"
            ) from exc
        except OSError as exc:
            raise ValueError(
                f"Failed to fetch OpenAPI spec from {url}: {type(exc).__name__}"
            ) from exc

        with response:
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
            if status in REDIRECT_STATUS_CODES:
                current_target = _redirect_target(current_target, response)
                continue
            raw_payload = _read_bounded_response(response)
            payload = raw_payload.decode(
                response.headers.get_content_charset("utf-8"),
                errors="replace",
            )
            break
    else:
        raise OpenAPIFetchPolicyError("OpenAPI URL exceeded redirect limit.")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(payload)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Failed to fetch OpenAPI spec from {url}: response was neither valid JSON nor YAML"
            ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Failed to fetch OpenAPI spec from {url}: response did not contain a mapping"
        )
    return parsed
