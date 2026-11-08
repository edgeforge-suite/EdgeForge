"""Offline, lossless residual reconciliation. No collection or risk acceptance."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote


class Invalid(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def decode(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, "duplicate JSON key")
            out[key] = value
        return out

    return json.loads(
        raw, object_pairs_hook=unique, parse_constant=lambda _: need(False, "nonfinite JSON number")
    )


def text(value):
    need(isinstance(value, str) and bool(value.strip()), "missing essential string")
    return value


def hexhash(value, length=64):
    need(
        isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value),
        "invalid hash identity",
    )
    return value


def image_id(value):
    need(isinstance(value, str) and value.startswith("sha256:"), "missing image identity")
    hexhash(value[7:])
    return value


def relative(value):
    text(value)
    p = PurePosixPath(value)
    need(
        not p.is_absolute()
        and ".." not in p.parts
        and str(p) == value
        and "\\" not in value
        and ":" not in value,
        "unsafe evidence member",
    )
    return value


def privacy(value):
    """Reject host paths instead of rewriting identity-bearing historical objects."""
    if isinstance(value, str):
        need(
            not re.search(
                r"(?:/" r"Users/|/home/|/private/(?:tmp|var)/|/var/folders/|"
                r"/tmp/edgeforge|[A-Za-z]:\\\\)",
                value,
            ),
            "private host path in output",
        )
    elif isinstance(value, dict):
        for key, item in value.items():
            privacy(key)
            privacy(item)
    elif isinstance(value, list):
        for item in value:
            privacy(item)


class Evidence:
    """Roots are private CLI arguments; emitted references contain no host roots."""

    def __init__(self, roots):
        self.roots = {name: Path(path).resolve() for name, path in roots.items()}
        self.used = {}

    def raw(self, ref):
        need(set(ref) == {"root", "member", "sha256"}, "invalid evidence reference")
        name, member = text(ref["root"]), relative(ref["member"])
        need(
            name in self.roots and re.fullmatch(r"[a-z][a-z0-9_-]*", name), "unknown evidence root"
        )
        hexhash(ref["sha256"])
        path = (self.roots[name] / member).resolve()
        need(path.is_relative_to(self.roots[name]) and path.is_file(), "missing evidence member")
        raw = path.read_bytes()
        need(sha(raw) == ref["sha256"], "evidence member hash mismatch")
        key = (name, member)
        need(key not in self.used or self.used[key] == ref, "conflicting member hashes")
        self.used[key] = dict(ref)
        return gzip.decompress(raw) if member.endswith(".gz") else raw

    def read(self, ref):
        return decode(self.raw(ref))


def historical(decisions, copies, ledger):
    rows = decisions["records"]
    need(
        isinstance(rows, list) and rows and isinstance(copies, dict) and copies,
        "empty historical identities",
    )
    need(isinstance(ledger, list) and len(rows) == len(ledger), "historical record loss")
    ids, indices, used, families = set(), set(), set(), defaultdict(lambda: [0, 0])
    for row in rows:
        identifier, index = text(row["id"]), row["source_ledger_index"]
        need(type(index) is int and 0 <= index < len(ledger), "invalid source index")
        need(identifier not in ids and index not in indices, "duplicate historical identity/index")
        ids.add(identifier)
        indices.add(index)
        old = row["historical_record"]
        need(
            old == ledger[index] and digest(old) == row["historical_record_sha256_canonical"],
            "canonical historical record mismatch",
        )
        need(identifier == "IMG-" + digest(old["finding"])[:20], "historical IMG identity mismatch")
        need(
            text(old["disposition"]).startswith("OPEN") and row["risk_accepted"] is False,
            "historical disposition not OPEN",
        )
        observations = old["observations"]
        need(isinstance(observations, list) and observations, "missing historical observations")
        keys = row["component_copy_keys"]
        need(
            isinstance(keys, list) and len(keys) == len(set(keys)),
            "duplicate historical copy reference",
        )
        for key in keys:
            need(key in copies, "unresolved historical COPY identity")
            copy = copies[key]
            need(key == "COPY-" + digest(copy)[:20], "historical COPY identity mismatch")
            need(
                any((o["case"], o["stage"]) == (copy["case"], copy["stage"]) for o in observations),
                "copy outside historical observation",
            )
            for field in ("artifact_id", "name", "version", "type"):
                text(copy["component"][field])
            need(isinstance(copy["component"]["locations"], list), "missing historical locations")
            relative(copy["syft_member"])
            used.add(key)
        for observation in observations:
            text(observation["case"])
            text(observation["stage"])
        fam = text(row["family"])
        families[fam][0] += 1
        families[fam][1] += len(observations)
    need(indices == set(range(len(ledger))), "historical source index set differs")
    need(used == set(copies), "unaccounted historical COPY identities")
    result = {k: {"records": n[0], "observations": n[1]} for k, n in sorted(families.items())}
    declared = decisions["family_accounting"]
    need(set(declared) == set(result), "family partition differs")
    for name, counts in result.items():
        need(all(declared[name][k] == n for k, n in counts.items()), "family multiplicity differs")
        need(
            set(declared[name]["members"]) == {r["id"] for r in rows if r["family"] == name}
            and len(declared[name]["members"]) == counts["records"],
            "family identity set differs",
        )
    return {
        "records": len(rows),
        "observations": sum(v["observations"] for v in result.values()),
        "copies": len(copies),
        "families": result,
    }


def known_contract(counts, decisions, ledger_raw_sha):
    """The only fixed historical count contract; never used by generic mapping."""
    need(
        counts
        == {
            "records": 2186,
            "observations": 64720,
            "copies": 3990,
            "families": {
                "BUILD_JDK": {"records": 61, "observations": 910},
                "BUILD_MAVEN": {"records": 24, "observations": 780},
                "BUILD_OS": {"records": 1886, "observations": 56580},
                "FINAL_GO_PEBBLE": {"records": 26, "observations": 780},
                "FINAL_OS": {"records": 189, "observations": 5670},
            },
        },
        "known historical count contract differs",
    )
    expected = "9eccefe41a2a86b42f336db1921989fbddc589e98d0c37daebd37a166a7a22a5"
    need(
        ledger_raw_sha == decisions["source_ledger_sha256"] == expected,
        "known historical source ledger hash differs",
    )


STAGES = ("generated-build-stage", "generated-final-image")
STAGE_MEMBERS = (
    "assessment",
    "inventory",
    "syft",
    "findings",
    "packaged",
    "provenance",
    "native-members",
    "coordinate-gaps",
    "cache-scanner-gaps",
    "build-bom-coverage",
)
CLASSIFIER_MEMBERS = (
    "build-classifiers.cdx",
    "grype-build-classifiers",
    "grype-build-classifiers-extracted.cdx",
)
BUILD_DECLARATION_MEMBERS = ("retained-maven-bom", "resolved-inventory")


def bom_classifier_keys(components):
    selected = []
    for component in components:
        purl = text(component["purl"])
        query = parse_qs(purl.partition("?")[2].split("#", 1)[0], keep_blank_values=True)
        values = query.get("classifier", [""])
        need(len(values) == 1, "duplicate BOM classifier qualifier")
        if not values[0]:
            continue
        base = purl_base(purl)
        need(base.startswith("pkg:maven/") and "@" in base, "invalid classifier Maven purl")
        name, version = base[len("pkg:maven/") :].rsplit("@", 1)
        group, artifact = name.split("/", 1)
        types = query.get("type", ["jar"])
        need(len(types) == 1, "duplicate classifier artifact type")
        selected.append((group, artifact, version, types[0], values[0]))
    return selected


def classifier_inventory_required(bom, resolved):
    """Same qualified declaration boundary as the frozen assessor, not file presence."""
    need(
        isinstance(bom, dict)
        and bom["bomFormat"] == "CycloneDX"
        and isinstance(bom["components"], list)
        and bom["components"]
        and isinstance(resolved, list)
        and resolved,
        "missing build classifier declaration inventories",
    )
    need(all(isinstance(row, dict) for row in bom["components"]),
         "invalid classifier BOM component")
    need(all(isinstance(row, dict)
             and all(isinstance(row.get(key), str) and row[key]
                     for key in ("group", "artifact", "version", "type", "scope"))
             and isinstance(row.get("classifier", ""), str) for row in resolved),
         "invalid resolved-inventory member")
    selected = bom_classifier_keys(bom["components"])
    declared = [row for row in resolved if row.get("classifier")]
    if not selected:
        need(not declared, "classifier BOM/resolved set mismatch")
        return False
    expected = {
        ("org.apache.kafka", artifact, "4.2.1", "jar", "test")
        for artifact in ("kafka-clients", "kafka-server-common")
    }
    need(
        len(selected) == 2 and set(selected) == expected,
        "unsupported/missing/duplicate classifier declaration",
    )
    need(
        len(declared) == 2
        and all(row["scope"] == "test" for row in declared)
        and {
            (row["group"], row["artifact"], row["version"], row["type"], row["classifier"])
            for row in declared
        }
        == expected,
        "classifier BOM/resolved set mismatch",
    )
    return True


def paths(component):
    return {
        loc[field]
        for loc in component["locations"]
        for field in ("path", "realPath", "accessPath")
        if isinstance(loc.get(field), str)
    }


def purl_base(value):
    return unquote(value.split("?", 1)[0].split("#", 1)[0]) if value else None


def coordinate(value):
    base = purl_base(value)
    return base.rsplit("@", 1)[0] if base and "@" in base else None


def stage_data(ev, row, source):
    base = set(STAGE_MEMBERS) | (
        set(BUILD_DECLARATION_MEMBERS) if row["stage"] == STAGES[0] else set()
    )
    need(base <= set(row["evidence"]), "missing essential stage evidence")
    data = {name: ev.read(row["evidence"][name]) for name in base}
    requires_classifiers = row["stage"] == STAGES[0] and classifier_inventory_required(
        data["retained-maven-bom"], data["resolved-inventory"]
    )
    expected = base | (set(CLASSIFIER_MEMBERS) if requires_classifiers else set())
    need(set(row["evidence"]) == expected, "missing essential stage evidence")
    data.update({name: ev.read(row["evidence"][name]) for name in expected - base})
    assessment, provenance = data["assessment"], data["provenance"]
    for obj in (assessment, provenance):
        need(
            (obj["case"], obj["stage"], obj["generator_sha"], obj["collector_sha"])
            == (row["case"], row["stage"], source, source),
            "stage source binding differs",
        )
    need(
        assessment["status"] in ("complete-with-findings", "complete-no-matches")
        and type(assessment["exit_code"]) is int
        and assessment["exit_code"] == int(bool(data["findings"]))
        and assessment["status"]
        == ("complete-with-findings" if data["findings"] else "complete-no-matches")
        and type(assessment["findings"]) is int
        and assessment["findings"] == len(data["findings"]),
        "incomplete current stage",
    )
    image = assessment["image"]
    image_id(image["image_id"])
    need(hexhash(image["config_sha256"]) == image["image_id"][7:], "image/config binding differs")
    hexhash(image["configuration_sha256"])
    hexhash(image["jar_sha256"])
    need(image["platform"] == "linux/amd64" and image["rootfs"], "missing physical image scope")
    for layer in image["rootfs"]:
        image_id(layer)
    for field in (
        "image.tar",
        "source.tar",
        "input.tar",
        "image-config.json",
        "image-manifest.json",
    ):
        hexhash(provenance["files"][field])
    need(
        provenance["files"]["image-config.json"] == image["config_sha256"],
        "provenance config differs",
    )
    metadata = data["syft"]["source"]["metadata"]
    need(
        metadata["imageID"] == image["image_id"]
        and [x["digest"] for x in metadata["layers"]] == image["rootfs"],
        "Syft image binding differs",
    )
    artifacts = data["syft"]["artifacts"]
    need(isinstance(artifacts, list) and artifacts, "empty physical inventory")
    by_id = {}
    for item in artifacts:
        for field in ("id", "name", "version", "type"):
            text(item[field])
        need(item["id"] not in by_id, "duplicate current physical artifact identity")
        need(
            "purl" in item and isinstance(item["locations"], list) and item["locations"],
            "missing essential physical inventory fields",
        )
        for loc in item["locations"]:
            text(loc["path"])
            if loc.get("layerID"):
                need(loc["layerID"] in image["rootfs"], "artifact layer outside image")
        by_id[item["id"]] = item
    projected = [
        {k: x.get(k) for k in ("id", "type", "name", "version", "purl")}
        for x in sorted(artifacts, key=lambda x: x["id"])
    ]
    need(data["inventory"] == projected, "normalized/physical inventory identity loss")
    for name in (
        "findings",
        "packaged",
        "native-members",
        "coordinate-gaps",
        "cache-scanner-gaps",
        "build-bom-coverage",
    ):
        need(isinstance(data[name], list), "missing essential evidence array")
    if requires_classifiers:
        for label in (CLASSIFIER_MEMBERS[0], CLASSIFIER_MEMBERS[2]):
            need(
                data[label]["bomFormat"] == "CycloneDX"
                and isinstance(data[label]["components"], list),
                "missing classifier inventory",
            )
            need(
                sorted(bom_classifier_keys(data[label]["components"]))
                == sorted(bom_classifier_keys(data["retained-maven-bom"]["components"])),
                "classifier supplement declaration mismatch",
            )
        need(
            isinstance(data[CLASSIFIER_MEMBERS[1]]["matches"], list), "missing classifier findings"
        )
    cache = image["cache_jar_inventory"] if row["stage"] == STAGES[0] else []
    cache_by_path = {}
    for item in cache:
        need(text(item["path"]) not in cache_by_path, "duplicate physical cache path")
        hexhash(item["sha256"])
        need(type(item["bytes"]) is int and item["bytes"] > 0, "missing physical cache size")
        cache_by_path[item["path"]] = item
    if row["stage"] == STAGES[0]:
        need(
            cache and image["cache_jars"] == [x["path"] for x in cache],
            "incomplete cache inventory",
        )
    for item in artifacts:
        item_hashes = [
            {"path": p, "sha256": cache_by_path[p]["sha256"]}
            for p in sorted(paths(item) & cache_by_path.keys())
        ]
        item["physical_hashes"] = item_hashes
    for item in data["packaged"]:
        for field in ("group", "artifact", "version", "filename"):
            text(item[field])
        hexhash(item["sha256"])
        physical = [
            a
            for a in artifacts
            if any(p.endswith("BOOT-INF/lib/" + item["filename"]) for p in paths(a))
        ]
        need(physical, "packaged JAR lacks physical location")
        for artifact in physical:
            artifact["physical_hashes"].append(
                {"member": item["filename"], "sha256": item["sha256"]}
            )
    for item in data["native-members"]:
        hexhash(item["sha256"])
        text(item["member"])
        need(
            item["library"] in assessment["packaged_libraries"],
            "native member library binding differs",
        )
    need(
        [p["filename"] for p in data["packaged"]] == assessment["packaged_libraries"],
        "packaged inventory/assessment differs",
    )
    for item in data["findings"]:
        for field in ("scanner", "id", "type", "name", "version"):
            text(item[field])
        need(type(item["excluded_by_scanner"]) is bool, "finding exclusion identity missing")
    by_name, by_purl = defaultdict(list), defaultdict(list)
    for artifact in artifacts:
        by_name[(artifact["name"], artifact["version"])].append(artifact["id"])
        if artifact["purl"]:
            by_purl[(purl_base(artifact["purl"]), artifact["version"])].append(artifact["id"])
    candidate_rows, by_artifact = [], defaultdict(list)
    for ordinal, finding in enumerate(data["findings"]):
        candidates = (
            by_purl[(purl_base(finding["purl"]), finding["version"])]
            if finding.get("purl")
            else by_name[(finding["name"], finding["version"])]
        )
        candidate_rows.append(candidates)
        for identifier in candidates:
            by_artifact[identifier].append(
                {"ordinal": ordinal, "actual_id": finding["id"], "association_only": True}
            )
    return {
        "case": row["case"],
        "stage": row["stage"],
        "image": image,
        "classifier_inventory_required": requires_classifiers,
        "evidence": row["evidence"],
        "data": data,
        "artifacts": by_id,
        "finding_candidates": candidate_rows,
        "finding_links_by_artifact": by_artifact,
    }


def json_pointer(value, pointer):
    need(
        isinstance(pointer, str) and (not pointer or pointer.startswith("/")),
        "invalid evidence JSON pointer",
    )
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) and token.isdecimal() else value[token]
    return value


def behavior_receipt(ev, claim, source):
    """Retain actual helper receipt identities, without requiring deleted images/JARs."""
    receipt_ref = claim["receipt"]
    receipt = ev.read(receipt_ref)
    need(
        receipt["source_sha"] == source and receipt["source_dirty"] is False,
        "behavior receipt source differs",
    )
    if claim["passed"]:
        need(receipt["complete"] is True, "behavior receipt incomplete")
    cases = receipt["cases"]
    need(
        len(cases) == 2 and sorted(c["java"] for c in cases) == ["17", "21"],
        "behavior receipt Java scope differs",
    )
    observed = []
    for case in cases:
        identity = image_id(case["image_id"])
        if claim["kind"] == "lz4-default":
            if claim["passed"]:
                need(receipt["status"] == "passed", "default receipt behavior differs")
            origin = text(case["observation"]["lz4_origin"])
            need(
                case["observation"]["java"].startswith(case["java"] + "."),
                "behavior Java observation differs",
            )
        else:
            need(case["lz4"] == claim["version"], "native receipt version differs")
            if claim["passed"]:
                need(case["native_and_roundtrip"] == "passed", "native receipt behavior differs")
            log_ref = claim["runtime_logs"][case["java"]]
            need(
                PurePosixPath(log_ref["member"]).name == relative(case["runtime_log"]),
                "native runtime log identity differs",
            )
            log = ev.raw(log_ref).decode("utf-8")
            markers = "\n".join(line for line in log.splitlines() if "LZ4_NATIVE_PROOF" in line)
            origins = re.findall(r"\borigin=(\S+)", markers)
            need(origins and len(set(origins)) == 1, "native runtime origin missing/ambiguous")
            origin = origins[0]
        need(
            "lz4-java-" + claim["version"] + ".jar" in origin,
            "behavior receipt origin/version differs",
        )
        observed.append(
            {
                "java": case["java"],
                "version": claim["version"],
                "origin": origin,
                "observer_image_config_id": identity,
            }
        )
    if "library_sha256" in claim:
        hexhash(claim["library_sha256"])
        witness = claim["library_hash_evidence"]
        actual = json_pointer(ev.read(witness["evidence"]), witness["pointer"])
        need(
            actual == claim["library_sha256"], "declared behavior JAR hash unsupported/conflicting"
        )
    else:
        need("library_hash_evidence" not in claim, "hash evidence without declared JAR hash")
    return {
        "receipt": receipt_ref,
        "observations": observed,
        "library_sha256_retained": "library_sha256" in claim,
        "production_image_equivalence": False,
        "limitation": "Behavior observer images are not campaign production images; no behavior-to-campaign JAR hash equality inferred",
    }


def proofs(ev, ref, source):
    proof = ev.read(ref)
    need(
        proof["schema_version"] == "residual-proof-v1"
        and proof["source_sha"] == source
        and proof["complete"] is True,
        "incomplete proof aggregate",
    )
    result = {}
    for row in proof["claims"]:
        key = text(row["id"])
        need(key not in result, "duplicate proof claim")
        need(
            type(row["passed"]) is bool
            and row["kind"]
            in (
                "compatibility",
                "runtime",
                "lz4-default",
                "lz4-jni",
                "base-qualification",
                "toolchain",
            ),
            "invalid proof claim",
        )
        hexhash(row["source_sha"], 40)
        need(row["source_sha"] == source and row["evidence"], "missing proof source/evidence")
        for member in row["evidence"]:
            ev.raw(member)
        if row["kind"] in ("lz4-default", "lz4-jni"):
            need(
                row["coordinate"] == "at.yawk.lz4:lz4-java"
                and row["version"] == "1.11.4"
                and sorted(row["java_versions"]) == ["17", "21"],
                "LZ4 proof scope differs",
            )
            row = {**row, "retained_behavior": behavior_receipt(ev, row, source)}
        if row["kind"] in ("compatibility", "runtime"):
            text(row["case"])
            need(row["stage"] in STAGES, "compatibility proof stage missing")
            image_id(row["image_id"])
            hexhash(row["jar_sha256"])
        result[key] = row
    requirements = proof["requirements"]
    need(
        isinstance(requirements, list)
        and requirements
        and len(requirements) == len(set(requirements))
        and set(requirements) <= set(result),
        "required proof identity omitted",
    )
    return result


def proof_support(claim, current):
    return (
        claim["passed"] is True
        and claim["kind"] == "compatibility"
        and claim["case"] == current["case"]
        and claim["stage"] == current["stage"]
        and claim["image_id"] == current["image"]["image_id"]
        and claim["jar_sha256"] == current["image"]["jar_sha256"]
    )


def copy_mapping(key, old, current, claims, explicit, ev):
    component = old["component"]
    candidates = [
        item
        for item in current["artifacts"].values()
        if component.get("purl")
        and purl_base(item["purl"]) == purl_base(component["purl"])
        and item["version"] == component["version"]
        and paths(item) & paths(component)
    ]
    exact_remaining = list(candidates)
    coordinate_candidates = [
        item
        for item in current["artifacts"].values()
        if coordinate(component.get("purl"))
        and coordinate(item["purl"]) == coordinate(component["purl"])
    ]
    basis, gaps, edge = "exact-purl-version-and-physical-path", [], None
    status = "current-copy-observed" if len(candidates) == 1 else "OPEN"
    if len(candidates) != 1:
        gaps.append(
            "ambiguous-current-physical-copy" if candidates else "no-exact-current-physical-copy"
        )
        if coordinate_candidates:
            gaps.append("same-coordinate-current-candidates-unverified-not-replacements")
    if key in explicit:
        link = explicit[key]
        target = current["artifacts"].get(link["artifact_id"])
        need(target is not None, "replacement target identity omitted")
        need(link["proof_claim"] in claims, "unknown replacement proof")
        edge = ev.read(link["edge_evidence"])
        need(
            edge["old_copy_key"] == key
            and edge["case"] == current["case"]
            and edge["stage"] == current["stage"]
            and edge["artifact_id"] == target["id"]
            and edge["image_id"] == current["image"]["image_id"]
            and edge["purl"] == target["purl"]
            and edge["version"] == target["version"]
            and edge["locations"] == target["locations"]
            and edge["physical_hashes"] == target["physical_hashes"],
            "replacement evidence binding differs",
        )
        text(edge["introducing_edge"])
        text(edge["candidate_basis"])
        candidates = [target]
        basis = "explicit-copy-edge-and-bound-compatibility-proof"
        if (
            proof_support(claims[link["proof_claim"]], current)
            and target["physical_hashes"]
            and target["purl"]
        ):
            status, gaps = "current-replacement-observed", []
        else:
            status, gaps = "OPEN", ["replacement-compatibility-or-physical-hash-unproven"]
        if exact_remaining:
            status = "OPEN"
            gaps.append("historical-physical-copy-still-observed-no-replacement-clearance")
    # This physical copy is a residual, not cleared by the compiler's separate 4.0.3 realm.
    if any(
        item["version"] == "4.0.2"
        and coordinate(item["purl"]) == "pkg:maven/org.codehaus.plexus/plexus-utils"
        for item in candidates + exact_remaining
    ):
        status = "OPEN"
        gaps.append("clean-plugin-plexus-4.0.2-distinct-copy-remains-open")
    finding_links = sorted(
        {
            x["ordinal"]: x
            for a in candidates
            for x in current["finding_links_by_artifact"].get(a["id"], [])
        }.values(),
        key=lambda x: x["ordinal"],
    )
    return {
        "historical_copy": old,
        "case": current["case"],
        "stage": current["stage"],
        "image_id": current["image"]["image_id"],
        "config_sha256": current["image"]["config_sha256"],
        "jar_sha256": current["image"]["jar_sha256"],
        "current_candidates": candidates,
        "exact_historical_copy_observations": exact_remaining,
        "unverified_coordinate_candidates": coordinate_candidates,
        "evidence": current["evidence"],
        "current_disposition": status,
        "historical_disposition": "OPEN",
        "basis": basis,
        "gaps": gaps,
        "replacement_link": explicit.get(key),
        "introducing_edge": edge,
        "current_finding_links": finding_links,
        "owner": "Engine maintainer",
        "next_action": "Resolve physical-copy/applicability gaps; no automatic closure",
        "risk_accepted": False,
    }


def map_history(decisions, copies, stages, claims, explicit, ev):
    mapped = {}
    for key, old in copies.items():
        stage = stages.get((old["case"], old["stage"]))
        need(stage is not None, "historical copy current stage omitted")
        mapped[key] = copy_mapping(key, old, stage, claims, explicit, ev)
    rows = []
    for row in decisions["records"]:
        observations = []
        for ordinal, old in enumerate(row["historical_record"]["observations"]):
            identity = (old["case"], old["stage"])
            need(identity in stages, "historical observation current stage omitted")
            keys = [
                k
                for k in row["component_copy_keys"]
                if (copies[k]["case"], copies[k]["stage"]) == identity
            ]
            current = stages[identity]
            observations.append(
                {
                    "ordinal": ordinal,
                    "historical_observation": old,
                    "copy_links": keys,
                    "stage_key": "/".join(identity),
                    "current_image_id": current["image"]["image_id"],
                    "source_member": current["evidence"]["inventory"],
                    "status": "OPEN",
                    "gaps": [] if keys else ["historical-observation-has-no-physical-copy"],
                }
            )
        rows.append(
            {
                "historical_decision": row,
                "id": row["id"],
                "observation_links": observations,
                "status": "OPEN",
                "risk_accepted": False,
            }
        )
    return rows, mapped


def current_findings(stages, decisions):
    old_exact = defaultdict(list)
    for row in decisions["records"]:
        old_exact[digest(row["historical_record"]["finding"])].append(row["id"])
    result = []
    for identity, stage in sorted(stages.items()):
        for ordinal, finding in enumerate(stage["data"]["findings"]):
            candidates = stage["finding_candidates"][ordinal]
            result.append(
                {
                    "case": identity[0],
                    "stage": identity[1],
                    "ordinal": ordinal,
                    "actual_id": finding["id"],
                    "finding": finding,
                    "finding_sha256_canonical": digest(finding),
                    "image_id": stage["image"]["image_id"],
                    "source_member": stage["evidence"]["findings"],
                    "exact_historical_candidates": old_exact.get(digest(finding), []),
                    "physical_artifact_candidates": candidates,
                    "gaps": []
                    if len(candidates) == 1
                    else [
                        "ambiguous-finding-physical-copy"
                        if candidates
                        else "no-finding-physical-copy"
                    ],
                    "status": "OPEN",
                    "risk_accepted": False,
                }
            )
    return result


LZ4 = {
    "GHSA-343h-94h5-c4wr": "1.11.4",
    "GHSA-4v53-57pg-c464": "1.11.2",
    "GHSA-6cx8-rjf8-pr8g": "1.11.2",
    "GHSA-gm45-99xc-r7wv": "1.11.4",
    "GHSA-mcr4-qmvw-px4g": "1.11.4",
}
JACKSON = "GHSA-5gvw-p9qm-jgwh"


def range_evaluation(installed, expression):
    """Only retained numeric comparison syntax; unsupported is never clearance."""

    def version(value):
        parts = value.split(".")
        return tuple(map(int, parts)) + (0,) * (4 - len(parts))

    if not isinstance(expression, str) or not re.fullmatch(r"\d+(?:\.\d+){0,3}", installed):
        return "OPEN_UNSUPPORTED_RANGE"
    checks = []
    for fragment in expression.split(","):
        match = re.fullmatch(r"\s*(<=|>=|<|>|=)?\s*(\d+(?:\.\d+){0,3})\s*", fragment)
        if match is None:
            return "OPEN_UNSUPPORTED_RANGE"
        actual, boundary = version(installed), version(match[2])
        checks.append(
            {
                "<=": actual <= boundary,
                ">=": actual >= boundary,
                "<": actual < boundary,
                ">": actual > boundary,
                "=": actual == boundary,
            }[match[1] or "="]
        )
    return (
        "OPEN_INSTALLED_IN_RANGE"
        if all(checks)
        else "verified-installed-version-not-in-affected-range"
    )


def vendor_current(ev, plan, verification, sources, stages, kafka_cases, claims):
    need(
        len(plan) == len(LZ4) + 1 and {r["id"] for r in plan} == set(LZ4) | {JACKSON},
        "six vendor identity set differs",
    )
    verified = verification["five_supported_candidates"]
    need(
        len(verified) == len(LZ4) and {r["id"] for r in verified} == set(LZ4),
        "verified LZ4 identity set differs",
    )
    verified = {r["id"]: r for r in verified}
    need(
        len(kafka_cases) == 9 and len(set(kafka_cases)) == 9,
        "vendor proof requires nine Kafka cases",
    )
    rows = []
    for row in plan:
        identifier = row["id"]
        references = sources[identifier]
        need(references, "vendor source evidence omitted")
        refs = {x["label"]: x for x in references}
        need(len(refs) == len(references), "duplicate vendor source label")
        source_rows = []
        for entry in references:
            raw = ev.raw(entry["evidence"])
            need(
                sha(raw) == entry["content_sha256"] and text(entry["retrieved_at_utc"]),
                "vendor source content/date differs",
            )
            source_rows.append(entry)
        out = {
            "id": identifier,
            "status": "OPEN",
            "historical_open_record": row["historical_open_record"],
            "source_evidence": source_rows,
            "owner": row["owner"],
            "risk_accepted": False,
            "adopted": False,
            "native_clearance": False,
            "current_observations": [],
        }
        if identifier == JACKSON:
            for label, field, body_name in (
                ("repository", "repository_advisory", "jackson-databind-advisories.body"),
                ("new-global", "global_advisory", "jackson-global-advisory.body"),
                ("new-osv", "osv_advisory", "jackson-osv-advisory.body"),
            ):
                entry = refs[label]
                source = next(x for x in row["source_receipts"] if x["body"] == body_name)
                need(
                    entry["http_status"] == 200
                    and entry["content_sha256"] == source["sha256"]
                    and entry["retrieved_at_utc"] == source["retrieved_at_utc"],
                    "Jackson source/date differs",
                )
                body = ev.read(entry["evidence"])
                if label == "repository":
                    body = next(x for x in body if x["ghsa_id"] == identifier)
                need(body == row[field], "Jackson contradiction source content differs")
            out.update(
                {
                    "contradiction": text(row["contradiction"]),
                    "repository_advisory": row["repository_advisory"],
                    "global_advisory": row["global_advisory"],
                    "osv_advisory": row["osv_advisory"],
                    "historical_scopes": row["actual_scope"],
                    "next_action": "Reconcile repository inclusive range; runtime 3.1.7 and test-only 2.21.7 are distinct; no waiver",
                }
            )
            for identity, current in sorted(stages.items()):
                artifacts = [
                    a
                    for a in current["artifacts"].values()
                    if coordinate(a["purl"])
                    in (
                        "pkg:maven/tools.jackson.core/jackson-databind",
                        "pkg:maven/com.fasterxml.jackson.core/jackson-databind",
                    )
                ]
                out["current_observations"].append(
                    {
                        "case": identity[0],
                        "stage": identity[1],
                        "artifacts": artifacts,
                        "evidence": current["evidence"],
                    }
                )
        else:
            candidate = verified[identifier]
            need(
                candidate["fix_floor"] == LZ4[identifier]
                and candidate["coordinate"] == "at.yawk.lz4:lz4-java"
                and candidate["installed_version_to_reverify"] == "1.11.4",
                "LZ4 source candidate differs",
            )
            for suffix in ("global", "osv"):
                old, new = refs["old-" + suffix], refs["new-" + suffix]
                need(
                    old["http_status"] == 404 and new["http_status"] == 200,
                    "vendor feed status differs",
                )
                previous = next(
                    x for x in row["historical_feed_observation"] if suffix in x["artifact"]
                )
                recent = next(
                    x
                    for x in candidate["source_receipts"]
                    if x["file"].endswith(identifier + "-" + suffix + ".body")
                )
                need(
                    previous["sha256_uncompressed"] == old["content_sha256"]
                    and previous["retrieved_at_utc"] == old["retrieved_at_utc"]
                    and recent["sha256"] == new["content_sha256"]
                    and recent["retrieved_at_utc"] == new["retrieved_at_utc"],
                    "vendor dated source hash differs",
                )
                body = ev.read(new["evidence"])
                need(
                    body["ghsa_id" if suffix == "global" else "id"] == identifier,
                    "vendor actual advisory ID differs",
                )
                need(
                    body == row["global_advisory" if suffix == "global" else "osv_advisory"],
                    "vendor retained advisory content differs",
                )
                if suffix == "global":
                    branches = [
                        v
                        for v in body["vulnerabilities"]
                        if v["package"]["name"] == candidate["coordinate"]
                    ]
                    need(
                        len(branches) == 1
                        and branches[0]["first_patched_version"] == candidate["fix_floor"]
                        and branches[0]["vulnerable_version_range"] == candidate["affected_range"],
                        "global per-ID range/fix differs",
                    )
                else:
                    branches = [
                        v
                        for v in body["affected"]
                        if v["package"]["name"] == candidate["coordinate"]
                    ]
                    need(
                        len(branches) == 1
                        and any(
                            e.get("fixed") == candidate["fix_floor"]
                            for span in branches[0]["ranges"]
                            for e in span["events"]
                        ),
                        "OSV per-ID fix differs",
                    )
            evaluation = range_evaluation("1.11.4", candidate["affected_range"])
            gaps, all_hashes = [], []
            if evaluation != "verified-installed-version-not-in-affected-range":
                gaps.append(evaluation)
            for case in kafka_cases:
                both_hashes = []
                for stage_name in STAGES:
                    current = stages[(case, stage_name)]
                    packaged = [
                        x
                        for x in current["data"]["packaged"]
                        if (x["group"], x["artifact"]) == ("at.yawk.lz4", "lz4-java")
                    ]
                    old_coordinate = [
                        a
                        for a in current["artifacts"].values()
                        if coordinate(a["purl"]) == "pkg:maven/org.lz4/lz4-java"
                    ]
                    old_coordinate.extend(
                        x for x in current["data"]["packaged"] if x["group"] == "org.lz4"
                    )
                    physical = [
                        a
                        for a in current["artifacts"].values()
                        if purl_base(a["purl"]) == "pkg:maven/at.yawk.lz4/lz4-java@1.11.4"
                        and any(p.endswith("BOOT-INF/lib/lz4-java-1.11.4.jar") for p in paths(a))
                    ]
                    proof_ids = [
                        c["id"]
                        for c in claims.values()
                        if c["passed"] and c["kind"] in ("lz4-default", "lz4-jni")
                    ]
                    passed = {claims[c]["kind"] for c in proof_ids} == {"lz4-default", "lz4-jni"}
                    for claim in claims.values():
                        if (
                            claim["kind"] in ("lz4-default", "lz4-jni")
                            and "library_sha256" in claim
                        ):
                            need(
                                len(packaged) == 1
                                and claim["library_sha256"] == packaged[0]["sha256"],
                                "declared behavior/campaign JAR hash conflicts",
                            )
                    ok = (
                        len(packaged) == 1
                        and packaged[0]["version"] == "1.11.4"
                        and physical
                        and not old_coordinate
                    )
                    if not ok:
                        gaps.append(
                            case + "/" + stage_name + ":packaged-coordinate-hash-or-absence-gap"
                        )
                    if len(packaged) == 1:
                        both_hashes.append(packaged[0]["sha256"])
                        all_hashes.append(packaged[0]["sha256"])
                    out["current_observations"].append(
                        {
                            "case": case,
                            "stage": stage_name,
                            "image_id": current["image"]["image_id"],
                            "jar_sha256": current["image"]["jar_sha256"],
                            "packaged": packaged,
                            "physical_artifacts": physical,
                            "org_lz4_observations": old_coordinate,
                            "org_lz4_absence_checked": True,
                            "evidence": current["evidence"],
                            "behavior_proofs_passed": passed,
                            "behavior_claims_are_production_image_proof": False,
                            "behavior_to_campaign_jar_hash_link": "not-inferred-from-version-or-origin",
                            "proof_claims": proof_ids,
                        }
                    )
                if len(both_hashes) != len(STAGES) or len(set(both_hashes)) != 1:
                    gaps.append(case + ":build-final-lz4-hash-differs")
            if len(set(all_hashes)) != 1:
                gaps.append("cross-case-lz4-jar-hashes-differ")
            out.update(
                {
                    "coordinate": candidate["coordinate"],
                    "affected_range": candidate["affected_range"],
                    "fix_floor": candidate["fix_floor"],
                    "gaps": gaps,
                    "source_range_evaluation": evaluation,
                    "current_applicability_conclusion": evaluation if not gaps else "OPEN",
                    "behavior_proof_gaps": []
                    if {c["kind"] for c in claims.values() if c["passed"]}
                    >= {"lz4-default", "lz4-jni"}
                    else ["default-or-native-behavior-proof-not-passed"],
                    "behavior_hash_link_limitations": [
                        {"claim": c["id"], "status": "OPEN_BEHAVIOR_JAR_HASH_NOT_RETAINED"}
                        for c in claims.values()
                        if c["kind"] in ("lz4-default", "lz4-jni") and "library_sha256" not in c
                    ],
                    "source_observation": candidate.get("source_observation"),
                    "repository_advisory": row["repository_advisory"],
                    "global_advisory": row["global_advisory"],
                    "osv_advisory": row["osv_advisory"],
                    "current_disposition": "supported-candidate/OPEN" if not gaps else "OPEN",
                    "next_action": "Original goal authorizes an explicit evidence-based per-ID applicability decision; no new approval gate, risk acceptance or native blanket clearance",
                }
            )
        rows.append(out)
    return rows


def reconcile(manifest, ev, require_known=False):
    need(manifest["schema_version"] == "residual-reconciliation-v1", "unsupported manifest schema")
    source = hexhash(manifest["source_sha"], 40)
    h = manifest["historical"]
    decisions, copies, ledger = (ev.read(h[k]) for k in ("decisions", "copies", "ledger"))
    counts = historical(decisions, copies, ledger)
    need(
        decisions["source_ledger_sha256"] == h["ledger"]["sha256"],
        "historical compressed source hash differs",
    )
    if require_known:
        known_contract(counts, decisions, h["ledger"]["sha256"])
        need(source == "c8798275065a8a0b619046707fad053f8a9b9ad1", "frozen campaign source differs")
    # Read candidate/introducing-edge source context, without adopting its proposals.
    candidate, edges = ev.read(h["candidate"]), ev.read(h["edges"])
    need(
        candidate["automatic_risk_acceptance"] is False and edges,
        "invalid candidate/edge groundwork",
    )
    declaration = ev.read(manifest["declaration"])
    declared = {}
    kafka = []
    for row in declaration["cases"]:
        case = text(row["case"])
        need(
            case not in declared
            and set(row["assess"]) == set(STAGES)
            and len(row["assess"]) == len(STAGES),
            "duplicate/incomplete declared coverage",
        )
        declared[case] = row
        if row["shape"] in ("kafka", "kafka-router", "kafka-mixed"):
            kafka.append(case)
    campaign = ev.read(manifest["campaign"])
    need(
        campaign["campaign_complete"] is True
        and campaign["generator_sha"] == source
        and campaign["collector_sha"] == source,
        "incomplete current campaign",
    )
    campaign_cases = [row["case"] for row in campaign["cases"]]
    need(
        len(campaign_cases) == len(set(campaign_cases)) and set(campaign_cases) == set(declared),
        "campaign case coverage differs",
    )
    for row in campaign["cases"]:
        need(
            row["generator_sha"] == row["collector_sha"] == source
            and set(row["stages"]) == set(STAGES)
            and all(type(v) is int and v in (0, 1) for v in row["stages"].values()),
            "campaign stage/source incomplete",
        )
    stage_rows = manifest["stages"]
    stage_keys = [(row["case"], row["stage"]) for row in stage_rows]
    expected = {(case, stage) for case in declared for stage in STAGES}
    need(
        len(stage_keys) == len(set(stage_keys)) and set(stage_keys) == expected,
        "incomplete/duplicate current stage coverage",
    )
    if require_known:
        need(len(declared) == 30 and len(stage_rows) == 60, "known campaign scope differs")
    stages = {
        key: stage_data(ev, row, source) for key, row in zip(stage_keys, stage_rows, strict=True)
    }
    for case in declared:
        build, final = (stages[(case, stage)] for stage in STAGES)
        need(
            build["classifier_inventory_required"] == (case in kafka),
            "declared Kafka family classifier inventory coverage differs",
        )
        need(
            build["image"]["jar_sha256"] == final["image"]["jar_sha256"]
            and build["data"]["packaged"] == final["data"]["packaged"],
            "case build/final JAR or packaged inventory differs",
        )
    for row in campaign["cases"]:
        for stage, code in row["stages"].items():
            need(
                stages[(row["case"], stage)]["data"]["assessment"]["exit_code"] == code,
                "campaign/stage exit status differs",
            )
    claims = proofs(ev, manifest["proof_aggregate"], source)
    explicit = {}
    for link in manifest["replacement_links"]:
        copy_id = link["old_copy_key"]
        need(copy_id in copies and copy_id not in explicit, "duplicate/unknown replacement COPY")
        explicit[copy_id] = link
    records, copy_rows = map_history(decisions, copies, stages, claims, explicit, ev)
    findings = current_findings(stages, decisions)
    vendors = vendor_current(
        ev,
        ev.read(h["vendor_plan"]),
        ev.read(h["vendor_verification"]),
        manifest["vendor_sources"],
        stages,
        kafka,
        claims,
    )
    result = {
        "schema_version": "residual-history-map-v1",
        "status": "complete-assessed-with-OPEN",
        "source_sha": source,
        "historical_counts": counts,
        "records": records,
        "component_copies": copy_rows,
        "current_findings": findings,
        "current_counts": {
            "cases": len(declared),
            "stages": len(stages),
            "findings": len(findings),
            "copy_dispositions": dict(
                Counter(c["current_disposition"] for c in copy_rows.values())
            ),
        },
        "stages": {
            "/".join(k): {
                "case": s["case"],
                "stage": s["stage"],
                "image": s["image"],
                "classifier_inventory_required": s["classifier_inventory_required"],
                "assessment_gaps": {
                    name: {
                        "status": "OPEN" if s["data"][name] else "none-recorded-not-clearance",
                        "records": s["data"][name],
                    }
                    for name in ("coordinate-gaps", "cache-scanner-gaps")
                },
                "evidence": s["evidence"],
            }
            for k, s in sorted(stages.items())
        },
        "proof_claims": claims,
        "candidate_evidence": h["candidate"],
        "edge_evidence": h["edges"],
        "proof_gaps": [
            {"claim": c["id"], "gap": "required-proof-claim-not-passed"}
            for c in claims.values()
            if not c["passed"]
        ],
        "clean_plugin_plexus_residuals": [
            {
                "case": key[0],
                "stage": key[1],
                "artifact": a,
                "source_member": s["evidence"]["syft"],
                "status": "OPEN",
                "next_action": "Bind clean 3.5.0 realm; do not conflate compiler Plexus 4.0.3 or add override",
            }
            for key, s in sorted(stages.items())
            for a in s["artifacts"].values()
            if coordinate(a["purl"]) == "pkg:maven/org.codehaus.plexus/plexus-utils"
            and a["version"] == "4.0.2"
        ],
        "risk_accepted": False,
        "m2_complete": False,
        "release_clearance": False,
    }
    verify_lossless(result, decisions, copies)
    verify_current(result, stages)
    vendor_result = {
        "schema_version": "residual-vendor-current-v1",
        "status": "complete-assessed-with-OPEN",
        "rows": vendors,
        "risk_accepted": False,
        "release_clearance": False,
    }
    evidence = {
        "schema_version": "residual-input-receipt-v1",
        "members": [ev.used[k] for k in sorted(ev.used)],
        "historical_counts": counts,
        "current_counts": result["current_counts"],
        "actual_campaign_executed_by_this_cli": False,
    }
    for value in (result, vendor_result, evidence):
        privacy(value)
    return result, vendor_result, evidence


def verify_lossless(result, decisions, copies):
    rows = result["records"]
    need(len(rows) == len(decisions["records"]), "output historical record loss")
    need(
        {r["id"] for r in rows} == {r["id"] for r in decisions["records"]},
        "output historical ID set differs",
    )
    for mapped, old in zip(rows, decisions["records"], strict=True):
        need(
            mapped["historical_decision"] == old and mapped["id"] == old["id"],
            "output old record changed",
        )
        links = mapped["observation_links"]
        observations = old["historical_record"]["observations"]
        need(len(links) == len(observations), "output observation multiplicity loss")
        for ordinal, (link, observation) in enumerate(zip(links, observations, strict=True)):
            need(
                link["ordinal"] == ordinal and link["historical_observation"] == observation,
                "output observation identity changed",
            )
            keys = [
                k
                for k in old["component_copy_keys"]
                if (copies[k]["case"], copies[k]["stage"])
                == (observation["case"], observation["stage"])
            ]
            need(link["copy_links"] == keys, "output observation COPY link loss")
    need(set(result["component_copies"]) == set(copies), "output COPY identity set differs")
    for key, old in copies.items():
        need(
            result["component_copies"][key]["historical_copy"] == old, "output COPY object changed"
        )


def verify_current(result, stages):
    expected = [
        (key[0], key[1], n, finding)
        for key, stage in sorted(stages.items())
        for n, finding in enumerate(stage["data"]["findings"])
    ]
    actual = [
        (r["case"], r["stage"], r["ordinal"], r["finding"]) for r in result["current_findings"]
    ]
    need(actual == expected, "output current finding identity/multiplicity differs")


def write_new(path, value):
    privacy(value)
    if path.suffix == ".gz":
        with path.open("xb") as stream:
            stream.write(gzip.compress(canonical(value) + b"\n", mtime=0))
        return
    with path.open("x", encoding="ascii") as stream:
        stream.write(
            json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", action="append", required=True, metavar="ALIAS=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--known-historical-contract", action="store_true")
    parser.add_argument("--historical-only", action="store_true")
    parser.add_argument(
        "--plain-output",
        action="store_true",
        help="debugging only; default is compact deterministic gzip",
    )
    args = parser.parse_args(argv)
    try:
        roots = {}
        for value in args.root:
            name, path = value.split("=", 1)
            need(name not in roots, "duplicate root alias")
            roots[name] = path
        need(not args.output.exists(), "output already exists")
        ev = Evidence(roots)
        manifest_raw = args.manifest.read_bytes()
        manifest = decode(manifest_raw)
        if args.historical_only:
            h = manifest["historical"]
            decisions, copies, ledger = (ev.read(h[k]) for k in ("decisions", "copies", "ledger"))
            counts = historical(decisions, copies, ledger)
            need(
                decisions["source_ledger_sha256"] == h["ledger"]["sha256"],
                "historical ledger hash differs",
            )
            if args.known_historical_contract:
                known_contract(counts, decisions, h["ledger"]["sha256"])
            outputs = {
                "historical-contract-receipt.json": {
                    "status": "historical-integrity-only",
                    "counts": counts,
                    "members": [ev.used[k] for k in sorted(ev.used)],
                    "current_campaign_assessed": False,
                    "release_clearance": False,
                }
            }
            code = 0
        else:
            history, vendor, receipt = reconcile(manifest, ev, args.known_historical_contract)
            receipt["manifest_sha256"] = sha(manifest_raw)
            suffix = ".json" if args.plain_output else ".json.gz"
            outputs = {
                "residual-history-map" + suffix: history,
                "residual-vendor-current" + suffix: vendor,
                "reconciliation-receipt" + suffix: receipt,
            }
            code = 1
        for value in outputs.values():
            privacy(value)
        need(
            not any(args.output.resolve().is_relative_to(root) for root in ev.roots.values()),
            "output must be outside input roots",
        )
        args.output.mkdir(parents=True, exist_ok=False)
        for name, value in outputs.items():
            write_new(args.output / name, value)
        print(
            json.dumps(
                {
                    "exit_code": code,
                    "outputs": sorted(outputs),
                    "historical_counts": counts
                    if args.historical_only
                    else history["historical_counts"],
                }
            )
        )
        return code
    except Exception:
        # Never expose private exception paths or leave a misleading success receipt.
        print(
            "Reconciliation incomplete: invalid/missing evidence, identity, schema, or fresh output.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
