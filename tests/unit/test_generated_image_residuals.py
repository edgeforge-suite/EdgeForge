"""All current campaign fixtures are synthetic, never evidence of actual scans."""

import gzip
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import prepare_generated_image_residual_manifest as adapter
from scripts import reconcile_generated_image_residuals as r

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reconcile_generated_image_residuals.py"
SOURCE = "a" * 40


class Fixture:
    def __init__(self, root, case_count=10):
        self.root = root
        self.inputs = root / "inputs"
        self.inputs.mkdir()
        self.cases = [f"case-{i:02d}" for i in range(case_count)]
        self.stage_rows = []
        self.manifest = {
            "schema_version": "residual-reconciliation-v1",
            "source_sha": SOURCE,
            "historical": {},
            "replacement_links": [],
            "vendor_sources": {},
        }
        self.claims = []
        declarations, campaign_cases = [], []
        for i, case in enumerate(self.cases):
            declarations.append(
                {"case": case, "shape": "kafka" if i < 9 else "crud", "assess": list(r.STAGES)}
            )
            codes = {}
            for stage in r.STAGES:
                key = case + "/" + stage
                image = {
                    "image_id": "sha256:" + r.digest(key),
                    "config_sha256": r.digest(key),
                    "configuration_sha256": "b" * 64,
                    "jar_sha256": "c" * 64,
                    "platform": "linux/amd64",
                    "rootfs": ["sha256:" + "d" * 64],
                }
                artifacts = [
                    self.artifact("demo", "1.0", "/usr/share/demo/data", "pkg:generic/demo@1.0"),
                    self.artifact(
                        "clean",
                        "4.0.2",
                        "/root/.m2/clean/plexus-utils-4.0.2.jar",
                        "pkg:maven/org.codehaus.plexus/plexus-utils@4.0.2",
                        "plexus-utils",
                    ),
                    self.artifact(
                        "compiler",
                        "4.0.3",
                        "/root/.m2/compiler/plexus-utils-4.0.3.jar",
                        "pkg:maven/org.codehaus.plexus/plexus-utils@4.0.3",
                        "plexus-utils",
                    ),
                    self.artifact(
                        "lz4",
                        "1.11.4",
                        "/app/app.jar/BOOT-INF/lib/lz4-java-1.11.4.jar",
                        "pkg:maven/at.yawk.lz4/lz4-java@1.11.4",
                        "lz4-java",
                    ),
                ]
                packaged = [
                    {
                        "group": "at.yawk.lz4",
                        "artifact": "lz4-java",
                        "version": "1.11.4",
                        "filename": "lz4-java-1.11.4.jar",
                        "sha256": "e" * 64,
                    }
                ]
                if stage == r.STAGES[0]:
                    image["cache_jar_inventory"] = [
                        {"path": x["locations"][0]["path"], "sha256": r.digest(x), "bytes": 10}
                        for x in artifacts[1:3]
                    ]
                    image["cache_jars"] = [x["path"] for x in image["cache_jar_inventory"]]
                findings = [
                    {
                        "scanner": "synthetic",
                        "id": "NEW-ACTUAL-ID",
                        "name": "demo",
                        "version": "1.0",
                        "type": "generic",
                        "severity": "High",
                        "excluded_by_scanner": False,
                    }
                ] * 2
                assessment = {
                    "case": case,
                    "stage": stage,
                    "generator_sha": SOURCE,
                    "collector_sha": SOURCE,
                    "status": "complete-with-findings",
                    "exit_code": 1,
                    "findings": len(findings),
                    "image": image,
                    "packaged_libraries": [p["filename"] for p in packaged],
                }
                provenance = {
                    "case": case,
                    "stage": stage,
                    "generator_sha": SOURCE,
                    "collector_sha": SOURCE,
                    "files": {
                        k: "f" * 64
                        for k in (
                            "image.tar",
                            "source.tar",
                            "input.tar",
                            "image-config.json",
                            "image-manifest.json",
                        )
                    },
                }
                provenance["files"]["image-config.json"] = image["config_sha256"]
                data = {
                    "assessment": assessment,
                    "provenance": provenance,
                    "syft": {
                        "source": {
                            "metadata": {
                                "imageID": image["image_id"],
                                "layers": [{"digest": x} for x in image["rootfs"]],
                            }
                        },
                        "artifacts": artifacts,
                    },
                    "inventory": [
                        {k: a[k] for k in ("id", "type", "name", "version", "purl")}
                        for a in sorted(artifacts, key=lambda x: x["id"])
                    ],
                    "findings": findings,
                    "packaged": packaged,
                    "native-members": [],
                    "coordinate-gaps": [],
                    "cache-scanner-gaps": [],
                    "build-bom-coverage": [],
                }
                if stage == r.STAGES[0]:
                    components = [{"purl": "pkg:maven/demo/demo@1.0?type=jar"}]
                    resolved = [
                        {
                            "group": "demo",
                            "artifact": "demo",
                            "version": "1.0",
                            "type": "jar",
                            "scope": "compile",
                        }
                    ]
                    classifiers = (
                        [
                            {
                                "purl": "pkg:maven/org.apache.kafka/"
                                + name
                                + "@4.2.1?classifier=test&type=jar"
                            }
                            for name in ("kafka-clients", "kafka-server-common")
                        ]
                        if i < 9
                        else []
                    )
                    components.extend(classifiers)
                    resolved.extend(
                        {
                            "group": "org.apache.kafka",
                            "artifact": name,
                            "version": "4.2.1",
                            "type": "jar",
                            "scope": "test",
                            "classifier": "test",
                        }
                        for name in (("kafka-clients", "kafka-server-common") if i < 9 else ())
                    )
                    data.update(
                        {
                            "retained-maven-bom": {
                                "bomFormat": "CycloneDX",
                                "components": components,
                            },
                            "resolved-inventory": resolved,
                        }
                    )
                    if classifiers:
                        data.update(
                            {
                                "build-classifiers.cdx": {
                                    "bomFormat": "CycloneDX",
                                    "components": classifiers,
                                },
                                "grype-build-classifiers": {"matches": []},
                                "grype-build-classifiers-extracted.cdx": {
                                    "bomFormat": "CycloneDX",
                                    "components": classifiers,
                                },
                            }
                        )
                self.stage_rows.append(
                    {
                        "case": case,
                        "stage": stage,
                        "evidence": {
                            k: self.save(key + "/" + k + ".json", v) for k, v in data.items()
                        },
                    }
                )
                self.claims.append(
                    {
                        "id": key,
                        "kind": "compatibility",
                        "passed": True,
                        "source_sha": SOURCE,
                        "case": case,
                        "stage": stage,
                        "image_id": image["image_id"],
                        "jar_sha256": image["jar_sha256"],
                        "evidence": [self.save(key + "/proof.json", {"synthetic": True})],
                    }
                )
                codes[stage] = 1
            campaign_cases.append(
                {"case": case, "generator_sha": SOURCE, "collector_sha": SOURCE, "stages": codes}
            )
        self.manifest["stages"] = self.stage_rows
        self.manifest["declaration"] = self.save("declaration.json", {"cases": declarations})
        self.manifest["campaign"] = self.save(
            "campaign.json",
            {
                "campaign_complete": True,
                "generator_sha": SOURCE,
                "collector_sha": SOURCE,
                "cases": campaign_cases,
            },
        )
        for kind in ("lz4-default", "lz4-jni"):
            behavior_cases = [
                {
                    "java": java,
                    "image_id": "sha256:" + r.digest(kind + java),
                    "lz4": "1.11.4",
                    "native_and_roundtrip": "passed",
                    "runtime_log": "runtime-j" + java + ".log",
                    "observation": {
                        "java": java + ".0.1",
                        "lz4_origin": "jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/",
                    },
                }
                for java in ("17", "21")
            ]
            receipt = self.save(
                kind + "-receipt.json",
                {
                    "source_sha": SOURCE,
                    "source_dirty": False,
                    "complete": True,
                    "status": "passed",
                    "cases": behavior_cases,
                },
            )
            logs = {}
            for java in ("17", "21"):
                member = kind + "/runtime-j" + java + ".log"
                path = self.inputs / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(
                    b"LZ4_NATIVE_PROOF origin=jar:nested:/app/app.jar/!BOOT-INF/lib/lz4-java-1.11.4.jar!/ sha256=native-member-not-jar\n"
                )
                logs[java] = {
                    "root": "synthetic",
                    "member": member,
                    "sha256": r.sha(path.read_bytes()),
                }
            self.claims.append(
                {
                    "id": kind,
                    "kind": kind,
                    "passed": True,
                    "source_sha": SOURCE,
                    "coordinate": "at.yawk.lz4:lz4-java",
                    "receipt": receipt,
                    "runtime_logs": logs,
                    "version": "1.11.4",
                    "java_versions": ["17", "21"],
                    "evidence": [receipt],
                }
            )
        self.manifest["proof_aggregate"] = self.save(
            "proof.json",
            {
                "schema_version": "residual-proof-v1",
                "source_sha": SOURCE,
                "complete": True,
                "claims": self.claims,
                "requirements": [x["id"] for x in self.claims],
            },
        )
        self.copies = {}
        records, ledger = [], []
        for name, component in [
            ("demo", self.artifact("demo", "1.0", "/usr/share/demo/data", "pkg:generic/demo@1.0")),
            (
                "plexus-utils",
                self.artifact(
                    "clean",
                    "4.0.2",
                    "/root/.m2/clean/plexus-utils-4.0.2.jar",
                    "pkg:maven/org.codehaus.plexus/plexus-utils@4.0.2",
                    "plexus-utils",
                ),
            ),
        ]:
            component["artifact_id"] = component.pop("id")
            component["copy_sites"] = ["base-os-or-jdk" if name == "demo" else "maven-cache"]
            component["metadata"] = {}
            physical = {
                "case": self.cases[0],
                "stage": r.STAGES[0],
                "component": component,
                "syft_member": self.cases[0] + "/" + r.STAGES[0] + "/syft.json.gz",
            }
            key = "COPY-" + r.digest(physical)[:20]
            self.copies[key] = physical
            finding = {
                "scanner": "old-synthetic",
                "id": "OLD-" + name,
                "name": name,
                "version": component["version"],
                "type": component["type"],
                "excluded_by_scanner": False,
            }
            old = {
                "finding": finding,
                "disposition": "OPEN; historical synthetic",
                "observations": [{"case": self.cases[0], "stage": r.STAGES[0]}]
                * (2 if name == "demo" else 1),
            }
            identifier = "IMG-" + r.digest(finding)[:20]
            records.append(
                {
                    "id": identifier,
                    "source_ledger_index": len(records),
                    "historical_record": old,
                    "historical_record_sha256_canonical": r.digest(old),
                    "component_copy_keys": [key],
                    "family": "SYNTHETIC",
                    "risk_accepted": False,
                    "owner": "Engine",
                    "next_action": "test only",
                }
            )
            ledger.append(old)
        ledger_ref = self.save("ledger.json.gz", ledger)
        self.decisions = {
            "records": records,
            "source_ledger_sha256": ledger_ref["sha256"],
            "family_accounting": {
                "SYNTHETIC": {
                    "records": 2,
                    "observations": 3,
                    "members": [x["id"] for x in records],
                }
            },
        }
        self.manifest["historical"] = {
            "decisions": self.save("decisions.json", self.decisions),
            "copies": self.save("copies.json", self.copies),
            "ledger": ledger_ref,
            "candidate": self.save("candidate.json", {"automatic_risk_acceptance": False}),
            "edges": self.save("edges.json", [{"synthetic": True}]),
        }
        vendor, verified = [], []
        for identifier, fix in r.LZ4.items():
            global_body = {
                "ghsa_id": identifier,
                "vulnerabilities": [
                    {
                        "package": {"name": "at.yawk.lz4:lz4-java"},
                        "first_patched_version": fix,
                        "vulnerable_version_range": "<= 1.11.3" if fix == "1.11.4" else "<= 1.11.1",
                    }
                ],
            }
            osv = {
                "id": identifier,
                "affected": [
                    {
                        "package": {"name": "at.yawk.lz4:lz4-java"},
                        "ranges": [{"events": [{"fixed": fix}]}],
                    }
                ],
            }
            feed, previous, recent = [], [], []
            for suffix, body in (("global", global_body), ("osv", osv)):
                for prefix, status, content in (
                    ("old", 404, {"message": "synthetic missing"}),
                    ("new", 200, body),
                ):
                    date = "2026-10-05T00:00:00Z" if prefix == "old" else "2026-10-19T00:00:00Z"
                    ref = self.save(identifier + "/" + prefix + "-" + suffix + ".json", content)
                    feed.append(
                        {
                            "label": prefix + "-" + suffix,
                            "http_status": status,
                            "retrieved_at_utc": date,
                            "content_sha256": ref["sha256"],
                            "evidence": ref,
                        }
                    )
                    if prefix == "old":
                        previous.append(
                            {
                                "artifact": identifier + "-" + suffix + ".json.gz",
                                "sha256_uncompressed": ref["sha256"],
                                "retrieved_at_utc": date,
                                "http_status": 404,
                            }
                        )
                    else:
                        recent.append(
                            {
                                "file": "maven-research/" + identifier + "-" + suffix + ".body",
                                "sha256": ref["sha256"],
                                "retrieved_at_utc": date,
                                "http_status": 200,
                            }
                        )
            self.manifest["vendor_sources"][identifier] = feed
            vendor.append(
                {
                    "id": identifier,
                    "owner": "Engine",
                    "historical_open_record": {"status": "OPEN"},
                    "historical_feed_observation": previous,
                    "repository_advisory": global_body,
                    "global_advisory": global_body,
                    "osv_advisory": osv,
                }
            )
            verified.append(
                {
                    "id": identifier,
                    "coordinate": "at.yawk.lz4:lz4-java",
                    "fix_floor": fix,
                    "affected_range": "<= 1.11.3" if fix == "1.11.4" else "<= 1.11.1",
                    "installed_version_to_reverify": "1.11.4",
                    "source_receipts": recent,
                }
            )
        jackson = {
            "id": r.JACKSON,
            "owner": "Engine",
            "historical_open_record": {"status": "OPEN"},
            "contradiction": ">= 2.21.0, <= 2.22.0 versus >= 2.21.0, < 2.21.5",
            "repository_advisory": {"ghsa_id": r.JACKSON, "synthetic": True},
            "global_advisory": {"id": r.JACKSON, "synthetic": True},
            "osv_advisory": {"id": r.JACKSON, "synthetic": True},
            "actual_scope": {"runtime": "3.1.7", "test_only": "2.21.7"},
            "source_receipts": [],
        }
        vendor.append(jackson)
        self.manifest["vendor_sources"][r.JACKSON] = []
        for label, field, body_name in (
            ("repository", "repository_advisory", "jackson-databind-advisories.body"),
            ("new-global", "global_advisory", "jackson-global-advisory.body"),
            ("new-osv", "osv_advisory", "jackson-osv-advisory.body"),
        ):
            body = [jackson[field]] if label == "repository" else jackson[field]
            ref = self.save("jackson-" + label + ".json", body)
            entry = {
                "label": label,
                "http_status": 200,
                "retrieved_at_utc": "2026-10-19T00:00:00Z",
                "content_sha256": ref["sha256"],
                "evidence": ref,
            }
            self.manifest["vendor_sources"][r.JACKSON].append(entry)
            jackson["source_receipts"].append(
                {
                    "body": body_name,
                    "sha256": ref["sha256"],
                    "retrieved_at_utc": entry["retrieved_at_utc"],
                    "http_status": 200,
                }
            )
        self.manifest["historical"]["vendor_plan"] = self.save("vendor-plan.json", vendor)
        self.manifest["historical"]["vendor_verification"] = self.save(
            "vendor-verification.json", {"five_supported_candidates": verified}
        )

    @staticmethod
    def artifact(identifier, version, path, purl, name=None):
        location = {"path": path, "layerID": "sha256:" + "d" * 64}
        if "/BOOT-INF/lib/" in path:
            outer, nested = path.split("/BOOT-INF/", 1)
            location.update(path=outer, accessPath=outer + ":BOOT-INF/" + nested)
        return {
            "id": identifier,
            "name": name or identifier,
            "version": version,
            "type": "generic",
            "purl": purl,
            "locations": [location],
        }

    def save(self, member, value):
        path = self.inputs / member
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = r.canonical(value)
        if member.endswith(".gz"):
            raw = gzip.compress(raw, mtime=0)
        path.write_bytes(raw)
        return {"root": "synthetic", "member": member, "sha256": r.sha(raw)}

    def update(self, ref, change):
        value = r.Evidence({"synthetic": self.inputs}).read(ref)
        change(value)
        ref.update(self.save(ref["member"], value))

    def run(self):
        return r.reconcile(self.manifest, r.Evidence({"synthetic": self.inputs}))


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parent, prefix="synthetic-"
        )
        self.root = Path(self.temp.name)
        self.f = Fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_lossless_open_and_additive_actual_ids(self):
        history, vendor, receipt = self.f.run()
        self.assertEqual(history["historical_counts"]["observations"], 3)
        self.assertEqual(len(history["records"][0]["observation_links"]), 2)
        self.assertEqual(len(history["current_findings"]), 40)
        self.assertTrue(
            all(
                x["actual_id"] == "NEW-ACTUAL-ID" and not x["exact_historical_candidates"]
                for x in history["current_findings"]
            )
        )
        self.assertEqual(len(vendor["rows"]), 6)
        self.assertTrue(all(x["status"] == "OPEN" for x in vendor["rows"]))
        self.assertTrue(
            all(
                x["current_disposition"] == "supported-candidate/OPEN"
                for x in vendor["rows"]
                if x["id"] in r.LZ4
            )
        )
        clean = next(
            x
            for x in history["component_copies"].values()
            if x["historical_copy"]["component"]["version"] == "4.0.2"
        )
        self.assertEqual(clean["current_disposition"], "OPEN")
        self.assertEqual([x["version"] for x in clean["current_candidates"]], ["4.0.2"])
        r.privacy(history)
        self.assertTrue(receipt["members"])

    def test_omitted_identity_fails(self):
        self.f.update(self.f.manifest["historical"]["decisions"], lambda x: x["records"].pop())
        with self.assertRaisesRegex(r.Invalid, "record loss"):
            self.f.run()

    def test_duplicate_historical_identity_fails(self):
        self.f.update(
            self.f.manifest["historical"]["decisions"],
            lambda x: x["records"].__setitem__(1, x["records"][0]),
        )
        with self.assertRaisesRegex(r.Invalid, "duplicate historical"):
            self.f.run()

    def test_dropped_observation_fails(self):
        self.f.update(
            self.f.manifest["historical"]["decisions"],
            lambda x: x["records"][0]["historical_record"]["observations"].pop(),
        )
        with self.assertRaisesRegex(r.Invalid, "canonical historical"):
            self.f.run()

    def test_wrong_hash_fails(self):
        self.f.manifest["stages"][0]["evidence"]["syft"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(r.Invalid, "hash mismatch"):
            self.f.run()

    def test_incomplete_current_stage_fails(self):
        self.f.manifest["stages"].pop()
        with self.assertRaisesRegex(r.Invalid, "stage coverage"):
            self.f.run()

    def test_duplicate_current_stage_fails(self):
        self.f.manifest["stages"].append(self.f.manifest["stages"][0])
        with self.assertRaisesRegex(r.Invalid, "stage coverage"):
            self.f.run()

    def test_duplicate_physical_identity_fails(self):
        self.f.update(
            self.f.stage_rows[0]["evidence"]["syft"],
            lambda x: x["artifacts"].append(x["artifacts"][0]),
        )
        with self.assertRaisesRegex(r.Invalid, "duplicate current physical"):
            self.f.run()

    def test_inventory_omission_fails(self):
        self.f.update(self.f.stage_rows[0]["evidence"]["inventory"], lambda x: x.pop())
        with self.assertRaisesRegex(r.Invalid, "inventory identity loss"):
            self.f.run()

    def test_missing_essential_field_fails(self):
        self.f.update(
            self.f.stage_rows[0]["evidence"]["assessment"], lambda x: x["image"].pop("jar_sha256")
        )
        with self.assertRaises(KeyError):
            self.f.run()

    def test_scanner_silence_does_not_close_history(self):
        for row in self.f.stage_rows:
            self.f.update(row["evidence"]["findings"], lambda x: x.clear())
            self.f.update(
                row["evidence"]["assessment"],
                lambda x: x.update(status="complete-no-matches", exit_code=0, findings=0),
            )
        self.f.update(
            self.f.manifest["campaign"],
            lambda x: [row.update(stages={s: 0 for s in r.STAGES}) for row in x["cases"]],
        )
        history, _, _ = self.f.run()
        self.assertEqual(history["current_counts"]["findings"], 0)
        self.assertTrue(all(x["status"] == "OPEN" for x in history["records"]))
        self.assertFalse(history["release_clearance"])

    def test_no_match_is_open(self):
        row = self.f.stage_rows[0]
        self.f.update(
            row["evidence"]["syft"],
            lambda x: x["artifacts"][0].update(version="2.0", purl="pkg:generic/demo@2.0"),
        )
        self.f.update(
            row["evidence"]["inventory"],
            lambda x: [
                a.update(version="2.0", purl="pkg:generic/demo@2.0") for a in x if a["id"] == "demo"
            ],
        )
        history, _, _ = self.f.run()
        mapped = next(
            x
            for x in history["component_copies"].values()
            if x["historical_copy"]["component"]["name"] == "demo"
        )
        self.assertEqual(mapped["current_disposition"], "OPEN")
        self.assertIn("no-exact-current-physical-copy", mapped["gaps"])

    def test_ambiguous_copies_are_open(self):
        ref = self.f.stage_rows[0]["evidence"]
        self.f.update(
            ref["syft"], lambda x: x["artifacts"].append({**x["artifacts"][0], "id": "demo2"})
        )
        self.f.update(
            ref["inventory"],
            lambda x: (
                x.append({**next(a for a in x if a["id"] == "demo"), "id": "demo2"}),
                x.sort(key=lambda a: a["id"]),
            ),
        )
        history, _, _ = self.f.run()
        mapped = next(
            x
            for x in history["component_copies"].values()
            if x["historical_copy"]["component"]["name"] == "demo"
        )
        self.assertEqual(mapped["current_disposition"], "OPEN")
        self.assertEqual(len(mapped["current_candidates"]), 2)

    def test_failed_behavior_is_separate_from_vendor_applicability(self):
        self.f.update(
            self.f.manifest["proof_aggregate"], lambda x: x["claims"][-1].update(passed=False)
        )
        _, vendor, _ = self.f.run()
        self.assertTrue(
            all(
                x["current_disposition"] == "supported-candidate/OPEN" and x["behavior_proof_gaps"]
                for x in vendor["rows"]
                if x["id"] in r.LZ4
            )
        )

    def test_cross_stage_lz4_hash_drift_open(self):
        self.f.update(
            self.f.stage_rows[1]["evidence"]["packaged"], lambda x: x[0].update(sha256="0" * 64)
        )
        with self.assertRaisesRegex(r.Invalid, "build/final JAR or packaged inventory"):
            self.f.run()

    def test_vendor_identity_omission_fails(self):
        self.f.update(self.f.manifest["historical"]["vendor_plan"], lambda x: x.pop())
        with self.assertRaisesRegex(r.Invalid, "six vendor"):
            self.f.run()

    def explicit_link(self, old_name="demo", remove_old=True, passed=True):
        key = next(k for k, c in self.f.copies.items() if c["component"]["name"] == old_name)
        row = self.f.stage_rows[0]
        if remove_old:
            self.f.update(
                row["evidence"]["syft"],
                lambda x: x.update(artifacts=[a for a in x["artifacts"] if a["id"] != "demo"]),
            )
            self.f.update(
                row["evidence"]["inventory"],
                lambda x: x.remove(next(a for a in x if a["id"] == "demo")),
            )
        ev = r.Evidence({"synthetic": self.f.inputs})
        current = r.stage_data(ev, row, SOURCE)
        target = current["artifacts"]["compiler"]
        edge = {
            "old_copy_key": key,
            "case": row["case"],
            "stage": row["stage"],
            "artifact_id": target["id"],
            "image_id": current["image"]["image_id"],
            "purl": target["purl"],
            "version": target["version"],
            "locations": target["locations"],
            "physical_hashes": target["physical_hashes"],
            "introducing_edge": "SYNTHETIC explicit edge, not actual product evidence",
            "candidate_basis": "SYNTHETIC replacement scenario",
        }
        self.f.manifest["replacement_links"] = [
            {
                "old_copy_key": key,
                "artifact_id": "compiler",
                "proof_claim": self.f.claims[0]["id"],
                "edge_evidence": self.f.save("replacement-edge.json", edge),
            }
        ]
        if not passed:
            self.f.update(
                self.f.manifest["proof_aggregate"], lambda x: x["claims"][0].update(passed=False)
            )
        return key

    def test_explicit_bound_replacement_still_preserves_historical_open(self):
        key = self.explicit_link()
        history, _, _ = self.f.run()
        self.assertEqual(
            history["component_copies"][key]["current_disposition"], "current-replacement-observed"
        )
        self.assertEqual(history["component_copies"][key]["historical_disposition"], "OPEN")
        self.assertTrue(all(x["status"] == "OPEN" for x in history["records"]))

    def test_explicit_replacement_failed_proof_is_open(self):
        key = self.explicit_link(passed=False)
        history, _, _ = self.f.run()
        self.assertEqual(history["component_copies"][key]["current_disposition"], "OPEN")

    def test_explicit_replacement_cannot_hide_still_present_clean_copy(self):
        key = self.explicit_link(old_name="plexus-utils", remove_old=False)
        history, _, _ = self.f.run()
        self.assertEqual(history["component_copies"][key]["current_disposition"], "OPEN")
        self.assertIn(
            "clean-plugin-plexus-4.0.2-distinct-copy-remains-open",
            history["component_copies"][key]["gaps"],
        )
        self.assertEqual(
            history["component_copies"][key]["exact_historical_copy_observations"][0]["version"],
            "4.0.2",
        )

    def test_replacement_edge_wrong_hash_rejected(self):
        self.explicit_link()
        self.f.update(
            self.f.manifest["replacement_links"][0]["edge_evidence"],
            lambda x: x["physical_hashes"][0].update(sha256="0" * 64),
        )
        with self.assertRaisesRegex(r.Invalid, "replacement evidence binding"):
            self.f.run()

    def test_required_proof_omission_fails(self):
        self.f.update(self.f.manifest["proof_aggregate"], lambda x: x["claims"].pop())
        with self.assertRaisesRegex(r.Invalid, "proof identity omitted"):
            self.f.run()

    def test_missing_classifier_evidence_fails(self):
        self.f.stage_rows[0]["evidence"].pop("build-classifiers.cdx")
        with self.assertRaisesRegex(r.Invalid, "essential stage evidence"):
            self.f.run()

    def test_non_kafka_build_without_supplements_is_complete(self):
        row = self.f.stage_rows[18]
        self.assertFalse(set(row["evidence"]) & set(r.CLASSIFIER_MEMBERS))
        history, _, _ = self.f.run()
        self.assertFalse(
            history["stages"][row["case"] + "/" + row["stage"]]["classifier_inventory_required"]
        )

    def test_nested_jar_access_path_is_physical_evidence(self):
        history, vendor, _ = self.f.run()
        ev = r.Evidence({"synthetic": self.f.inputs})
        stage = r.stage_data(ev, self.f.stage_rows[18], SOURCE)
        artifact = stage["artifacts"]["lz4"]
        self.assertEqual(artifact["locations"][0]["path"], "/app/app.jar")
        self.assertIn("BOOT-INF/lib/", artifact["locations"][0]["accessPath"])
        self.assertTrue(artifact["physical_hashes"])
        self.assertTrue(
            all(
                x["current_disposition"] == "supported-candidate/OPEN"
                for x in vendor["rows"]
                if x["id"] in r.LZ4
            )
        )

    def test_classifier_bom_resolved_mismatch_fails(self):
        self.f.update(self.f.stage_rows[0]["evidence"]["resolved-inventory"], lambda x: x.pop())
        with self.assertRaisesRegex(r.Invalid, "classifier BOM/resolved"):
            self.f.run()

    def test_kafka_cannot_drop_declarations_and_supplements(self):
        row = self.f.stage_rows[0]
        self.f.update(
            row["evidence"]["retained-maven-bom"],
            lambda x: x.update(components=x["components"][:1]),
        )
        self.f.update(
            row["evidence"]["resolved-inventory"], lambda x: x.__delitem__(slice(1, None))
        )
        for label in r.CLASSIFIER_MEMBERS:
            row["evidence"].pop(label)
        with self.assertRaisesRegex(r.Invalid, "Kafka family classifier"):
            self.f.run()

    def test_unexpected_non_kafka_classifier_supplement_fails(self):
        row = self.f.stage_rows[18]
        row["evidence"][r.CLASSIFIER_MEMBERS[0]] = self.f.stage_rows[0]["evidence"][
            r.CLASSIFIER_MEMBERS[0]
        ]
        with self.assertRaisesRegex(r.Invalid, "essential stage evidence"):
            self.f.run()

    def test_current_coordinate_gaps_are_open(self):
        self.f.update(
            self.f.stage_rows[0]["evidence"]["coordinate-gaps"],
            lambda x: x.append({"filename": "synthetic.jar", "coverage": "unknown coordinate"}),
        )
        history, _, _ = self.f.run()
        first = history["stages"][self.f.cases[0] + "/" + r.STAGES[0]]
        self.assertEqual(first["assessment_gaps"]["coordinate-gaps"]["status"], "OPEN")

    def test_current_finding_output_loss_rejected(self):
        history, _, _ = self.f.run()
        ev = r.Evidence({"synthetic": self.f.inputs})
        stages = {
            (row["case"], row["stage"]): r.stage_data(ev, row, SOURCE) for row in self.f.stage_rows
        }
        history["current_findings"].pop()
        with self.assertRaisesRegex(r.Invalid, "current finding identity"):
            r.verify_current(history, stages)

    def test_vendor_wrong_per_id_fix_rejected(self):
        identifier = next(iter(r.LZ4))
        source = next(
            x for x in self.f.manifest["vendor_sources"][identifier] if x["label"] == "new-global"
        )
        # Rehash the file reference but not the independently retained source receipt.
        self.f.update(
            source["evidence"],
            lambda x: x["vulnerabilities"][0].update(first_patched_version="9.9.9"),
        )
        with self.assertRaisesRegex(r.Invalid, "source content/date"):
            self.f.run()

    def test_output_observation_loss_rejected(self):
        history, _, _ = self.f.run()
        history["records"][0]["observation_links"].pop()
        with self.assertRaisesRegex(r.Invalid, "multiplicity loss"):
            r.verify_lossless(history, self.f.decisions, self.f.copies)

    def test_output_copy_identity_loss_rejected(self):
        history, _, _ = self.f.run()
        history["component_copies"].pop(next(iter(history["component_copies"])))
        with self.assertRaisesRegex(r.Invalid, "COPY identity set"):
            r.verify_lossless(history, self.f.decisions, self.f.copies)

    def test_cli_fresh_output_and_input_bytes(self):
        manifest = self.root / "manifest.json"
        manifest.write_bytes(r.canonical(self.f.manifest))
        before = {p: r.sha(p.read_bytes()) for p in self.f.inputs.rglob("*") if p.is_file()}
        cmd = [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--root",
            "synthetic=" + str(self.f.inputs),
            "--output",
            str(self.root / "output"),
        ]
        first = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 1, first.stderr)
        compressed = self.root / "output" / "residual-history-map.json.gz"
        self.assertTrue(compressed.is_file())
        self.assertEqual(
            r.decode(gzip.decompress(compressed.read_bytes()))["historical_counts"]["observations"],
            3,
        )
        self.assertEqual(compressed.read_bytes()[4:8], b"\0\0\0\0")
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
        self.assertEqual(
            before, {p: r.sha(p.read_bytes()) for p in self.f.inputs.rglob("*") if p.is_file()}
        )

    def test_invalid_cli_does_not_create_output(self):
        self.f.manifest["stages"].pop()
        manifest = self.root / "manifest.json"
        manifest.write_bytes(r.canonical(self.f.manifest))
        p = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--manifest",
                str(manifest),
                "--root",
                "synthetic=" + str(self.f.inputs),
                "--output",
                str(self.root / "output"),
            ],
            capture_output=True,
        )
        self.assertEqual(p.returncode, 2)
        self.assertFalse((self.root / "output").exists())
        self.assertNotIn(str(self.root).encode(), p.stderr)

    def test_cli_hash_bound_malformed_inventory_is_incomplete_not_findings(self):
        reference = self.f.stage_rows[0]["evidence"]["resolved-inventory"]
        original = r.decode((self.f.inputs / reference["member"]).read_bytes())
        for index, bad in enumerate((None, "not-a-record", 7, [], {})):
            with self.subTest(member=bad):
                broken = list(original)
                broken[0] = bad
                self.f.update(reference, lambda value, broken=broken: value.__setitem__(slice(None), broken))
                manifest = self.root / ("malformed-" + str(index) + ".json")
                manifest.write_bytes(r.canonical(self.f.manifest))
                output = self.root / ("malformed-output-" + str(index))
                run = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "--manifest", str(manifest),
                     "--root", "synthetic=" + str(self.f.inputs), "--output", str(output)],
                    capture_output=True,
                )
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertFalse(output.exists())
                self.assertNotIn(b"Traceback", run.stderr)
                self.assertNotIn(str(self.root).encode(), run.stderr)

    def test_cli_unexpected_inspection_exception_is_incomplete(self):
        manifest = self.root / "unexpected-manifest.json"
        manifest.write_bytes(r.canonical(self.f.manifest))
        output = self.root / "unexpected-output"
        program = """
import sys
from unittest.mock import patch
from scripts import reconcile_generated_image_residuals as module
with patch.object(module, 'reconcile', side_effect=AttributeError('synthetic inspection failure')):
    raise SystemExit(module.main(sys.argv[1:]))
"""
        run = subprocess.run(
            [sys.executable, "-B", "-c", program, "--manifest", str(manifest),
             "--root", "synthetic=" + str(self.f.inputs), "--output", str(output)],
            cwd=SCRIPT.parents[1], capture_output=True,
        )
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertFalse(output.exists())
        self.assertNotIn(b"Traceback", run.stderr)
        self.assertNotIn(str(self.root).encode(), run.stderr)

    def test_adapter_unexpected_inspection_exception_is_incomplete(self):
        output = self.root / "unexpected-adapter-output.json"
        program = """
import sys
from unittest.mock import patch
from scripts import prepare_generated_image_residual_manifest as module
with patch.object(module, 'prepare', side_effect=AttributeError('synthetic inspection failure')):
    raise SystemExit(module.main(sys.argv[1:]))
"""
        run = subprocess.run(
            [sys.executable, "-B", "-c", program, "--plan", str(self.f.inputs),
             "--ledger-file", str(self.f.inputs / "ledger.json"), "--old-policy", str(self.f.inputs),
             "--verification-file", str(self.f.inputs / "verification.json"),
             "--proof-file", str(self.f.inputs / "proof.json"), "--current", str(self.f.inputs),
             "--output", str(output)],
            cwd=SCRIPT.parents[1], capture_output=True,
        )
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertFalse(output.exists())
        self.assertNotIn(b"Traceback", run.stderr)
        self.assertNotIn(str(self.root).encode(), run.stderr)

    def test_traversal_and_symlink_escape_fails(self):
        ev = r.Evidence({"synthetic": self.f.inputs})
        ref = {"root": "synthetic", "member": "../secret", "sha256": "0" * 64}
        with self.assertRaises(r.Invalid):
            ev.raw(ref)
        (self.root / "secret").write_text("secret")
        (self.f.inputs / "escape").symlink_to(self.root / "secret")
        ref["member"] = "escape"
        with self.assertRaises(r.Invalid):
            ev.raw(ref)

    def test_duplicate_json_key_and_host_paths_rejected(self):
        with self.assertRaises(r.Invalid):
            r.decode(b'{"x":1,"x":2}')
        with self.assertRaises(r.Invalid):
            r.privacy({"path": "/".join(("", "Users", "example", "private"))})

    def test_deterministic_outputs(self):
        first = tuple(r.canonical(x) for x in self.f.run())
        self.assertEqual(first, tuple(r.canonical(x) for x in self.f.run()))

    def test_full_synthetic_30_case_60_stage_scope(self):
        separate = self.root / "full"
        separate.mkdir()
        f = Fixture(separate, case_count=30)
        history, vendor, _ = f.run()
        self.assertEqual(history["current_counts"]["cases"], 30)
        self.assertEqual(history["current_counts"]["stages"], 60)
        self.assertEqual(history["current_counts"]["findings"], 120)
        self.assertEqual(
            sum(stage["classifier_inventory_required"] for stage in history["stages"].values()), 9
        )
        self.assertTrue(
            all(len(x["current_observations"]) == 18 for x in vendor["rows"] if x["id"] in r.LZ4)
        )

    def adapter_roots(self, compressed=False):
        ev = r.Evidence({"synthetic": self.f.inputs})

        def copy_ref(old, name):
            return self.f.save(name, ev.read(old))

        for old, name in (
            ("decisions", "finding-decisions.json"),
            ("copies", "component-copies.json"),
            ("candidate", "candidate-bundle.json"),
            ("edges", "maven-research/edge-receipts.json"),
            ("vendor_plan", "maven-research/vendor-reconciliation.json"),
        ):
            copy_ref(self.f.manifest["historical"][old], name)
        copy_ref(self.f.manifest["declaration"], "coverage-declared.json")
        for identifier, sources in self.f.manifest["vendor_sources"].items():
            for source in sources:
                label = source["label"]
                if identifier in r.LZ4:
                    suffix = label.split("-", 1)[1]
                    member = (
                        "vendor-sources/" + identifier + "-" + suffix + ".json.gz"
                        if label.startswith("old-")
                        else "maven-research/" + identifier + "-" + suffix + ".body"
                    )
                else:
                    member = (
                        "maven-research/"
                        + {
                            "repository": "jackson-databind-advisories.body",
                            "new-global": "jackson-global-advisory.body",
                            "new-osv": "jackson-osv-advisory.body",
                        }[label]
                    )
                copy_ref(source["evidence"], member)
        if compressed:
            files = [self.f.inputs / name for name in ("campaign.json", "coverage-declared.json")]
            files += [
                self.f.inputs / ref["member"]
                for row in self.f.stage_rows
                for ref in row["evidence"].values()
            ]
            for path in files:
                path.with_suffix(path.suffix + ".gz").write_bytes(
                    gzip.compress(path.read_bytes(), mtime=0)
                )
                path.unlink()

        def proof_aliases(value):
            if isinstance(value, dict):
                if value.get("root") == "synthetic":
                    value["root"] = "proof"
                for item in value.values():
                    proof_aliases(item)
            elif isinstance(value, list):
                for item in value:
                    proof_aliases(item)

        self.f.update(self.f.manifest["proof_aggregate"], proof_aliases)
        return {
            name: self.f.inputs
            for name in ("plan", "historical", "policy", "verified", "proof", "current")
        }

    def test_raw_collector_adapter_without_manual_copy_edges(self):
        roots = self.adapter_roots()
        manifest = adapter.prepare(
            roots, "ledger.json.gz", "vendor-verification.json", "proof.json"
        )
        self.assertEqual(manifest["replacement_links"], [])
        history, vendor, _ = r.reconcile(manifest, r.Evidence(roots))
        self.assertEqual(history["historical_counts"]["copies"], 2)
        self.assertEqual(len(vendor["rows"]), 6)

    def test_sanitized_publisher_gzip_adapter(self):
        roots = self.adapter_roots(compressed=True)
        manifest = adapter.prepare(
            roots, "ledger.json.gz", "vendor-verification.json", "proof.json"
        )
        self.assertTrue(
            manifest["stages"][0]["evidence"]["inventory"]["member"].endswith(".json.gz")
        )
        history, _, _ = r.reconcile(manifest, r.Evidence(roots))
        self.assertEqual(history["current_counts"]["stages"], 20)

    def test_adapter_ambiguous_raw_and_gzip_member_fails(self):
        roots = self.adapter_roots()
        path = self.f.inputs / "campaign.json"
        (self.f.inputs / "campaign.json.gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        with self.assertRaisesRegex(r.Invalid, "ambiguous"):
            adapter.prepare(roots, "ledger.json.gz", "vendor-verification.json", "proof.json")

    def test_adapter_incomplete_campaign_fails(self):
        roots = self.adapter_roots()
        campaign = self.f.inputs / "campaign.json"
        value = r.decode(campaign.read_bytes())
        value["campaign_complete"] = False
        campaign.write_bytes(r.canonical(value))
        with self.assertRaisesRegex(r.Invalid, "not complete"):
            adapter.prepare(roots, "ledger.json.gz", "vendor-verification.json", "proof.json")

    def test_adapter_raw_build_bundle_declarations(self):
        roots = self.adapter_roots()
        row = self.f.stage_rows[18]
        for label in r.BUILD_DECLARATION_MEMBERS:
            path = self.f.inputs / row["evidence"][label]["member"]
            destination = self.f.inputs / row["case"] / (row["stage"] + "-bundle") / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
        manifest = adapter.prepare(
            roots, "ledger.json.gz", "vendor-verification.json", "proof.json"
        )
        self.assertIn(
            "-bundle/", manifest["stages"][18]["evidence"]["retained-maven-bom"]["member"]
        )
        r.reconcile(manifest, r.Evidence(roots))

    def test_adapter_raw_duplicate_assessment_is_explicitly_unsupported(self):
        roots = self.adapter_roots()
        row = self.f.stage_rows[18]
        path = self.f.inputs / row["evidence"]["assessment"]["member"]
        path.with_suffix(".json.gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        with self.assertRaisesRegex(r.Invalid, "ambiguous"):
            adapter.prepare(roots, "ledger.json.gz", "vendor-verification.json", "proof.json")

    @unittest.skipUnless(
        os.environ.get("EDGEFORGE_PARTIAL_STAGE"), "optional real read-only stage schema check"
    )
    def test_real_completed_non_kafka_stage_schema(self):
        stage = Path(os.environ["EDGEFORGE_PARTIAL_STAGE"])
        roots = {"current": stage.parent.parent}
        prefix = stage.parent.name + "/" + stage.name + "/"
        evidence = {
            name: (
                adapter.ref(roots, "current", prefix + "assessment.json.gz")
                if name == "assessment"
                else adapter.select(roots, "current", prefix + name)
            )
            for name in r.STAGE_MEMBERS
        }
        evidence.update(adapter.build_declarations(roots, stage.parent.name, stage.name))
        ev = r.Evidence(roots)
        source = ev.read(evidence["assessment"])["generator_sha"]
        data = r.stage_data(
            ev, {"case": stage.parent.name, "stage": stage.name, "evidence": evidence}, source
        )
        self.assertFalse(data["classifier_inventory_required"])

    def test_runtime_proof_is_not_builder_compatibility(self):
        key = self.explicit_link()
        self.f.update(
            self.f.manifest["proof_aggregate"], lambda x: x["claims"][0].update(kind="runtime")
        )
        history, _, _ = self.f.run()
        self.assertEqual(history["component_copies"][key]["current_disposition"], "OPEN")

    def test_version_change_candidates_are_enumerated_open(self):
        ref = self.f.stage_rows[0]["evidence"]
        self.f.update(
            ref["syft"],
            lambda x: x["artifacts"][0].update(version="2.0", purl="pkg:generic/demo@2.0"),
        )
        self.f.update(
            ref["inventory"],
            lambda x: [
                a.update(version="2.0", purl="pkg:generic/demo@2.0") for a in x if a["id"] == "demo"
            ],
        )
        history, _, _ = self.f.run()
        mapped = next(
            c
            for c in history["component_copies"].values()
            if c["historical_copy"]["component"]["name"] == "demo"
        )
        self.assertEqual(mapped["current_disposition"], "OPEN")
        self.assertEqual(mapped["unverified_coordinate_candidates"][0]["version"], "2.0")

    def test_affected_and_unsupported_ranges_never_clear(self):
        self.assertEqual(
            r.range_evaluation("1.11.4", "<= 1.11.3"),
            "verified-installed-version-not-in-affected-range",
        )
        self.assertEqual(r.range_evaluation("1.11.4", "<= 9.0.0"), "OPEN_INSTALLED_IN_RANGE")
        self.assertEqual(
            r.range_evaluation("1.11.4", "unrecognized range"), "OPEN_UNSUPPORTED_RANGE"
        )

    def test_cross_case_lz4_hash_drift_remains_open(self):
        for row in self.f.stage_rows[2:4]:
            self.f.update(row["evidence"]["packaged"], lambda x: x[0].update(sha256="0" * 64))
        _, vendor, _ = self.f.run()
        self.assertTrue(
            all(
                x["current_disposition"] == "OPEN"
                and "cross-case-lz4-jar-hashes-differ" in x["gaps"]
                for x in vendor["rows"]
                if x["id"] in r.LZ4
            )
        )

    def test_no_fabricated_behavior_jar_hash_required(self):
        history, vendor, _ = self.f.run()
        for claim in history["proof_claims"].values():
            if claim["kind"] in ("lz4-default", "lz4-jni"):
                self.assertNotIn("library_sha256", claim)
                self.assertFalse(claim["retained_behavior"]["production_image_equivalence"])
        for row in vendor["rows"]:
            if row["id"] in r.LZ4:
                self.assertEqual(
                    row["current_applicability_conclusion"],
                    "verified-installed-version-not-in-affected-range",
                )
                self.assertEqual(len(row["behavior_hash_link_limitations"]), 2)
                self.assertFalse(row["native_clearance"])

    def test_declared_hash_without_retained_support_is_incomplete(self):
        self.f.update(
            self.f.manifest["proof_aggregate"],
            lambda x: x["claims"][-1].update(library_sha256="e" * 64),
        )
        with self.assertRaises(KeyError):
            self.f.run()

    def test_declared_conflicting_optional_hash_is_incomplete(self):
        witness = self.f.save("retained-behavior-jar-hash.json", {"jar_sha256": "0" * 64})
        self.f.update(
            self.f.manifest["proof_aggregate"],
            lambda x: x["claims"][-1].update(
                library_sha256="e" * 64,
                library_hash_evidence={"evidence": witness, "pointer": "/jar_sha256"},
            ),
        )
        with self.assertRaisesRegex(r.Invalid, "unsupported/conflicting"):
            self.f.run()

    def test_optional_supported_hash_conflicting_with_campaign_is_incomplete(self):
        witness = self.f.save("retained-behavior-jar-hash.json", {"jar_sha256": "0" * 64})
        self.f.update(
            self.f.manifest["proof_aggregate"],
            lambda x: x["claims"][-1].update(
                library_sha256="0" * 64,
                library_hash_evidence={"evidence": witness, "pointer": "/jar_sha256"},
            ),
        )
        with self.assertRaisesRegex(r.Invalid, "behavior/campaign JAR hash conflicts"):
            self.f.run()

    def test_optional_actually_supported_matching_hash_is_accepted(self):
        witness = self.f.save("retained-behavior-jar-hash.json", {"jar_sha256": "e" * 64})
        self.f.update(
            self.f.manifest["proof_aggregate"],
            lambda x: x["claims"][-1].update(
                library_sha256="e" * 64,
                library_hash_evidence={"evidence": witness, "pointer": "/jar_sha256"},
            ),
        )
        _, vendor, _ = self.f.run()
        self.assertTrue(
            all(
                row["current_disposition"] == "supported-candidate/OPEN"
                for row in vendor["rows"]
                if row["id"] in r.LZ4
            )
        )

    def test_applicability_does_not_require_behavior_claims(self):
        def source_only(value):
            value["claims"] = [
                c for c in value["claims"] if c["kind"] not in ("lz4-default", "lz4-jni")
            ]
            value["requirements"] = [c["id"] for c in value["claims"]]

        self.f.update(self.f.manifest["proof_aggregate"], source_only)
        _, vendor, _ = self.f.run()
        for row in vendor["rows"]:
            if row["id"] in r.LZ4:
                self.assertEqual(
                    row["current_applicability_conclusion"],
                    "verified-installed-version-not-in-affected-range",
                )
                self.assertTrue(row["behavior_proof_gaps"])


if __name__ == "__main__":
    unittest.main()
