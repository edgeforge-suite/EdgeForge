"""Derive bounded proof, vendor, or replay records for compact publication.

This is a derived record, not an original runtime receipt or a new proof run.
Original byte hashes remain binding; no scanner exceptions or risk acceptance.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

MAX_SOURCE_BYTES = 32 * 1024 * 1024
VENDOR_MEMBER = "reconciliation/residual-vendor-current.original.json.gz"
REPLAY_MEMBER = "reconciliation/publication-replay.original.json.gz"
JACKSON = "GHSA-5gvw-p9qm-jgwh"
LZ4 = {
    "GHSA-343h-94h5-c4wr": ("<= 1.11.3", "1.11.4"),
    "GHSA-4v53-57pg-c464": ("<= 1.11.1", "1.11.2"),
    "GHSA-6cx8-rjf8-pr8g": ("<= 1.11.1", "1.11.2"),
    "GHSA-gm45-99xc-r7wv": ("<= 1.11.3", "1.11.4"),
    "GHSA-mcr4-qmvw-px4g": ("<= 1.11.3", "1.11.4"),
}
BODIES = ("global_advisory", "repository_advisory", "osv_advisory")
STAGES = {"generated-build-stage", "generated-final-image"}
CONCLUSION = "verified-installed-version-not-in-affected-range"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def _digest(value):
    return _sha(_canonical(value))


def _hash(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "invalid SHA256")
    return value


def _text(value):
    require(isinstance(value, str) and value.strip(), "required text missing")
    return value


def _keys(value, required, optional=()):
    require(isinstance(value, dict), "object required")
    require(set(required) <= value.keys() <= set(required) | set(optional), "fields differ")


def _list(value, nonempty=False):
    require(isinstance(value, list) and (value or not nonempty), "required list missing")
    return value


def _member(value):
    _text(value)
    path = PurePosixPath(value)
    require(
        not path.is_absolute() and str(path) == value and ".." not in path.parts
        and not re.search(r"[\\\x00-\x20:]", value),
        "unsafe archive member",
    )
    return value


def _date(value):
    _text(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "timezone required")
    return value


def _url(value):
    _text(value)
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and not re.search(r"[\s<>]", value), "unsafe source URL")
    return value


def _version(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+(?:[.][0-9A-Za-z]+)*(?:[-+][0-9A-Za-z.-]+)?", value),
            "invalid version")
    return value


def _numeric_release(value):
    """Compare only bounded numeric releases, not general Maven version qualifiers."""
    component = r"(?:0|[1-9][0-9]{0,8})"
    require(isinstance(value, str) and len(value) <= 79
            and re.fullmatch(component + r"(?:\." + component + r"){0,7}", value),
            "unsupported OSV release comparison")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (8 - len(parts))


def _osv_intervals(events):
    """Validate finite, ordered intervals; last_affected alone includes its endpoint."""
    _list(events, True)
    require(len(events) >= 2 and len(events) % 2 == 0, "incomplete OSV range")
    intervals = []
    for index in range(0, len(events), 2):
        introduced, terminal = events[index:index + 2]
        _keys(introduced, ("introduced",))
        require(isinstance(terminal, dict) and len(terminal) == 1
                and set(terminal) <= {"fixed", "last_affected", "limit"},
                "contradictory OSV event order")
        start = _numeric_release(introduced["introduced"])
        end = _numeric_release(next(iter(terminal.values())))
        inclusive = "last_affected" in terminal
        require(start < end or (inclusive and start == end), "empty or inverted OSV interval")
        if intervals:
            previous_end, previous_inclusive = intervals[-1][1:]
            require(start > previous_end or (start == previous_end and not previous_inclusive),
                    "unordered or overlapping OSV intervals")
        intervals.append((start, end, inclusive))
    return intervals


def _range(value):
    _text(value)
    bounds = []
    for part in value.split(","):
        match = re.fullmatch(r"\s*(<=|>=|<|>|=)\s*(\S+)\s*", part)
        require(match is not None, "invalid affected range")
        _version(match[2])
        if re.fullmatch(r"\d+(?:\.\d+)*", match[2]):
            bounds.append((match[1], tuple(int(x) for x in match[2].split("."))))
    for lower, low in bounds:
        for upper, high in bounds:
            if lower in (">", ">=", "=") and upper in ("<", "<=", "="):
                width = max(len(low), len(high))
                left, right = low + (0,) * (width - len(low)), high + (0,) * (width - len(high))
                require(left < right or (left == right and lower != ">" and upper != "<"), "inverted affected range")
    return value


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, "nonfinite JSON number"))


def _source(raw, expected_sha256, source_member, role):
    _hash(expected_sha256)
    require(isinstance(raw, bytes) and len(raw) <= MAX_SOURCE_BYTES, "source size/type differs")
    require(_sha(raw) == expected_sha256, "source hash mismatch")
    require(_member(source_member) == role, "wrong archive source role")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        decoded = stream.read(MAX_SOURCE_BYTES + 1)
    require(len(decoded) <= MAX_SOURCE_BYTES, "decompressed source too large")
    value = _decode(decoded)
    require(isinstance(value, dict), "source object required")
    return value, {"archive_member": source_member, "gzip_sha256": _sha(raw),
                   "json_sha256": _sha(decoded)}


def _safety(value):
    if isinstance(value, str):
        require(not re.search(r"(?:/" r"Users/|/home/|/private/(?:tmp|var)/|/var/folders/|"
                              r"[A-Za-z]:\\|<host-\d+>/Documents/|\x00)", value),
                "private host path in projection")
    elif isinstance(value, dict):
        for key, item in value.items():
            _text(key)
            _safety(key)
            _safety(item)
    elif isinstance(value, list):
        for item in value:
            _safety(item)
    else:
        require(value is None or type(value) in (bool, int, float), "invalid JSON value")


def _package(value):
    require(isinstance(value, dict), "package required")
    result = {k: value[k] for k in ("ecosystem", "name", "purl") if k in value}
    require(result.get("ecosystem") in ("maven", "Maven"), "unsupported ecosystem")
    require(isinstance(result.get("name"), str)
            and re.fullmatch(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+", result["name"]),
            "invalid package coordinate")
    if "purl" in result:
        require(result["purl"] == "pkg:maven/" + result["name"].replace(":", "/"),
                "package purl differs")
    return result


def _identity(value):
    require(isinstance(value, dict), "attribution identity required")
    result = {k: value[k] for k in ("login", "html_url", "type") if k in value}
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", _text(result.get("login"))),
            "invalid attribution login")
    _url(result.get("html_url"))
    if "type" in result:
        require(result["type"] in ("User", "Organization", "Bot"), "invalid identity type")
    return result


def _body_facts(body, role, identifier):
    """Select only typed leaves, never arbitrary vendor-provided nested subtrees."""
    require(isinstance(body, dict), "advisory body required")
    osv = role == "osv_advisory"
    identity = "id" if osv else "ghsa_id"
    require(body.get(identity) == identifier, "advisory identity differs")
    result = {identity: identifier}
    dates = ("published", "modified") if osv else ("published_at", "updated_at")
    for key in dates:
        result[key] = _date(body.get(key))
    for key in ("withdrawn_at", "github_reviewed_at", "nvd_published_at", "created_at", "closed_at"):
        if key in body:
            result[key] = None if body[key] is None else _date(body[key])
    if osv:
        result["aliases"] = [_text(x) for x in _list(body.get("aliases"), True)]
        require(all(re.fullmatch(r"(?:CVE-\d{4}-\d+|GHSA-[a-z0-9-]+)", x)
                    for x in result["aliases"]), "invalid advisory alias")
        result["references"] = []
        for reference in _list(body.get("references"), True):
            require(isinstance(reference, dict), "reference required")
            require(reference.get("type") in ("ADVISORY", "ARTICLE", "REPORT", "FIX", "PACKAGE", "WEB", "EVIDENCE"),
                    "invalid reference type")
            result["references"].append({"type": reference["type"], "url": _url(reference.get("url"))})
        result["affected"] = []
        for entry in _list(body.get("affected"), True):
            require(isinstance(entry, dict), "affected package required")
            affected = {"package": _package(entry.get("package")), "ranges": []}
            for span in _list(entry.get("ranges"), True):
                require(isinstance(span, dict) and span.get("type") == "ECOSYSTEM", "unsupported OSV range")
                events = []
                for event in _list(span.get("events"), True):
                    require(isinstance(event, dict) and len(event) == 1
                            and set(event) <= {"introduced", "fixed", "last_affected", "limit"}, "invalid OSV event")
                    events.append({k: _version(v) for k, v in event.items()})
                _osv_intervals(events)
                affected["ranges"].append({"type": span["type"], "events": events})
            if "versions" in entry:
                affected["versions"] = [_version(x) for x in _list(entry["versions"])]
            if "database_specific" in entry:
                database = entry["database_specific"]
                require(isinstance(database, dict), "OSV package database facts required")
                facts = {}
                if "source" in database:
                    facts["source"] = _url(database["source"])
                if "last_known_affected_version_range" in database:
                    facts["last_known_affected_version_range"] = _range(database["last_known_affected_version_range"])
                affected["database_specific"] = facts
            result["affected"].append(affected)
    else:
        result["cve_id"] = body.get("cve_id")
        require(isinstance(result["cve_id"], str) and re.fullmatch(r"CVE-\d{4}-\d+", result["cve_id"]),
                "CVE identity required")
        result["identifiers"] = []
        for item in _list(body.get("identifiers"), True):
            require(isinstance(item, dict) and item.get("type") in ("GHSA", "CVE"), "invalid advisory identifier")
            require(item.get("value") == (identifier if item["type"] == "GHSA" else result["cve_id"]),
                    "contradictory advisory identity")
            result["identifiers"].append({"type": item["type"], "value": item["value"]})
        require({x["type"] for x in result["identifiers"]} == {"GHSA", "CVE"}, "missing identifiers")
        for key in ("url", "html_url"):
            result[key] = _url(body.get(key))
        for key in ("repository_advisory_url", "source_code_location"):
            if key in body and body[key] is not None:
                result[key] = _url(body[key])
        if "references" in body:
            result["references"] = [_url(x) for x in _list(body["references"])]
        result["vulnerabilities"] = []
        patch = "patched_versions" if role == "repository_advisory" else "first_patched_version"
        for item in _list(body.get("vulnerabilities"), True):
            require(isinstance(item, dict) and patch in item, "patch fact missing")
            result["vulnerabilities"].append({
                "package": _package(item.get("package")),
                "vulnerable_version_range": _range(item.get("vulnerable_version_range")),
                patch: item[patch] if item[patch] in (None, "") else _version(item[patch]),
            })
        for key in ("author", "publisher"):
            if key in body:
                result[key] = None if body[key] is None else _identity(body[key])
        if "credits" in body:
            result["credits"] = []
            for entry in _list(body["credits"]):
                require(isinstance(entry, dict), "credit required")
                # Global credits wrap a user; repository credits are user identities.
                if "user" in entry:
                    credit = {"user": _identity(entry["user"])}
                    if "type" in entry:
                        require(re.fullmatch(r"[a-z_]{1,60}", _text(entry["type"])), "invalid credit role")
                        credit["type"] = entry["type"]
                else:
                    credit = {"login": _text(entry.get("login")), "type": _text(entry.get("type"))}
                    require(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", credit["login"])
                            and re.fullmatch(r"[a-z_]{1,60}", credit["type"]), "invalid credit identity")
                result["credits"].append(credit)
    return result


def _reference(value):
    _keys(value, ("root", "member", "sha256"))
    require(value["root"] in ("current", "plan", "policy"), "unknown evidence root")
    _member(value["member"])
    _hash(value["sha256"])


def _artifact(value):
    require(isinstance(value, dict), "physical artifact required")
    for key in ("name", "version", "purl", "type"):
        _text(value.get(key))
    _version(value["version"])
    require(value["purl"].startswith("pkg:maven/") and value["type"] == "java-archive"
            and value["purl"].endswith("/" + value["name"] + "@" + value["version"]), "artifact identity differs")
    for entry in _list(value.get("physical_hashes"), True):
        require(isinstance(entry, dict) and set(entry) in ({"member", "sha256"}, {"path", "sha256"}),
                "physical hash binding differs")
        if "member" in entry:
            _member(entry["member"])
        else:
            _text(entry["path"])
        _hash(entry["sha256"])
    for entry in _list(value.get("locations"), True):
        require(isinstance(entry, dict), "physical location required")
        _text(entry.get("path"))


def _vendor_rows(value):
    """Validate the bounded six-row record without changing any dispositions."""
    _keys(value, ("schema_version", "status", "release_clearance", "risk_accepted", "rows"))
    require(value["schema_version"] in ("residual-vendor-current-v1", "residual-vendor-current-publication-v1")
            and value["status"] == "complete-assessed-with-OPEN"
            and value["release_clearance"] is False and value["risk_accepted"] is False, "vendor role differs")
    rows = _list(value["rows"], True)
    require(len(rows) == 6 and all(isinstance(r, dict) for r in rows), "six vendor rows required")
    require(all(isinstance(r.get("id"), str) for r in rows)
            and {r["id"] for r in rows} == set(LZ4) | {JACKSON}, "vendor row identity set differs")
    common = {"id", "status", "adopted", "risk_accepted", "native_clearance", "owner", "next_action",
              "historical_open_record", "source_evidence", "current_observations", *BODIES}
    lz4 = {"coordinate", "affected_range", "fix_floor", "gaps", "source_range_evaluation",
           "current_applicability_conclusion", "current_disposition", "behavior_proof_gaps",
           "behavior_hash_link_limitations", "source_observation"}
    case_sets = []
    for row in rows:
        jackson = row["id"] == JACKSON
        _keys(row, common | ({"contradiction", "historical_scopes"} if jackson else lz4))
        require(row["status"] == "OPEN" and all(row[k] is False for k in ("adopted", "risk_accepted", "native_clearance")),
                "OPEN distinctions changed")
        _text(row["owner"])
        _text(row["next_action"])
        historical = row["historical_open_record"]
        _keys(historical, ("id", "status", "risk_accepted", "source", "source_sha256", "source_retrieved_at_utc",
                           "branches", "next_decision", "open_reasons", "owner"))
        require(historical.get("id") == row["id"]
                and historical.get("status") == "OPEN" and historical.get("risk_accepted") is False,
                "historical OPEN identity differs")
        _text(historical["next_decision"])
        _text(historical["owner"])
        for reason in _list(historical["open_reasons"], True):
            _text(reason)
        _hash(historical.get("source_sha256"))
        _date(historical.get("source_retrieved_at_utc"))
        _member(historical.get("source"))
        for branch in _list(historical.get("branches"), True):
            _keys(branch, ("coordinate", "affected_range", "final_runtime", "reported_fixed", "scope_observations", "statuses"))
            _range(branch.get("affected_range"))
            _text(branch.get("coordinate"))
            _text(branch["final_runtime"])
            if branch["reported_fixed"] not in (None, ""):
                _version(branch["reported_fixed"])
            for status in _list(branch.get("statuses"), True):
                _text(status)
            for scope in _list(branch.get("scope_observations")):
                _keys(scope, ("case", "coordinate", "packaged", "scope", "usage", "version"))
                require(type(scope["packaged"]) is bool, "historical scope packaged type differs")
                for key in ("case", "coordinate", "scope", "usage"):
                    _text(scope[key])
                _version(scope["version"])
        labels = set()
        for entry in _list(row["source_evidence"], True):
            _keys(entry, ("label", "content_sha256", "evidence", "http_status", "retrieved_at_utc"))
            require(entry["label"] not in labels, "duplicate source label")
            labels.add(entry["label"])
            _hash(entry["content_sha256"])
            _reference(entry["evidence"])
            _date(entry["retrieved_at_utc"])
            expected_status = 404 if entry["label"].startswith("old-") else 200
            require(type(entry["http_status"]) is int and entry["http_status"] == expected_status,
                    "source HTTP status differs")
        require(labels == ({"repository", "new-global", "new-osv"} if jackson
                           else {"old-global", "old-osv", "new-global", "new-osv"}), "source labels missing")
        identities = set()
        observations = _list(row["current_observations"], True)
        require(len(observations) == (60 if jackson else 18), "observations omitted")
        for observation in observations:
            require(isinstance(observation, dict), "observation required")
            case, stage = _text(observation.get("case")), observation.get("stage")
            require(re.fullmatch(r"[a-z0-9-]+-j(?:17|21)", case) and stage in STAGES, "invalid case/stage")
            require((case, stage) not in identities, "duplicate observation")
            identities.add((case, stage))
            evidence = observation.get("evidence")
            require(isinstance(evidence, dict) and {"assessment", "packaged", "syft", "provenance"} <= evidence.keys(),
                    "physical evidence bindings missing")
            for ref in evidence.values():
                _reference(ref)
                require(ref["root"] == "current" and ref["member"].startswith(case + "/" + stage + "/"),
                        "cross-case evidence binding")
            if jackson:
                _keys(observation, ("case", "stage", "artifacts", "evidence"))
                for artifact in _list(observation["artifacts"], True):
                    _artifact(artifact)
            else:
                _keys(observation, ("case", "stage", "evidence", "image_id", "jar_sha256", "packaged",
                                    "physical_artifacts", "org_lz4_observations", "org_lz4_absence_checked",
                                    "behavior_proofs_passed", "behavior_claims_are_production_image_proof",
                                    "behavior_to_campaign_jar_hash_link", "proof_claims"))
                require(isinstance(observation["image_id"], str) and observation["image_id"].startswith("sha256:"), "image ID missing")
                _hash(observation["image_id"][7:])
                _hash(observation["jar_sha256"])
                require(observation["org_lz4_absence_checked"] is True and observation["org_lz4_observations"] == []
                        and observation["behavior_claims_are_production_image_proof"] is False
                        and observation["behavior_proofs_passed"] is True
                        and observation["behavior_to_campaign_jar_hash_link"] == "not-inferred-from-version-or-origin",
                        "physical/behavior distinctions differ")
                claims = _list(observation["proof_claims"], True)
                require(len(claims) == 2 and all(isinstance(x, str) for x in claims)
                        and set(claims) == {"lz4-default", "lz4-jni"}, "behavior proof claims differ")
                packaged = _list(observation["packaged"], True)
                require(len(packaged) == 1, "packaged binding differs")
                item = packaged[0]
                _keys(item, ("group", "artifact", "version", "filename", "sha256", "classifier", "origin"))
                require((item["group"], item["artifact"], item["version"]) == ("at.yawk.lz4", "lz4-java", "1.11.4"),
                        "installed component differs")
                _hash(item["sha256"])
                _member(item["filename"])
                require(item["filename"] == "lz4-java-1.11.4.jar" and item["classifier"] == ""
                        and item["origin"] == "resolved-runtime", "packaged role differs")
                for artifact in _list(observation["physical_artifacts"], True):
                    _artifact(artifact)
                    require(artifact["purl"] == "pkg:maven/at.yawk.lz4/lz4-java@1.11.4"
                            and any(x["sha256"] == item["sha256"] for x in artifact["physical_hashes"]),
                            "physical packaged hash differs")
        cases = {case for case, _ in identities}
        require(identities == {(case, stage) for case in cases for stage in STAGES}, "stage observations incomplete")
        if jackson:
            _text(row["contradiction"])
            _keys(row["historical_scopes"], ("runtime", "test_only"))
            for scope in row["historical_scopes"].values():
                _text(scope)
        else:
            case_sets.append(cases)
            require((row["affected_range"], row["fix_floor"]) == LZ4[row["id"]]
                    and row["coordinate"] == "at.yawk.lz4:lz4-java"
                    and row["source_range_evaluation"] == row["current_applicability_conclusion"] == CONCLUSION
                    and row["current_disposition"] == "supported-candidate/OPEN"
                    and row["gaps"] == [] and row["behavior_proof_gaps"] == [], "LZ4 conclusion differs")
            for limitation in _list(row["behavior_hash_link_limitations"], True):
                _keys(limitation, ("claim", "status"))
                require(limitation["status"] == "OPEN_BEHAVIOR_JAR_HASH_NOT_RETAINED", "behavior limit differs")
                _text(limitation["claim"])
            if row["source_observation"] is not None:
                _keys(row["source_observation"], ("file", "lines", "observation"))
                _member(row["source_observation"]["file"])
                require(all(type(x) is int and x > 0 for x in _list(row["source_observation"]["lines"], True)), "source lines differ")
                _text(row["source_observation"]["observation"])
    require(all(cases == case_sets[0] for cases in case_sets), "LZ4 case scope differs")


def _vendor_body_consistency(row):
    global_body, repository, osv = (row[k] for k in BODIES)
    count = 5 if row["id"] == JACKSON else 2
    require(len(global_body["vulnerabilities"]) == len(repository["vulnerabilities"])
            == len(osv["affected"]) == count, "advisory branches omitted")
    packages = [sorted(x["package"]["name"] for x in body)
                for body in (global_body["vulnerabilities"], repository["vulnerabilities"], osv["affected"])]
    require(packages[0] == packages[1] == packages[2], "advisory package branches differ")
    require(global_body["cve_id"] == repository["cve_id"] and global_body["cve_id"] in osv["aliases"],
            "body aliases conflict")
    if row["id"] != JACKSON:
        for role, patch in (("global_advisory", "first_patched_version"), ("repository_advisory", "patched_versions")):
            branches = [x for x in row[role]["vulnerabilities"] if x["package"]["name"] == row["coordinate"]]
            require(len(branches) == 1 and branches[0][patch] == row["fix_floor"]
                    and branches[0]["vulnerable_version_range"] == row["affected_range"], "body range/fix differs")
        branches = [x for x in osv["affected"] if x["package"]["name"] == row["coordinate"]]
        require(len(branches) == 1 and any(e.get("fixed") == row["fix_floor"]
                for span in branches[0]["ranges"] for e in span["events"]), "OSV fix differs")
        installed = _numeric_release("1.11.4")
        for span in branches[0]["ranges"]:
            for start, end, inclusive in _osv_intervals(span["events"]):
                require(not (start <= installed and (installed < end or (inclusive and installed == end))),
                        "OSV interval includes installed LZ4 version")
        for version in branches[0].get("versions", []):
            require(_numeric_release(version) != installed, "OSV explicit affected version includes installed LZ4 version")
    else:
        # The contradiction is evidence, not a reason to silently choose a feed.
        ranges = [{(x["package"]["name"], x["vulnerable_version_range"]) for x in b["vulnerabilities"]}
                  for b in (global_body, repository)]
        require(ranges[0] != ranges[1], "Jackson range conflict omitted")


def _metadata(source, kind, payload):
    return {"schema_version": kind + "-publication-1", "role": "DERIVED", "source": source,
            "canonicalization": "json-sort-keys-ascii-compact-v1", "projected_payload_sha256": _digest(payload)}


def project_vendor(raw: bytes, expected_sha256: str, source_member: str) -> dict:
    """Project the retained six-row source; raw source hashes stay distinct from object hashes."""
    value, source = _source(raw, expected_sha256, source_member, VENDOR_MEMBER)
    require(value.get("schema_version") == "residual-vendor-current-v1", "original vendor schema required")
    _vendor_rows(value)
    result = copy.deepcopy(value)
    bindings = []
    for index, (original, row) in enumerate(zip(value["rows"], result["rows"], strict=True)):
        pointer = "/rows/" + str(index)
        bodies = {}
        for role in BODIES:
            row[role] = _body_facts(original[role], role, row["id"])
            bodies[role] = {"json_pointer": pointer + "/" + role,
                            "canonical_sha256": _digest(original[role]), "projected_sha256": _digest(row[role])}
        _vendor_body_consistency(row)
        bindings.append({"id": row["id"], "json_pointer": pointer, "canonical_sha256": _digest(original),
                         "projected_sha256": _digest(row), "bodies": bodies})
    result["schema_version"] = "residual-vendor-current-publication-v1"
    metadata = _metadata(source, "vendor", result)
    metadata["source_canonical_sha256"] = _digest(value)
    metadata["rows"] = bindings
    result["publication_projection"] = metadata
    validate_vendor_projection(result)
    return result


def _projection(value, kind, member):
    require(isinstance(value, dict) and "publication_projection" in value, "projection metadata missing")
    payload = {k: v for k, v in value.items() if k != "publication_projection"}
    metadata = value["publication_projection"]
    common = {"schema_version", "role", "source", "canonicalization", "projected_payload_sha256"}
    _keys(metadata, common | ({"rows", "source_canonical_sha256"} if kind == "vendor" else {"original_command", "interpreter"}))
    source = metadata["source"]
    _keys(source, ("archive_member", "gzip_sha256", "json_sha256"))
    require(_member(source["archive_member"]) == member, "wrong source role")
    _hash(source["gzip_sha256"])
    _hash(source["json_sha256"])
    require(metadata == {**metadata, **_metadata(source, kind, payload)}, "projection role/hash differs")
    _safety(value)
    _canonical(value)
    return payload, metadata


def validate_vendor_projection(value: dict, source_raw: bytes | None = None) -> None:
    """Without source bytes this checks completeness/self-consistency, never provenance."""
    payload, metadata = _projection(value, "vendor", VENDOR_MEMBER)
    require(payload.get("schema_version") == "residual-vendor-current-publication-v1", "derived vendor schema required")
    _vendor_rows(payload)
    _hash(metadata["source_canonical_sha256"])
    bindings = _list(metadata["rows"], True)
    require(len(bindings) == len(payload["rows"]), "row fingerprints omitted")
    for index, (row, binding) in enumerate(zip(payload["rows"], bindings, strict=True)):
        _keys(binding, ("id", "json_pointer", "canonical_sha256", "projected_sha256", "bodies"))
        pointer = "/rows/" + str(index)
        require(binding["id"] == row["id"] and binding["json_pointer"] == pointer
                and binding["projected_sha256"] == _digest(row), "row binding differs")
        _hash(binding["canonical_sha256"])
        _keys(binding["bodies"], BODIES)
        for role in BODIES:
            body = row[role]
            require(body == _body_facts(body, role, row["id"]), "body contains non-whitelisted facts")
            entry = binding["bodies"][role]
            _keys(entry, ("json_pointer", "canonical_sha256", "projected_sha256"))
            _hash(entry["canonical_sha256"])
            require(entry["json_pointer"] == pointer + "/" + role and entry["projected_sha256"] == _digest(body),
                    "body binding differs")
        _vendor_body_consistency(row)
    if source_raw is not None:
        require(value == project_vendor(source_raw, metadata["source"]["gzip_sha256"],
                                        metadata["source"]["archive_member"]), "source reconstruction differs")


def _replay(value):
    require(isinstance(value, dict) and type(value.get("schema_version")) is int and value["schema_version"] == 1
            and value.get("status") == "complete-publication-replay", "original replay required")
    for key in ("command", "started_at_utc", "ended_at_utc", "cases", "stage_assessments", "summary",
                "generator_sha", "publication_tooling_sha", "publication_sha256", "execution_kind", "goal",
                "exit_code", "cli_exit_code", "input_files_unchanged", "runtime_proofs_repeated", "scans_repeated",
                "amendment_revision", "last_consumed_execution_ordinal", "repair_cycle", "repair_ceiling"):
        require(key in value, "replay required field missing")
    command = _list(value["command"], True)
    for argument in command:
        _text(argument)
    require(len(command) >= 2, "replay command missing")
    for key in ("started_at_utc", "ended_at_utc"):
        _date(value[key])
    require(datetime.fromisoformat(value["started_at_utc"].replace("Z", "+00:00"))
            <= datetime.fromisoformat(value["ended_at_utc"].replace("Z", "+00:00")), "replay time order differs")
    for key in ("exit_code", "cli_exit_code", "runtime_proofs_repeated", "scans_repeated"):
        require(type(value[key]) is int and value[key] == 0, "replay execution claim differs")
    for key in ("amendment_revision", "last_consumed_execution_ordinal", "repair_cycle", "repair_ceiling"):
        require(type(value[key]) is int and value[key] >= 0, "replay execution count differs")
    require(value["repair_cycle"] <= value["repair_ceiling"] and value["input_files_unchanged"] is True,
            "replay limits/inputs differ")
    _text(value["goal"])
    require(type(value["cases"]) is int and value["cases"] > 0
            and type(value["stage_assessments"]) is int and value["stage_assessments"] == 2 * value["cases"],
            "replay counts differ")
    require(isinstance(value["summary"], dict) and value["summary"].get("cases") == value["cases"]
            and value["summary"].get("stage_observations") == value["stage_assessments"], "replay summary differs")
    for key in ("generator_sha", "publication_tooling_sha"):
        require(isinstance(value[key], str) and re.fullmatch(r"[0-9a-f]{40}", value[key]), "replay source ID differs")
    _hash(value["publication_sha256"])
    _text(value["execution_kind"])


def project_replay(raw, expected_sha256, source_member, interpreter_provenance=None):
    """Change only command[0]; historical executable provenance is not inferred."""
    require(interpreter_provenance is None, "historical interpreter evidence is not supported by this schema")
    value, source = _source(raw, expected_sha256, source_member, REPLAY_MEMBER)
    require("publication_projection" not in value, "original replay required")
    _replay(value)
    result = copy.deepcopy(value)
    result["command"][0] = "python3"
    metadata = _metadata(source, "replay", result)
    metadata["original_command"] = {"json_pointer": "/command", "canonical_sha256": _digest(value["command"])}
    metadata["interpreter"] = {"portable_identifier": "python3", "historical_version": "not-recorded",
                               "historical_executable_sha256": "not-recorded"}
    result["publication_projection"] = metadata
    validate_replay_projection(result)
    return result


def validate_replay_projection(value, source_raw=None):
    """Source-assisted validation checks exact reconstruction, including untouched receipt fields."""
    payload, metadata = _projection(value, "replay", REPLAY_MEMBER)
    _replay(payload)
    require(payload["command"][0] == "python3", "portable interpreter differs")
    _keys(metadata["original_command"], ("json_pointer", "canonical_sha256"))
    require(metadata["original_command"]["json_pointer"] == "/command", "command reference differs")
    _hash(metadata["original_command"]["canonical_sha256"])
    require(metadata["interpreter"] == {"portable_identifier": "python3", "historical_version": "not-recorded",
                                       "historical_executable_sha256": "not-recorded"}, "invented interpreter provenance")
    if source_raw is not None:
        require(value == project_replay(source_raw, metadata["source"]["gzip_sha256"],
                                        metadata["source"]["archive_member"]), "source reconstruction differs")


def project(value, original_sha256):
    require(
        isinstance(original_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", original_sha256),
        "invalid private summary digest",
    )
    require(
        value.get("schema_version") == 1
        and value.get("status") == "validated-with-explicit-evidence-limits"
        and value.get("release_acceptance") is False
        and value.get("goal_complete") is False,
        "validated private summary required",
    )
    result = copy.deepcopy(value)
    hashes = result.pop("input_sha256")
    require(isinstance(hashes, dict) and hashes, "source hashes missing")
    require(
        all(
            isinstance(path, str)
            and path
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            for path, digest in hashes.items()
        ),
        "invalid source hash map",
    )
    result["input_files"] = [
        {"path": path, "sha256": digest} for path, digest in sorted(hashes.items())
    ]
    cases = result["runtime_default"]["cases"]
    require(
        len(cases) == 2 and {str(case["java_target"]) for case in cases} == {"17", "21"},
        "default runtime scope missing",
    )
    redactions = []
    for case in cases:
        wire = case["roundtrip"]
        nonce = wire["key"]
        require(
            isinstance(nonce, str) and nonce.startswith("default-lz4-") and len(nonce) > 12,
            "synthetic correlation missing",
        )
        require(
            wire["input_partition_key"] == nonce
            and wire["input"]["paymentId"] == nonce
            and wire["output"]["entryId"] == nonce,
            "contradictory correlation cannot be concealed by projection",
        )
        placeholder = "<synthetic-correlation-j" + str(case["java_target"]) + ">"
        wire["key"] = wire["input_partition_key"] = placeholder
        wire["input"]["paymentId"] = wire["output"]["entryId"] = placeholder
        redactions.append(
            {
                "java": str(case["java_target"]),
                "placeholder": placeholder,
                "fields": ["key", "input_partition_key", "input.paymentId", "output.entryId"],
            }
        )
    result["publication_projection"] = {
        "schema_version": "proof-publication-1",
        "private_summary_sha256": original_sha256,
        "raw_runtime_receipt": False,
        "changes": [
            "Lossless path/hash map represented as path/sha256 array.",
            "Random synthetic correlation values replaced consistently after original proof validation.",
        ],
        "correlation_redactions": redactions,
        "runtime_library_jar_byte_linkage": "Not retained by original default/native helpers. Their version/origin/image/source/config evidence is separate from assessed production-image JAR hashes.",
        "secret_scan_exceptions_added": False,
        "originals": "Unchanged private receipts and summary retained; their recorded hashes are not replaced.",
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("proof", "vendor", "replay"), default="proof")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--source-member")
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "fresh output required")
        raw = args.input.read_bytes()
        if args.mode == "proof":
            require(args.expected_sha256 is None and args.source_member is None, "proof mode options differ")
            output = project(_decode(raw), hashlib.sha256(raw).hexdigest())
        else:
            require(args.expected_sha256 is not None and args.source_member is not None, "source binding required")
            projector = project_vendor if args.mode == "vendor" else project_replay
            output = projector(raw, args.expected_sha256, args.source_member)
        encoded = json.dumps(output, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        if args.output.suffix == ".gz":
            encoded = gzip.compress(encoded, mtime=0)
        with args.output.open("xb") as stream:
            stream.write(encoded)
        print(
            "Derived publication record written; originals unchanged; not release clearance."
        )
        return 0
    except Exception as error:
        print("Proof publication incomplete: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
