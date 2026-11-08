"""Deterministic synthetic controls only; never execute real proof modules."""

import argparse
import contextlib
import copy
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts import summarize_generated_image_proofs as summary

HERE = Path(__file__).resolve().parent


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return summary.digest(data)


def put(path, value):
    return write(path, (json.dumps(value, sort_keys=True) + "\n").encode())


def app_files(app, proof=False):
    result = {
        "pom.xml": write(app / "pom.xml", b"<project/>"),
        "Dockerfile": write(app / "Dockerfile", b"FROM synthetic\n"),
    }
    if not proof:
        name = "src/test/java/example/EmittedTest.java"
        result[name] = write(app / name, b"// synthetic emitted test source\n")
    return result


def compatibility_fixture(root, prior):
    rows = []
    for case in sorted(summary.CASES):
        reuse = case in summary.REUSED
        directory = (prior if reuse else root) / "cases" / case
        proof, app = directory / "proof", directory / "isolated-app"
        supplied = case.startswith("kafka-")
        pristine = app_files(app, proof=supplied)
        added = {}
        if supplied:
            name = "src/test/java/proof/KafkaGeneratedContractTest.java"
            added[name] = write(app / name, b"// synthetic supplied test source\n")
        after = {**pristine, **added}
        class_name = "proof.KafkaGeneratedContractTest" if supplied else "example.EmittedTest"
        methods = ["contract" + str(i) for i in range(13)] if supplied else ["contextLoads"]
        counters = {"tests": len(methods), "failures": 0, "errors": 0, "skipped": 0}
        report_name = "target/surefire-reports/TEST-" + class_name + ".xml"
        xml = ET.Element("testsuite", name=class_name, **{k: str(v) for k, v in counters.items()})
        for method in methods:
            ET.SubElement(xml, "testcase", classname=class_name, name=method)
        xml_sha = write(app / report_name, ET.tostring(xml))
        suite = {
            "name": class_name,
            "report": report_name,
            "sha256": xml_sha,
            **{k: str(v) for k, v in counters.items()},
            "testcases": [{"classname": class_name, "name": method} for method in methods],
        }
        put(proof / "executed-tests.json", {"counts": counters, "suites": [suite]})
        before_sha = put(proof / "source-before.json", pristine)
        put(proof / "source-after.json", after)
        put(
            proof / "proof-test-origin.json",
            {
                "origin": "proof-supplied" if supplied else "engine-emitted",
                "added_sources": added,
                "pristine_source_inventory": pristine,
                "instrumented_before_maven": after,
                "pristine_production_unchanged": True,
            },
        )
        row = {
            "case": case,
            "reused": reuse,
            "generator_sha": summary.SOURCE,
            "tested_sha": summary.SOURCE,
            "source_unchanged": True,
            "packaged_policy": "passed",
            "source_and_packaged_independence": True,
            "platform": "linux/amd64",
            "java": summary.JDK[case[-2:]],
            "maven": "3.9.16",
            "source_inventory_digest": summary.inv_digest(after),
            "jar_sha256": "1" * 64,
            "builder_reference": "maven@sha256:" + "2" * 64,
            "proof_supplied_sources": added,
            "pristine_production_unchanged": True,
            "test_origin": "proof-supplied" if supplied else "engine-emitted",
            "executed_tests": counters,
        }
        original_hash = put(proof / "receipt.json", row)
        if reuse:
            row.update(
                prior_receipt_sha256=original_hash,
                pristine_inventory_sha256=before_sha,
                app_pom_sha256=pristine["pom.xml"],
                recipe_sha256=pristine["Dockerfile"],
            )
        rows.append(row)
    value = {
        "status": "eight-case-compatibility-complete",
        "exit_code": 0,
        "source_sha": summary.SOURCE,
        "generator_sha": summary.SOURCE,
        "tested_sha": summary.SOURCE,
        "source_status": "",
        "no_production_pom_dependency_recipe_changes": True,
        "reused_cases": [r for r in rows if r["reused"]],
        "fresh_cases": [r for r in rows if not r["reused"]],
        "total_executed_tests": 32,
        "execution_ordinal": 7,
        "cumulative_helper_repair_cycles": 5,
    }
    put(root / "receipt.json", value)


def runtime_fixture(root, source_root, mode):
    module_name = "scripts/smoke/synthetic_" + mode.replace("-", "_") + ".py"
    helper_hash = write(source_root / module_name, b"# synthetic module, never executed\n")
    rows, infrastructure = [], ""
    for java in ("17", "21"):
        app = root / ("app-j" + java)
        pristine = {
            "pom.xml": write(app / "pom.xml", b"<project/>"),
            "Dockerfile": write(app / "Dockerfile", b"FROM synthetic\n"),
        }
        observer = "src/main/java/proof/Observer.java"
        instrumented = {**pristine, observer: write(app / observer, b"// synthetic observer\n")}
        image_id = "sha256:" + ("1" if java == "17" else "2") * 64
        row = {
            "java": java,
            "profile": "springboot-legacy-compatible"
            if java == "17"
            else "springboot-standard-enterprise",
            "platform": "linux/amd64",
            "user": "edgeforge",
            "image_id": image_id,
            "pom_sha256": pristine["pom.xml"],
            "dockerfile_sha256": pristine["Dockerfile"],
            "runtime_log": "runtime-j" + java + ".log",
        }
        if mode == "default":
            impl = {
                "kafka_default_compression_level": 9,
                "kafka_compression_level_source": "CompressionType.LZ4.defaultLevel()",
                "native_loaded_after_traffic": False,
                "native_loaded_after_observation": False,
                "compressor": "net.jpountz.lz4.SyntheticJavaCompressor",
            }
            wire = {
                "key": "default-" "lz4-synthetic",
                "input": {"paymentId": "default-lz4-synthetic"},
                "output": {"entryId": "default-lz4-synthetic", "amountMinorUnits": 1234},
                "input_compression": "lz4",
                "output_partition_key_strategy": "round_robin",
                "output_partition_key": None,
            }
            obs = {
                "java": summary.JDK[java],
                "uid": 999,
                "os": "Linux",
                "arch": "amd64",
                "java_command": "/app/app.jar",
                "jvm_args": [],
                "implementations": impl,
                "roundtrip": wire,
            }
            row.update(
                exit_code=0,
                production_unchanged=True,
                entrypoint=["java", "-jar", "/app/app.jar"],
                process=["java", "-jar", "/app/app.jar"],
                observation=obs,
                production_sha256=summary.inv_digest(pristine),
                instrumented_sha256=summary.inv_digest(instrumented),
                observer_path=observer,
                observer_sha256=instrumented[observer],
            )
            write(
                root / row["runtime_log"], ("LZ4_DEFAULT_PROOF " + json.dumps(obs) + "\n").encode()
            )
            put(
                root / ("container-j" + java + ".json"),
                {
                    "Image": image_id,
                    "State": {"ExitCode": 0, "Running": False},
                    "Path": "java",
                    "Args": ["-jar", "/app/app.jar"],
                    "Config": {"User": "edgeforge"},
                },
            )
        else:
            row.update(
                native_and_roundtrip="passed",
                lz4="1.11.4",
                source_sha256=summary.inv_digest(instrumented),
            )
            write(
                root / row["runtime_log"],
                (
                    "LZ4_NATIVE_PROOF java="
                    + summary.JDK[java]
                    + " uid=999 lz4=JNI sha256="
                    + "3" * 64
                    + " mappings=[synthetic-native-map]\nLZ4_ROUNDTRIP_PROOF compression.type=lz4 input=synthetic\n"
                ).encode(),
            )
            infrastructure += (
                "$ docker image inspect synthetic-j"
                + java
                + "\n"
                + json.dumps(
                    [
                        {
                            "Id": image_id,
                            "Os": "linux",
                            "Architecture": "amd64",
                            "Config": {"User": "edgeforge"},
                        }
                    ]
                )
                + "\n"
            )
        rows.append(row)
    if mode != "default":
        write(root / "infrastructure.log", infrastructure.encode())
    value = {
        "complete": True,
        "source_sha": summary.SOURCE,
        "source_dirty": False,
        "image_security_clearance": False,
        "proof_source_hashes": {module_name: helper_hash},
        "cases": rows,
    }
    if mode == "default":
        value.update(status="passed", approved_source_sha=summary.SOURCE)
    put(root / "receipt.json", value)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-summary-", dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compat, self.prior, self.source = (
            self.root / n for n in ("compat", "prior", "source")
        )
        self.default, self.native = self.root / "default", self.root / "native"
        compatibility_fixture(self.compat, self.prior)
        runtime_fixture(self.default, self.source, "default")
        runtime_fixture(self.native, self.source, "explicit-native")

    def run_summary(self):
        return summary.summarize(
            self.compat / "receipt.json",
            self.prior,
            self.default / "receipt.json",
            self.native / "receipt.json",
            self.source,
        )

    def mutate(self, path, fn):
        value = json.loads(path.read_bytes())
        fn(value)
        put(path, value)

    def reject(self):
        with self.assertRaises(ValueError):
            self.run_summary()

    def test_positive_deterministic_reconstruction_no_host_paths(self):
        first, text = self.run_summary()
        second, other = self.run_summary()
        self.assertEqual(first, second)
        self.assertEqual(text, other)
        self.assertEqual(
            first["compatibility"]["totals_reconstructed_from_methods"],
            {"engine-emitted": 6, "proof-supplied": 26},
        )
        self.assertEqual(len(first["compatibility"]["cases"]), 8)
        self.assertNotIn(str(self.root), json.dumps(first))
        self.assertFalse(first["goal_complete"])
        self.assertEqual(first["runtime_default"]["cases"][0]["actual_uid"], 999)
        self.assertIn(
            "pristine", first["runtime_explicit_native"]["cases"][0]["production_unchanged"]
        )

    def test_zero_tests_reject(self):
        self.mutate(
            self.compat / "receipt.json",
            lambda r: r["fresh_cases"][0]["executed_tests"].update(tests=0),
        )
        self.reject()

    def test_skipped_tests_reject(self):
        self.mutate(
            self.compat / "receipt.json",
            lambda r: r["fresh_cases"][0]["executed_tests"].update(skipped=1),
        )
        self.reject()

    def test_error_tests_reject(self):
        self.mutate(
            self.compat / "receipt.json",
            lambda r: r["fresh_cases"][0]["executed_tests"].update(errors=1),
        )
        self.reject()

    def test_wrong_total_not_sole_proof(self):
        self.mutate(self.compat / "receipt.json", lambda r: r.update(total_executed_tests=33))
        self.reject()

    def test_missing_case_reject(self):
        self.mutate(self.compat / "receipt.json", lambda r: r["fresh_cases"].pop())
        self.reject()

    def test_duplicate_case_reject(self):
        self.mutate(
            self.compat / "receipt.json",
            lambda r: r["fresh_cases"].__setitem__(0, copy.deepcopy(r["fresh_cases"][1])),
        )
        self.reject()

    def test_dirty_frozen_source_reject(self):
        self.mutate(self.compat / "receipt.json", lambda r: r.update(source_status="dirty"))
        self.reject()

    def test_changed_junit_bytes_reject(self):
        xml = next(
            (self.prior / "cases/crud-h2-j17/isolated-app/target/surefire-reports").glob("*.xml")
        )
        xml.write_bytes(b"<testsuite/>")
        self.reject()

    def test_changed_pom_reject(self):
        (self.compat / "cases/kafka-pg-j17/isolated-app/pom.xml").write_text("changed")
        self.reject()

    def test_changed_supplied_source_reject(self):
        (
            self.compat
            / "cases/kafka-pg-j17/isolated-app/src/test/java/proof/KafkaGeneratedContractTest.java"
        ).write_text("changed")
        self.reject()

    def test_changed_reused_receipt_reject(self):
        self.mutate(
            self.prior / "cases/crud-h2-j17/proof/receipt.json", lambda r: r.update(extra="changed")
        )
        self.reject()

    def test_missing_original_xml_explicitly_limited_not_invented(self):
        xml = next(
            (self.prior / "cases/crud-h2-j17/isolated-app/target/surefire-reports").glob("*.xml")
        )
        xml.unlink()
        value, _ = self.run_summary()
        self.assertTrue(
            any("surefire-reports" in r for r in value["unavailable_preimages_or_bindings"])
        )

    def test_incomplete_runtime_reject(self):
        self.mutate(self.default / "receipt.json", lambda r: r.update(complete=False))
        self.reject()

    def test_dirty_runtime_reject(self):
        self.mutate(self.native / "receipt.json", lambda r: r.update(source_dirty=True))
        self.reject()

    def test_duplicate_jdk_runtime_reject(self):
        self.mutate(
            self.native / "receipt.json",
            lambda r: r["cases"].__setitem__(1, copy.deepcopy(r["cases"][0])),
        )
        self.reject()

    def test_default_root_uid_reject(self):
        self.mutate(
            self.default / "receipt.json", lambda r: r["cases"][0]["observation"].update(uid=0)
        )
        self.reject()

    def test_native_log_uid_reject(self):
        log = self.native / "runtime-j17.log"
        log.write_bytes(log.read_bytes().replace(b"uid=999", b"uid=0"))
        self.reject()

    def test_native_wrong_actual_jdk_reject(self):
        log = self.native / "runtime-j17.log"
        log.write_bytes(log.read_bytes().replace(b"java=17.0.20.1", b"java=17.0.1"))
        self.reject()

    def test_runtime_module_hash_reject(self):
        (self.source / "scripts/smoke/synthetic_default.py").write_text("changed")
        self.reject()

    def test_default_log_observation_mismatch_reject(self):
        (self.default / "runtime-j17.log").write_text("LZ4_DEFAULT_PROOF {}\n")
        self.reject()

    def test_native_missing_roundtrip_reject(self):
        log = self.native / "runtime-j17.log"
        log.write_bytes(log.read_bytes().split(b"LZ4_ROUNDTRIP_PROOF")[0])
        self.reject()

    def test_native_image_binding_reject(self):
        log = self.native / "infrastructure.log"
        log.write_bytes(log.read_bytes().replace(b'"User": "edgeforge"', b'"User": "root"'))
        self.reject()

    def test_default_container_binding_reject(self):
        self.mutate(
            self.default / "container-j17.json", lambda r: r.update(Image="sha256:" + "9" * 64)
        )
        self.reject()

    def test_runtime_pom_changed_reject(self):
        (self.native / "app-j17/pom.xml").write_text("changed")
        self.reject()

    def test_output_host_path_not_exported(self):
        self.mutate(
            self.compat / "receipt.json",
            lambda r: r["fresh_cases"][0].update(builder_reference="/" "Users/secret"),
        )
        self.reject()

    def test_cli_output_new_and_sanitized(self):
        args = [
            "--compatibility-receipt",
            str(self.compat / "receipt.json"),
            "--reused-root",
            str(self.prior),
            "--default-receipt",
            str(self.default / "receipt.json"),
            "--native-receipt",
            str(self.native / "receipt.json"),
            "--source-root",
            str(self.source),
            "--output-dir",
            str(self.root / "output"),
        ]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(summary.main(args), 0)
            original = (self.root / "output/proof-summary.json").read_bytes()
            self.assertEqual(summary.main(args), 2)
            self.assertEqual((self.root / "output/proof-summary.json").read_bytes(), original)
        self.assertNotIn(str(self.root).encode(), original)

    def test_outer_runtime_runner_receipt_hash_binding(self):
        runner = self.root / "runner-receipt.json"
        value = {
            "status": "passed",
            "generator_sha": summary.SOURCE,
            "existing_proof_modules_changed": False,
            "owned_builder_cleanup_exit_code": 0,
            "proofs": [
                {
                    "label": label,
                    "exit_code": 0,
                    "receipt_sha256": summary.digest((root / "receipt.json").read_bytes()),
                }
                for label, root in (("default", self.default), ("explicit-native", self.native))
            ],
        }
        put(runner, value)
        result, _ = summary.summarize(
            self.compat / "receipt.json",
            self.prior,
            self.default / "receipt.json",
            self.native / "receipt.json",
            self.source,
            runner,
        )
        self.assertEqual(result["runtime_runner"]["status"], "passed")
        value["proofs"][0]["receipt_sha256"] = "0" * 64
        put(runner, value)
        with self.assertRaises(ValueError):
            summary.summarize(
                self.compat / "receipt.json",
                self.prior,
                self.default / "receipt.json",
                self.native / "receipt.json",
                self.source,
                runner,
            )

    def test_aggregate_failure_and_wrong_origin_reject(self):
        path = self.compat / "receipt.json"
        original = json.loads(path.read_bytes())
        changed = copy.deepcopy(original)
        changed["fresh_cases"][0]["executed_tests"]["failures"] = 1
        put(path, changed)
        self.reject()
        changed = copy.deepcopy(original)
        next(row for row in changed["fresh_cases"] if row["test_origin"] == "proof-supplied")[
            "test_origin"
        ] = "engine-emitted"
        put(path, changed)
        self.reject()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=HERE / "synthetic-receipt.json")
    args = parser.parse_args()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SummaryTests)
    )
    print(stream.getvalue(), end="")
    with args.receipt.with_suffix(".log").open("x") as output:
        output.write(stream.getvalue())
    with args.receipt.open("x") as output:
        json.dump(
            {
                "status": "passed" if result.wasSuccessful() else "failed",
                "tests": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "runtime_proof_credit": False,
                "real_receipts_summarized": False,
                "docker_network_calls": 0,
                "summarizer_sha256": summary.digest((HERE / "summarize_proofs.py").read_bytes()),
                "tests_sha256": summary.digest(Path(__file__).read_bytes()),
                "revision2_cycle": "2/3",
                "cumulative_repairs": 6,
                "independent_review_rounds": 0,
            },
            output,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")
    raise SystemExit(0 if result.wasSuccessful() else 2)
