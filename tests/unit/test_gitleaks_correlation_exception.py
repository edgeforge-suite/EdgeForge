"""Keep the approved proof-value exception limited to exact files and values."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = "docs/handover-evidence/kafka-lz4-default/2026-10-14/receipt.json"
FIXTURE = "tests/unit/test_default_lz4_evidence.py"


def exception_patterns():
    config = (ROOT / ".gitleaks.toml").read_text()
    # Inspect only the appended rule; the real pinned scanner validates TOML
    # and default-rule inheritance in the recorded CLI negative controls.
    inherited, rule = config.split("[[rules]]")
    assert "useDefault = true" in inherited
    assert "'''unique/idempotency'''" in inherited
    assert 'id = "generic-api-key"' in rule
    assert rule.count("[[rules.allowlists]]") == 1
    assert 'condition = "AND"' in rule
    assert 'regexTarget = "secret"' in rule
    assert "stopwords" not in rule
    patterns = re.findall(r"'''([^']+)'''", rule)
    assert len(patterns) == 2
    return tuple(re.compile(pattern) for pattern in patterns)


def proof_values():
    receipt = json.loads((ROOT / RECEIPT).read_text())
    observed = {case["observation"]["roundtrip"]["key"] for case in receipt["cases"]}
    assert len(observed) == 2
    fixture = (ROOT / FIXTURE).read_text()
    observed.add(re.search(r'^    key = "([^"]+)"$', fixture, re.MULTILINE)[1])
    return observed


@pytest.mark.parametrize("path", [RECEIPT, FIXTURE])
def test_only_exact_approved_files_and_values_match(path):
    path_pattern, value_pattern = exception_patterns()
    assert path_pattern.fullmatch(path)
    for value in proof_values():
        assert value_pattern.fullmatch(value)
        assert not value_pattern.fullmatch(value + "-not-approved")
        assert not value_pattern.fullmatch("prefix-" + value)
    assert not value_pattern.fullmatch("default-lz4-another-correlation")


@pytest.mark.parametrize("path", [
    "receipt.json", "tests/unit/test_default_lz4_evidence.py.backup",
    "other/tests/unit/test_default_lz4_evidence.py",
    "docs/handover-evidence/kafka-lz4-default/2026-10-15/receipt.json",
    "docs/handover-evidence/kafka-lz4-default/2026-10-14/receiptXjson",
])
def test_nearby_files_are_not_exempt(path):
    path_pattern, _ = exception_patterns()
    assert not path_pattern.fullmatch(path)
