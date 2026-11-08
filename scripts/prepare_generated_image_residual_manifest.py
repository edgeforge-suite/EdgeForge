"""Discover existing local evidence; write a fresh portable reconciliation manifest.

No proof claims or replacement edges are manufactured. Roots remain private CLI
arguments, printed as aliases only. Does not collect, publish or assess evidence.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.reconcile_generated_image_residuals import (  # noqa: E402
    BUILD_DECLARATION_MEMBERS,
    CLASSIFIER_MEMBERS,
    STAGE_MEMBERS,
    STAGES,
    Evidence,
    classifier_inventory_required,
    need,
    relative,
    sha,
    write_new,
)


def ref(roots, alias, member):
    relative(member)
    path = (roots[alias] / member).resolve()
    need(
        path.is_relative_to(roots[alias].resolve()) and path.is_file(),
        "missing adapter input member",
    )
    return {"root": alias, "member": member, "sha256": sha(path.read_bytes())}


def select(roots, alias, base):
    names = [
        name for name in (base + ".json", base + ".json.gz") if (roots[alias] / name).is_file()
    ]
    need(len(names) == 1, "missing or ambiguous JSON/gzip adapter member")
    return ref(roots, alias, names[0])


def build_declarations(roots, case, stage):
    refs = {}
    for label in BUILD_DECLARATION_MEMBERS:
        published = relative(case) + "/" + stage + "/" + label
        raw = relative(case) + "/" + stage + "-bundle/" + label
        locations = [
            base
            for base in (published, raw)
            if any(
                (roots["current"] / (base + suffix)).is_file() for suffix in (".json", ".json.gz")
            )
        ]
        need(len(locations) == 1, "missing/ambiguous build declaration location")
        refs[label] = select(roots, "current", locations[0])
    return refs


def prepare(
    roots,
    ledger_member,
    verification_member,
    proof_member,
    old_policy_prefix="vendor-sources",
    declaration_member=None,
):
    ev = Evidence(roots)
    h = {
        "decisions": ref(roots, "plan", "finding-decisions.json"),
        "copies": ref(roots, "plan", "component-copies.json"),
        "ledger": ref(roots, "historical", ledger_member),
        "candidate": ref(roots, "plan", "candidate-bundle.json"),
        "edges": ref(roots, "plan", "maven-research/edge-receipts.json"),
        "vendor_plan": ref(roots, "plan", "maven-research/vendor-reconciliation.json"),
        "vendor_verification": ref(roots, "verified", verification_member),
    }
    declaration_ref = (
        ref(roots, "declaration", declaration_member)
        if declaration_member
        else select(roots, "current", "coverage-declared")
    )
    declaration = ev.read(declaration_ref)
    campaign_ref = select(roots, "current", "campaign")
    campaign = ev.read(campaign_ref)
    need(campaign["campaign_complete"] is True, "campaign not complete; no ready manifest")
    rows = []
    for case in declaration["cases"]:
        for stage in STAGES:
            prefix = relative(case["case"]) + "/" + stage + "/"
            evidence = {label: select(roots, "current", prefix + label) for label in STAGE_MEMBERS}
            if stage == STAGES[0]:
                evidence.update(build_declarations(roots, case["case"], stage))
                if classifier_inventory_required(
                    ev.read(evidence["retained-maven-bom"]), ev.read(evidence["resolved-inventory"])
                ):
                    evidence.update(
                        {
                            label: select(roots, "current", prefix + label)
                            for label in CLASSIFIER_MEMBERS
                        }
                    )
                else:
                    need(
                        not any(
                            (roots["current"] / (prefix + label + suffix)).is_file()
                            for label in CLASSIFIER_MEMBERS
                            for suffix in (".json", ".json.gz")
                        ),
                        "unexpected classifier supplement without declaration",
                    )
            rows.append({"case": case["case"], "stage": stage, "evidence": evidence})
    vendor = ev.read(h["vendor_plan"])
    verified = ev.read(h["vendor_verification"])
    candidates = {r["id"]: r for r in verified["five_supported_candidates"]}
    sources = {}
    for row in vendor:
        identifier = row["id"]
        entries = []
        for old in row.get("historical_feed_observation", []):
            artifact = relative(old["artifact"])
            suffix = "global" if "-global." in artifact else "osv" if "-osv." in artifact else None
            need(suffix is not None, "unknown historical feed artifact")
            old_ref = ref(roots, "policy", old_policy_prefix + "/" + artifact)
            need(sha(ev.raw(old_ref)) == old["sha256_uncompressed"], "old feed content differs")
            entries.append(
                {
                    "label": "old-" + suffix,
                    "http_status": old["http_status"],
                    "retrieved_at_utc": old["retrieved_at_utc"],
                    "content_sha256": old["sha256_uncompressed"],
                    "evidence": old_ref,
                }
            )
        if identifier in candidates:
            for suffix in ("global", "osv"):
                recent = next(
                    x
                    for x in candidates[identifier]["source_receipts"]
                    if x["file"].endswith(identifier + "-" + suffix + ".body")
                )
                entries.append(
                    {
                        "label": "new-" + suffix,
                        "http_status": int(recent["http_status"]),
                        "retrieved_at_utc": recent["retrieved_at_utc"],
                        "content_sha256": recent["sha256"],
                        "evidence": ref(roots, "plan", recent["file"]),
                    }
                )
        else:
            for label, body in (
                ("repository", "jackson-databind-advisories.body"),
                ("new-global", "jackson-global-advisory.body"),
                ("new-osv", "jackson-osv-advisory.body"),
            ):
                recent = next(x for x in row["source_receipts"] if x["body"] == body)
                entries.append(
                    {
                        "label": label,
                        "http_status": int(recent["http_status"]),
                        "retrieved_at_utc": recent["retrieved_at_utc"],
                        "content_sha256": recent["sha256"],
                        "evidence": ref(roots, "plan", "maven-research/" + body),
                    }
                )
        sources[identifier] = entries
    return {
        "schema_version": "residual-reconciliation-v1",
        "source_sha": campaign["generator_sha"],
        "historical": h,
        "declaration": declaration_ref,
        "campaign": campaign_ref,
        "proof_aggregate": ref(roots, "proof", proof_member),
        "stages": rows,
        "replacement_links": [],
        "vendor_sources": sources,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--ledger-file", type=Path, required=True)
    parser.add_argument(
        "--old-policy",
        type=Path,
        required=True,
        help="historical directory containing vendor-sources/",
    )
    parser.add_argument("--verification-file", type=Path, required=True)
    parser.add_argument("--proof-file", type=Path, required=True)
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="complete raw collector or full sanitized publisher root",
    )
    parser.add_argument(
        "--declaration-file", type=Path, help="raw collector declaration if not inside current root"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        roots = {
            "plan": args.plan.resolve(),
            "historical": args.ledger_file.resolve().parent,
            "policy": args.old_policy.resolve(),
            "verified": args.verification_file.resolve().parent,
            "proof": args.proof_file.resolve().parent,
            "current": args.current.resolve(),
        }
        if args.declaration_file:
            roots["declaration"] = args.declaration_file.resolve().parent
        manifest = prepare(
            roots,
            args.ledger_file.name,
            args.verification_file.name,
            args.proof_file.name,
            declaration_member=args.declaration_file.name if args.declaration_file else None,
        )
        need(
            not any(args.output.resolve().is_relative_to(root) for root in roots.values()),
            "manifest output must be outside input roots",
        )
        write_new(args.output, manifest)
        print(
            json.dumps(
                {
                    "status": "manifest-prepared-not-assessed",
                    "stage_references": len(manifest["stages"]),
                    "replacement_links": 0,
                    "root_aliases": sorted(roots),
                }
            )
        )
        return 0
    except Exception:
        print(
            "Manifest preparation incomplete: missing/ambiguous evidence or non-fresh output.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
