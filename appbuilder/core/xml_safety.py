"""Bounded, DTD-free parsing for untrusted design-time XML contract files.

Design-time contract files (XSD/WSDL) are author-supplied, but a manifest
package can travel between hands, so the parsers that read them enforce
explicit bounds rather than trusting the input.

`xml.etree.ElementTree` never fetches external entities or external DTDs, so
document-retrieval XXE is already out of reach. The residual exposure is
*internal* entity expansion ("billion laughs") plus unbounded document size and
nesting depth, none of which ElementTree bounds on its own.

The controls here run as a pre-pass over the raw bytes using `xml.parsers.expat`
directly. Keeping the policy separate from the tree builder lets every caller
validate the exact bytes it parses or copies, and lets one budget cover an
entire include graph. The pre-pass rejects any DTD outright, which forecloses
entity declarations — and therefore entity expansion — before a single entity
is expanded.

Bounds are rejection-only: input that is accepted parses to exactly the tree it
did before, so generated output stays deterministic.
"""

from __future__ import annotations

import os
import xml.parsers.expat as expat
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_BYTES_ENV = "EDGEFORGE_XML_MAX_BYTES"
MAX_DEPTH_ENV = "EDGEFORGE_XML_MAX_DEPTH"
MAX_TOTAL_BYTES_ENV = "EDGEFORGE_XML_MAX_TOTAL_BYTES"
MAX_DOCUMENTS_ENV = "EDGEFORGE_XML_MAX_DOCUMENTS"

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_DEPTH = 200
DEFAULT_MAX_TOTAL_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_DOCUMENTS = 100


class XmlSafetyError(ValueError):
    """Raised when untrusted design-time XML violates a parser bound."""


@dataclass
class XmlParseBudget:
    """Aggregate allowance shared by every document in one contract load."""

    max_total_bytes: int = field(
        default_factory=lambda: _bound(MAX_TOTAL_BYTES_ENV, DEFAULT_MAX_TOTAL_BYTES)
    )
    max_documents: int = field(
        default_factory=lambda: _bound(MAX_DOCUMENTS_ENV, DEFAULT_MAX_DOCUMENTS)
    )
    total_bytes: int = 0
    document_count: int = 0
    _paths: set[Path] = field(default_factory=set, repr=False)

    def consume(self, path: Path, size: int, *, purpose: str) -> None:
        """Charge one distinct file to this load before parsing it."""

        resolved = path.resolve()
        if resolved in self._paths:
            return
        next_document_count = self.document_count + 1
        if next_document_count > self.max_documents:
            raise XmlSafetyError(
                f"{purpose} exceeds the {self.max_documents}-document aggregate XML "
                f"parse limit (override with {MAX_DOCUMENTS_ENV})."
            )
        next_total_bytes = self.total_bytes + size
        if next_total_bytes > self.max_total_bytes:
            raise XmlSafetyError(
                f"{purpose} exceeds the {self.max_total_bytes}-byte aggregate XML "
                f"parse limit (override with {MAX_TOTAL_BYTES_ENV})."
            )
        self._paths.add(resolved)
        self.document_count = next_document_count
        self.total_bytes = next_total_bytes


def read_untrusted_xml_bytes(
    path: Path,
    *,
    purpose: str,
    budget: XmlParseBudget | None = None,
) -> bytes:
    """Read and validate the exact XML bytes a caller will consume or copy."""

    data = _read_bounded_bytes(path, purpose=purpose)
    (budget or XmlParseBudget()).consume(path, len(data), purpose=purpose)
    _enforce_document_bounds(data, purpose=purpose)
    return data


def parse_untrusted_xml(
    path: Path,
    *,
    purpose: str,
    budget: XmlParseBudget | None = None,
) -> ET.Element:
    """Parse an untrusted XML file under explicit bounds and return its root."""

    data = read_untrusted_xml_bytes(path, purpose=purpose, budget=budget)
    return ET.fromstring(data)


def parse_untrusted_xml_with_namespaces(
    path: Path,
    *,
    purpose: str,
    budget: XmlParseBudget | None = None,
) -> tuple[ET.Element, list[tuple[str, str]]]:
    """Parse an untrusted XML file, returning its root and prefix/URI pairs.

    Namespace pairs are returned in document order so callers keep their own
    first-wins / last-wins precedence instead of inheriting one from here.
    """

    data = read_untrusted_xml_bytes(path, purpose=purpose, budget=budget)
    prefixes = [
        (prefix or "", uri)
        for _event, (prefix, uri) in ET.iterparse(BytesIO(data), events=("start-ns",))
    ]
    return ET.fromstring(data), prefixes


def _read_bounded_bytes(path: Path, *, purpose: str) -> bytes:
    """Read a file, refusing anything past the configured byte ceiling."""

    max_bytes = _bound(MAX_BYTES_ENV, DEFAULT_MAX_BYTES)
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise XmlSafetyError(
            f"{purpose} exceeds the {max_bytes}-byte XML parse limit "
            f"(override with {MAX_BYTES_ENV})."
        )
    return data


def _enforce_document_bounds(data: bytes, *, purpose: str) -> None:
    """Reject DTDs, entity declarations, external refs, and over-deep nesting.

    Malformed input is left alone deliberately: ElementTree raises the canonical
    `ParseError` for it, and callers already translate that into their own
    contract-specific message.
    """

    max_depth = _bound(MAX_DEPTH_ENV, DEFAULT_MAX_DEPTH)
    parser = expat.ParserCreate()
    depth = 0

    def _reject_doctype(name: str, system_id, public_id, has_internal_subset) -> None:
        raise XmlSafetyError(
            f"{purpose} declares an XML document type (DTD), which is not "
            "supported in design-time contract files."
        )

    def _reject_entity_decl(*_args: object) -> None:
        raise XmlSafetyError(
            f"{purpose} declares an XML entity, which is not supported in "
            "design-time contract files."
        )

    def _reject_external_ref(*_args: object) -> None:
        raise XmlSafetyError(
            f"{purpose} references an external XML entity, which is not "
            "supported in design-time contract files."
        )

    def _enter_element(_name: str, _attrs: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > max_depth:
            raise XmlSafetyError(
                f"{purpose} nests XML elements deeper than the {max_depth}-level "
                f"limit (override with {MAX_DEPTH_ENV})."
            )

    def _exit_element(_name: str) -> None:
        nonlocal depth
        depth -= 1

    parser.StartDoctypeDeclHandler = _reject_doctype
    parser.EntityDeclHandler = _reject_entity_decl
    parser.UnparsedEntityDeclHandler = _reject_entity_decl
    parser.ExternalEntityRefHandler = _reject_external_ref
    parser.StartElementHandler = _enter_element
    parser.EndElementHandler = _exit_element

    try:
        parser.Parse(data, True)
    except expat.ExpatError:
        return


def _bound(env_var: str, default: int) -> int:
    """Read a positive-integer bound override, failing fast on junk values."""

    raw = os.environ.get(env_var)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise XmlSafetyError(f"{env_var} must be a positive integer, got '{raw}'.") from exc
    if value <= 0:
        raise XmlSafetyError(f"{env_var} must be a positive integer, got '{raw}'.")
    return value
