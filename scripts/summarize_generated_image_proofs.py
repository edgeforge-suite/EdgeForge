"""Read-only compatibility/default/native proof summarizer; no proof execution."""

import argparse
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath

SOURCE = "c8798275065a8a0b619046707fad053f8a9b9ad1"
CASES = {
    "crud-h2-j17",
    "crud-soap-h2-j17",
    "passthrough-pg-j17",
    "kafka-pg-j17",
    "crud-pg-j21",
    "crud-soap-pg-j21",
    "passthrough-pg-j21",
    "kafka-pg-j21",
}
REUSED = {"crud-h2-j17", "crud-soap-h2-j17", "passthrough-pg-j17"}
JDK = {"17": "17.0.20.1", "21": "21.0.12.1"}
HEX = r"[0-9a-f]{64}"
LIMIT = 32 * 1024**2


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inv_digest(value):
    return digest(json.dumps(value, sort_keys=True).encode())


def relative(value):
    require(
        isinstance(value, str)
        and value
        and "\\" not in value
        and not PurePosixPath(value).is_absolute()
        and all(p not in {"", ".", ".."} for p in value.split("/")),
        "unsafe evidence reference",
    )
    return value


def hashed(value):
    require(isinstance(value, str) and re.fullmatch(HEX, value), "invalid SHA256")
    return value


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=pairs)


class Evidence:
    def __init__(self):
        self.hashes, self.unavailable = {}, []

    def read(self, root, name, label, *, optional=False):
        relative(name)
        path = Path(root) / name
        for parent in (path, *path.parents):
            require(not parent.is_symlink(), "linked evidence")
        if optional and not path.exists():
            self.unavailable.append(label)
            return None
        require(path.is_file() and path.stat().st_size <= LIMIT, "missing/oversized evidence")
        data = path.read_bytes()
        self.hashes[label] = digest(data)
        return data

    def json(self, root, name, label):
        return decode(self.read(root, name, label))

    def inventory(self, app, expected, label):
        require(
            isinstance(expected, dict) and {"pom.xml", "Dockerfile"} <= expected.keys(),
            "missing pristine POM/recipe inventory",
        )
        for name, sha in expected.items():
            relative(name)
            hashed(sha)
        if not app.is_dir():
            self.unavailable.append(label + "/current-source-tree")
            return "recorded inventory only; current source preimage unavailable"
        actual = {}
        for parent, dirs, files in os.walk(app, followlinks=False):
            directory = Path(parent)
            if directory == app:
                dirs[:] = [d for d in dirs if d not in {"target", ".git"}]
                files = [f for f in files if f != ".git"]
            require(not any((directory / d).is_symlink() for d in dirs), "linked source directory")
            for filename in files:
                name = (directory / filename).relative_to(app).as_posix()
                actual[name] = digest(self.read(app, name, label + "/" + name))
        require(actual == expected, "actual source differs from recorded inventory")
        return "all current source/config/POM/recipe bytes verified"


def counts(value):
    require(
        isinstance(value, dict)
        and all(type(value.get(k)) is int for k in ("tests", "errors", "failures", "skipped")),
        "invalid test counters",
    )
    require(
        value["tests"] > 0 and all(value[k] == 0 for k in ("errors", "failures", "skipped")),
        "zero/nonpassing tests",
    )
    return {key: value[key] for key in ("tests", "errors", "failures", "skipped")}


def compatibility(e, path, reused_root):
    root = path.parent
    value = e.json(root, path.name, "compatibility/receipt.json")
    require(
        value.get("status") == "eight-case-compatibility-complete" and value.get("exit_code") == 0,
        "compatibility incomplete",
    )
    require(
        all(value.get(k) == SOURCE for k in ("source_sha", "generator_sha", "tested_sha"))
        and value.get("source_status") == "",
        "compatibility source not clean/frozen",
    )
    require(
        value.get("no_production_pom_dependency_recipe_changes") is True
        and not value.get("cleanup_errors"),
        "compatibility mutation/cleanup failure",
    )
    reused, fresh = value["reused_cases"], value["fresh_cases"]
    require(
        len(reused) == 3 and len(fresh) == 5 and {r["case"] for r in reused} == REUSED,
        "wrong reuse/fresh scope",
    )
    rows = reused + fresh
    require(len(rows) == 8 and {r["case"] for r in rows} == CASES, "duplicate/missing cases")
    output, totals = [], Counter()
    for row in sorted(rows, key=lambda item: item["case"]):
        case = row["case"]
        reuse = case in REUSED
        require(
            row.get("reused") is reuse
            and row.get("generator_sha") == row.get("tested_sha") == SOURCE
            and row.get("source_unchanged") is True
            and row.get("packaged_policy") == "passed"
            and row.get("source_and_packaged_independence") is True,
            "invalid case identity/source",
        )
        require(
            row.get("platform") == "linux/amd64"
            and row.get("java") == JDK[case[-2:]]
            and row.get("maven") == "3.9.16",
            "wrong compatibility toolchain",
        )
        label = "compatibility/" + ("reused/" if reuse else "fresh/") + case
        directory = (reused_root if reuse else root) / "cases" / case
        proof, app = directory / "proof", directory / "isolated-app"
        original = e.read(proof, "receipt.json", label + "/receipt.json")
        prior = decode(original)
        if reuse:
            require(
                digest(original) == row.get("prior_receipt_sha256"),
                "reused original receipt hash mismatch",
            )
        require(
            prior.get("generator_sha") == prior.get("tested_sha") == SOURCE
            and prior.get("source_unchanged") is True,
            "original case source mismatch",
        )
        require(
            prior.get("case") == case
            and prior.get("source_inventory_digest") == row.get("source_inventory_digest"),
            "original case/source binding mismatch",
        )
        original_counts = prior.get("executed_tests", prior.get("generated_tests"))
        require(
            counts(original_counts) == counts(row["executed_tests"]),
            "original case test count mismatch",
        )
        before = e.json(proof, "source-before.json", label + "/source-before.json")
        after = e.json(proof, "source-after.json", label + "/source-after.json")
        if reuse:
            require(
                e.hashes[label + "/source-before.json"] == row.get("pristine_inventory_sha256"),
                "reuse inventory hash mismatch",
            )
            pristine, added = before, {}
            require(before == after, "reused source changed")
        else:
            origin = e.json(proof, "proof-test-origin.json", label + "/proof-test-origin.json")
            pristine, added = origin["pristine_source_inventory"], origin["added_sources"]
            require(
                origin.get("pristine_production_unchanged") is True
                and row.get("pristine_production_unchanged") is True
                and origin["instrumented_before_maven"] == after
                and origin.get("origin") == row.get("test_origin"),
                "fresh pristine/origin mismatch",
            )
            require(pristine == before, "pristine before inventory mismatch")
            require(row.get("proof_supplied_sources") == added, "proof-supplied source mismatch")
        require(
            all(
                name.startswith("src/test/java/proof/") and name.endswith("Test.java")
                for name in added
            ),
            "non-test proof injection",
        )
        require(
            not (set(pristine) & set(added)) and after == {**pristine, **added},
            "production source/POM/recipe mutation",
        )
        require(
            inv_digest(after) == row["source_inventory_digest"], "source inventory digest mismatch"
        )
        actual_sources = e.inventory(app, after, label + "/source")
        for name, sha in (
            ("pom.xml", row.get("app_pom_sha256")),
            ("Dockerfile", row.get("recipe_sha256")),
        ):
            if sha is not None:
                require(pristine[name] == sha, "POM/recipe binding mismatch")
        executed = e.json(proof, "executed-tests.json", label + "/executed-tests.json")
        expected = counts(row["executed_tests"])
        require(counts(executed["counts"]) == expected, "case/executed test counters mismatch")
        methods, reports = [], []
        for suite in executed["suites"]:
            suite_counts = counts({k: int(suite[k]) for k in expected})
            tests = suite["testcases"]
            require(len(tests) == suite_counts["tests"], "suite count does not match methods")
            names = [(t["classname"], t["name"]) for t in tests]
            require(
                len(names) == len(set(names)) and all(c == suite["name"] and n for c, n in names),
                "invalid/duplicate class methods",
            )
            xml = e.read(
                app, relative(suite["report"]), label + "/" + suite["report"], optional=True
            )
            hashed(suite["sha256"])
            if xml is not None:
                require(digest(xml) == suite["sha256"], "original JUnit hash mismatch")
                tree = ET.fromstring(xml)
                require(
                    tree.tag == "testsuite"
                    and tree.get("name") == suite["name"]
                    and {k: int(tree.attrib[k]) for k in expected} == suite_counts,
                    "original JUnit counters/class mismatch",
                )
                require(
                    not any(tree.findall(".//" + tag) for tag in ("error", "failure", "skipped")),
                    "nonpassing original JUnit",
                )
                require(
                    Counter((t.get("classname"), t.get("name")) for t in tree.findall("testcase"))
                    == Counter(names),
                    "original JUnit methods mismatch",
                )
            methods.extend(names)
            reports.append(
                {
                    "reference": label + "/" + suite["report"],
                    "sha256": suite["sha256"],
                    "verification": "original bytes verified"
                    if xml is not None
                    else "recorded hash; original unavailable",
                }
            )
        require(
            len(methods) == expected["tests"] and len(methods) == len(set(methods)),
            "case methods mismatch",
        )
        origin = row["test_origin"]
        require(
            origin == ("proof-supplied" if added else "engine-emitted")
            and all(c.startswith("proof.") == bool(added) for c, _ in methods),
            "test origin/class mismatch",
        )
        if added:
            source_classes = {"proof." + PurePosixPath(name).stem for name in added}
            require(
                {c for c, _ in methods} <= source_classes,
                "proof classes not bound to added sources",
            )
        totals[origin] += len(methods)
        output.append(
            {
                "case": case,
                "reused": reuse,
                "origin": origin,
                "counts": expected,
                "classes_methods": [{"class": c, "method": n} for c, n in sorted(methods)],
                "reports": reports,
                "proof_supplied_sources": added,
                "pristine_production_pom_recipe_unchanged": True,
                "current_source_check": actual_sources,
                "pom_sha256": pristine["pom.xml"],
                "recipe_sha256": pristine["Dockerfile"],
                "source_inventory_digest": row["source_inventory_digest"],
                "java": row["java"],
                "maven": row["maven"],
                "platform": row["platform"],
                "builder_reference": row["builder_reference"],
                "jar_sha256": hashed(row["jar_sha256"]),
            }
        )
    require(
        dict(totals) == {"engine-emitted": 6, "proof-supplied": 26}
        and sum(totals.values()) == value["total_executed_tests"],
        "reconstructed origin totals mismatch",
    )
    return {
        "status": "validated-completed-compatibility",
        "reused_cases": 3,
        "fresh_cases": 5,
        "totals_reconstructed_from_methods": dict(totals),
        "total_tests": sum(totals.values()),
        "cases": output,
        "receipt_reference": "compatibility/receipt.json",
        "historical_execution_ordinal": value["execution_ordinal"],
        "historical_cumulative_repairs": value["cumulative_helper_repair_cycles"],
    }


def runtime_sources(e, root, value, label, source_root):
    hashes = value.get("proof_source_hashes")
    require(isinstance(hashes, dict) and hashes, "missing runtime module/source identities")
    for name, expected in hashes.items():
        hashed(expected)
        raw = e.read(source_root, relative(name), label + "/module-source/" + name, optional=True)
        if raw is not None:
            require(digest(raw) == expected, "runtime module/source hash mismatch")
    return dict(sorted(hashes.items()))


def runtime(e, path, mode, source_root):
    root, label = path.parent, "runtime/" + mode
    value = e.json(root, path.name, label + "/receipt.json")
    require(
        value.get("complete") is True
        and value.get("source_sha") == SOURCE
        and value.get("source_dirty") is False
        and value.get("image_security_clearance") is False
        and not value.get("cleanup_errors"),
        "incomplete/dirty runtime proof",
    )
    if mode == "default":
        require(
            value.get("status") == "passed" and value.get("approved_source_sha") == SOURCE,
            "default approval/status mismatch",
        )
    rows = value.get("cases", [])
    require(
        len(rows) == 2 and {r.get("java") for r in rows} == set(JDK),
        "missing/duplicate runtime Java cases",
    )
    modules = runtime_sources(e, root, value, label, source_root)
    output = []
    for row in sorted(rows, key=lambda r: r["java"]):
        java = row["java"]
        require(
            row.get("platform") == "linux/amd64"
            and row.get("user") == "edgeforge"
            and re.fullmatch("sha256:" + HEX, row.get("image_id", "")),
            "wrong runtime image/platform/user",
        )
        item = {
            "java_target": java,
            "platform": row["platform"],
            "image_id": row["image_id"],
            "image_user": row["user"],
            "pom_sha256": hashed(row["pom_sha256"]),
            "recipe_sha256": hashed(row["dockerfile_sha256"]),
        }
        require(
            row.get("profile")
            == (
                "springboot-legacy-compatible" if java == "17" else "springboot-standard-enterprise"
            ),
            "runtime profile mismatch",
        )
        item["profile"] = row["profile"]
        log_name = relative(row["runtime_log"])
        require(log_name == "runtime-j" + java + ".log", "wrong runtime log link")
        log = e.read(root, log_name, label + "/" + log_name).decode()
        app = root / ("app-j" + java)
        if mode == "default":
            obs = row["observation"]
            require(
                row.get("exit_code") == 0
                and row.get("production_unchanged") is True
                and row.get("entrypoint") == row.get("process") == ["java", "-jar", "/app/app.jar"],
                "default launch/source changed",
            )
            require(
                obs.get("java") == JDK[java]
                and type(obs.get("uid")) is int
                and obs["uid"] > 0
                and obs.get("java_command") == "/app/app.jar"
                and obs.get("jvm_args") == []
                and (obs.get("os"), obs.get("arch")) == ("Linux", "amd64"),
                "default actual JDK/UID/launcher mismatch",
            )
            lines = [
                line[len("LZ4_DEFAULT_PROOF ") :]
                for line in log.splitlines()
                if line.startswith("LZ4_DEFAULT_PROOF ")
            ]
            require(
                len(lines) == 1 and decode(lines[0]) == obs, "default raw log/observation mismatch"
            )
            impl, wire = obs["implementations"], obs["roundtrip"]
            require(
                impl.get("kafka_default_compression_level") == 9
                and impl.get("kafka_compression_level_source")
                == "CompressionType.LZ4.defaultLevel()"
                and type(impl.get("native_loaded_after_traffic")) is bool
                and impl.get("native_loaded_after_traffic")
                == impl.get("native_loaded_after_observation"),
                "default compression/native observation mismatch",
            )
            require(
                wire.get("input_compression") == "lz4"
                and wire.get("output_partition_key_strategy") == "round_robin"
                and "output_partition_key" in wire
                and wire["output_partition_key"] is None,
                "default roundtrip configuration mismatch",
            )
            require(
                wire.get("input", {}).get("paymentId")
                == wire.get("key")
                == wire.get("output", {}).get("entryId")
                and wire.get("output", {}).get("amountMinorUnits") == 1234,
                "default correlated mapping mismatch",
            )
            item.update(
                actual_jdk=obs["java"],
                actual_uid=obs["uid"],
                launch=row["entrypoint"],
                production_unchanged="validated runner assertion; inventory digest bound",
                production_sha256=hashed(row["production_sha256"]),
                instrumented_sha256=hashed(row["instrumented_sha256"]),
                observer_sha256=hashed(row["observer_sha256"]),
                observer_path=relative(row["observer_path"]),
                implementations=impl,
                roundtrip=wire,
            )
            container_raw = e.read(
                root,
                "container-j" + java + ".json",
                label + "/container-j" + java + ".json",
                optional=True,
            )
            if container_raw is not None:
                container = decode(container_raw)
                require(
                    container.get("Image") == row["image_id"]
                    and container.get("State", {}).get("ExitCode") == 0
                    and not container["State"].get("Running")
                    and not container["State"].get("OOMKilled")
                    and [container.get("Path"), *container.get("Args", [])] == row["process"]
                    and container.get("Config", {}).get("User") == "edgeforge",
                    "default created image/config mismatch",
                )
                item["image_configuration_sha256"] = inv_digest(container["Config"])
            if app.is_dir():
                current = current_inventory(e, app, label + "/app-j" + java)
                require(
                    inv_digest(current) == row["instrumented_sha256"],
                    "default instrumented source digest mismatch",
                )
                observer = row["observer_path"]
                require(
                    current.get(observer) == row["observer_sha256"]
                    and inv_digest({k: v for k, v in current.items() if k != observer})
                    == row["production_sha256"],
                    "default pristine production digest mismatch",
                )
                require(
                    current["pom.xml"] == row["pom_sha256"]
                    and current["Dockerfile"] == row["dockerfile_sha256"],
                    "default POM/recipe mismatch",
                )
            else:
                e.unavailable.append(label + "/app-j" + java + "/current-source-tree")
        else:
            require(
                row.get("native_and_roundtrip") == "passed" and row.get("lz4") == "1.11.4",
                "native roundtrip incomplete",
            )
            native = [line for line in log.splitlines() if line.startswith("LZ4_NATIVE_PROOF ")]
            require(
                len(native) == 1 and "LZ4_ROUNDTRIP_PROOF compression.type=lz4" in log,
                "native log proof missing",
            )
            match = re.search(
                r"^LZ4_NATIVE_PROOF java=(\S+) uid=(\d+) .* sha256=(" + HEX + r") mappings=\[.+\]",
                native[0],
            )
            require(
                match and match[1] == JDK[java] and int(match[2]) > 0,
                "native actual JDK/UID/library mapping missing",
            )
            item.update(
                actual_jdk=match[1],
                actual_uid=int(match[2]),
                native_library_sha256=match[3],
                instrumented_sha256=hashed(row["source_sha256"]),
                mode="explicit Native.load / PropertiesLauncher; not ordinary default credit",
                production_unchanged="instrumented pre-build source digest only; pristine pre-instrumentation inventory unavailable",
            )
            if app.is_dir():
                current = current_inventory(e, app, label + "/app-j" + java)
                require(
                    inv_digest(current) == row["source_sha256"]
                    and current["pom.xml"] == row["pom_sha256"]
                    and current["Dockerfile"] == row["dockerfile_sha256"],
                    "native source/POM/recipe changed after pre-build digest",
                )
            else:
                e.unavailable.append(label + "/app-j" + java + "/current-source-tree")
            # The native module retains image inspect JSON in its infrastructure log, not a standalone image file.
            infra = e.read(root, "infrastructure.log", label + "/infrastructure.log").decode()
            images = []
            for marker in re.finditer(r"(?m)^\$ docker image inspect [^\n]+\n", infra):
                data, _ = json.JSONDecoder().raw_decode(infra[marker.end() :].lstrip())
                images.extend(data)
            image = next((image for image in images if image.get("Id") == row["image_id"]), None)
            require(
                image
                and (
                    image.get("Os"),
                    image.get("Architecture"),
                    image.get("Config", {}).get("User"),
                )
                == ("linux", "amd64", "edgeforge"),
                "native actual image/config binding missing",
            )
            item["image_configuration_sha256"] = inv_digest(image["Config"])
        output.append(item)
    return {
        "status": "validated-recorded-runtime",
        "mode": mode,
        "module_source_sha256": modules,
        "cases": output,
        "not_assessed_production_image_identity": True,
        "receipt_reference": label + "/receipt.json",
    }


def current_inventory(e, app, label):
    result = {}
    for directory, dirs, files in os.walk(app, followlinks=False):
        if Path(directory) == app:
            dirs[:] = [d for d in dirs if d not in {"target", ".git"}]
            files = [f for f in files if f != ".git"]
        require(not any((Path(directory) / d).is_symlink() for d in dirs), "linked runtime source")
        for file in files:
            name = (Path(directory) / file).relative_to(app).as_posix()
            result[name] = digest(e.read(app, name, label + "/" + name))
    return dict(sorted(result.items()))


def summarize(
    compatibility_receipt,
    reused_root,
    default_receipt,
    native_receipt,
    source_root,
    runtime_runner=None,
):
    e = Evidence()
    result = {
        "schema_version": 1,
        "source_sha": SOURCE,
        "goal_complete": False,
        "release_acceptance": False,
        "claim_boundary": "compatibility unit/contract tests and separate instrumented default/native runtime proof; no scanner/campaign/clearance credit",
    }
    result["compatibility"] = compatibility(e, Path(compatibility_receipt), Path(reused_root))
    result["runtime_default"] = runtime(e, Path(default_receipt), "default", Path(source_root))
    result["runtime_explicit_native"] = runtime(
        e, Path(native_receipt), "explicit-native", Path(source_root)
    )
    if runtime_runner:
        path = Path(runtime_runner)
        runner = e.json(path.parent, path.name, "runtime/runner-receipt.json")
        require(
            runner.get("status") == "passed"
            and runner.get("generator_sha") == SOURCE
            and runner.get("existing_proof_modules_changed") is False
            and runner.get("owned_builder_cleanup_exit_code") == 0,
            "runtime runner incomplete/mutated/cleanup failed",
        )
        rows = runner["proofs"]
        require(
            len(rows) == 2
            and {r["label"] for r in rows} == {"default", "explicit-native"}
            and all(
                r["exit_code"] == 0
                and r["receipt_sha256"] == e.hashes["runtime/" + r["label"] + "/receipt.json"]
                for r in rows
            ),
            "runtime runner/receipt binding mismatch",
        )
        result["runtime_runner"] = {"reference": "runtime/runner-receipt.json", "status": "passed"}
    else:
        e.unavailable.append("runtime/outer-runner-cleanup-binding-not-supplied")
    result["input_sha256"] = dict(sorted(e.hashes.items()))
    result["unavailable_preimages_or_bindings"] = sorted(set(e.unavailable))
    result["status"] = "validated-with-explicit-evidence-limits"
    text = json.dumps(result, sort_keys=True)
    require(
        not re.search(r"/" r"Users/|/home/|/private/|/var/folders/|[A-Za-z]:\\", text),
        "private host path in selected output",
    )
    summary = (
        "Compatibility: 8 distinct cases (3 reused, 5 fresh); "
        + str(result["compatibility"]["total_tests"])
        + " tests reconstructed: 6 Engine-emitted, 26 proof-supplied; no failures/errors/skips.\n"
        "Runtime: default and explicit-native Java17/21 validated separately; not assessed production-image identity.\n"
        "Native baseline limit: pre-build instrumented digest, not a separately retained pristine pre-instrumentation inventory.\n"
        "Synthetic controls are not runtime proof. Goal, campaign, independent review and release clearance not established.\n"
    )
    return result, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "compatibility-receipt",
        "reused-root",
        "default-receipt",
        "native-receipt",
        "source-root",
        "output-dir",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--runtime-runner", type=Path)
    args = vars(parser.parse_args(argv))
    output = args.pop("output_dir")
    try:
        require(not output.exists(), "output must be new")
        result, summary = summarize(**args)
        output.mkdir(mode=0o700)
        with (output / "proof-summary.json").open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        with (output / "summary.txt").open("x") as stream:
            stream.write(summary)
        print("Validated summary written; evidence limits explicit; goal not complete.")
        return 0
    except Exception as error:
        print(
            "Proof summary incomplete: "
            + type(error).__name__
            + "; no runtime/campaign credit inferred.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
