"""Command-line entry point for AppBuilder."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from appbuilder.contracts import validate_package_or_raise
from appbuilder.core import CURRENT_MANIFEST_SCHEMA_FILENAME
from appbuilder.core.path_safety import (
    cli_allowed_roots_active,
    ensure_cli_allowed_roots_if_shared_mode,
    resolve_allowed_file,
    resolve_allowed_path,
)
from appbuilder.generation import GenerationReport, generate_application
from appbuilder.generation.apply import apply_change_plan
from appbuilder.generation.change_plan import build_change_plan, render_change_plan_json
from appbuilder.ingestion import fetch_openapi_spec, summarize_openapi_assessment
from appbuilder.metadata import build_metadata_project


def build_parser() -> argparse.ArgumentParser:
    """Create the root CLI parser."""

    parser = argparse.ArgumentParser(
        prog="appbuilder",
        description="Generate contract-preserving replacement applications from manifest-driven input projects.",
    )
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a standalone application from an EdgeForge manifest.",
    )
    generate_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the app-definition.yaml manifest.",
    )
    generate_parser.add_argument(
        "--output",
        required=True,
        help="Output directory for the generated application.",
    )
    generate_parser.add_argument(
        "--generation-run-id",
        dest="generation_run_id",
        default=None,
        help="Optional stable generation run identifier to stamp into generated files.",
    )
    generate_parser.add_argument(
        "--validate-schema",
        action="store_true",
        help=(
            "Validate the raw manifest against "
            f"{CURRENT_MANIFEST_SCHEMA_FILENAME} before loading."
        ),
    )

    plan_parser = subparsers.add_parser(
        "plan",
        help="Emit a read-only regenerate/maintain Change Plan for a generated package.",
    )
    plan_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the app-definition.yaml manifest.",
    )
    plan_parser.add_argument(
        "--package",
        required=True,
        help="Existing generated application package directory to inspect.",
    )
    plan_parser.add_argument(
        "--out",
        required=False,
        help="Optional file path to write the Change Plan JSON. Must not be inside --package.",
    )
    plan_parser.add_argument(
        "--validate-schema",
        action="store_true",
        help=(
            "Validate the raw manifest against "
            f"{CURRENT_MANIFEST_SCHEMA_FILENAME} before loading."
        ),
    )

    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply an approved additive regenerate/maintain Change Plan.",
    )
    apply_parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the app-definition.yaml manifest.",
    )
    apply_parser.add_argument(
        "--package",
        required=True,
        help="Existing generated application package directory to mutate.",
    )
    apply_parser.add_argument(
        "--approved-plan-hash",
        required=True,
        help="Plan hash from a previously reviewed appbuilder plan run.",
    )
    apply_parser.add_argument(
        "--generation-run-id",
        dest="generation_run_id",
        default="apply",
        help="Stable generation run identifier to stamp into regenerated files.",
    )
    apply_parser.add_argument(
        "--validate-schema",
        action="store_true",
        help=(
            "Validate the raw manifest against "
            f"{CURRENT_MANIFEST_SCHEMA_FILENAME} before loading."
        ),
    )

    assess_parser = subparsers.add_parser(
        "assess",
        help="Assess an OpenAPI/Swagger spec for EdgeForge compatibility without generating files.",
    )
    assess_parser.add_argument(
        "--swagger",
        required=True,
        help="URL of the OpenAPI/Swagger spec endpoint.",
    )
    assess_parser.add_argument(
        "--output",
        required=False,
        help="Optional file path to write a JSON assessment report.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AppBuilder CLI."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "assess":
        try:
            ensure_cli_allowed_roots_if_shared_mode()
            output_path = (
                _resolve_cli_output_path(args.output, purpose="output")
                if args.output
                else None
            )
            spec = fetch_openapi_spec(args.swagger)
            assessment = summarize_openapi_assessment(spec, args.swagger)
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        if output_path is not None:
            output_path.write_text(json.dumps(assessment, indent=2), encoding="utf-8")
        else:
            _print_assessment_summary(assessment)
        return 0

    if args.command == "plan":
        try:
            manifest_path = _resolve_cli_manifest_path(args.manifest)
            package_path = _resolve_cli_output_path(args.package, purpose="package")
            if args.validate_schema:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    validate_package_or_raise(yaml.safe_load(handle))
            metadata = build_metadata_project(manifest_path)
            plan = build_change_plan(metadata=metadata, package_dir=package_path)
            rendered = render_change_plan_json(plan)
            if args.out:
                output_path = _resolve_cli_output_path(args.out, purpose="out")
                if _is_path_within(output_path, package_path):
                    raise ValueError(
                        "--out must not point inside --package; plan is read-only "
                        "and must not write into the generated package."
                    )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered, encoding="utf-8")
            print(rendered, end="")
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "apply":
        try:
            manifest_path = _resolve_cli_manifest_path(args.manifest)
            package_path = _resolve_cli_output_path(args.package, purpose="package")
            if args.validate_schema:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    validate_package_or_raise(yaml.safe_load(handle))
            metadata = build_metadata_project(manifest_path)
            report = apply_change_plan(
                metadata=metadata,
                package_dir=package_path,
                approved_plan_hash=args.approved_plan_hash,
                source_manifest=str(manifest_path),
                generation_run_id=args.generation_run_id,
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI tests
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        _print_apply_summary(report)
        if (
            report.generation_report.harness_report is not None
            and not report.generation_report.harness_report.passed
        ):
            return 1
        return 0

    if args.command != "generate":
        parser.print_help()
        return 1

    try:
        manifest_path = _resolve_cli_manifest_path(args.manifest)
        output_path = _resolve_cli_output_path(args.output, purpose="output")
        if args.validate_schema:
            with manifest_path.open("r", encoding="utf-8") as handle:
                validate_package_or_raise(yaml.safe_load(handle))
        metadata = build_metadata_project(manifest_path)
        report = generate_application(
            metadata,
            output_path,
            source_manifest=str(manifest_path),
            generation_run_id=args.generation_run_id,
        )
    except Exception as exc:  # pragma: no cover - exercised through CLI tests
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_generation_summary(report)
    if report.harness_report is not None and not report.harness_report.passed:
        return 1
    return 0


def _print_generation_summary(report: GenerationReport) -> None:
    print(f"Generated application at: {report.output_dir}")
    print(f"Files created: {len(report.files_created)}")
    if report.harness_report is None:
        print("Harness: NOT RUN")
    elif report.harness_report.passed:
        print("Harness: PASSED (static compatibility checks)")
    else:
        print("Harness: FAILED")
        for check in report.harness_report.errors:
            print(f"  ERROR {check.name}: {check.message}")
        for check in report.harness_report.warnings:
            print(f"  WARNING {check.name}: {check.message}")
    if report.warnings:
        print("Generation warnings:")
        for warning in report.warnings:
            print(f"  - {warning}")


def _print_apply_summary(report) -> None:
    print(f"Applied Change Plan: {report.plan_hash}")
    print(f"Package: {report.package_dir}")
    if report.migrations_created:
        print("Migrations created:")
        for migration in report.migrations_created:
            print(f"  - {migration.relative_to(report.package_dir)}")
    else:
        print("Migrations created: none")
    print(f"Baseline updated: {report.baseline_path.relative_to(report.package_dir)}")
    print(f"Files refreshed: {len(report.generation_report.files_created)}")
    if report.generation_report.warnings:
        print("Apply warnings:")
        for warning in report.generation_report.warnings:
            print(f"  - {warning}")


def _print_assessment_summary(assessment: dict) -> None:
    title = assessment["title"]
    version = assessment["version"]
    print(f"EdgeForge Assessment — {title} ({version})")
    print(f"Spec URL: {assessment['spec_url']}")
    print("════════════════════════════════════════════════")
    print()
    print("DOMAIN ENTITIES (EdgeForge will generate)")
    if assessment["domain_entities"]:
        for entity in assessment["domain_entities"]:
            id_suffix = (
                f", id: {entity['id_field']}" if entity.get("id_field") is not None else ""
            )
            print(
                f"  ✓ {entity['name']:<15} — {entity['field_count']} fields{id_suffix}"
            )
    else:
        print("  (none)")
    print()
    print("REQUEST/RESPONSE DTOs (skipped for entity generation)")
    if assessment["dto_schemas"]:
        for schema_name in assessment["dto_schemas"]:
            print(f"  ○ {schema_name}")
    else:
        print("  (none)")
    print()
    print("INFRASTRUCTURE SCHEMAS (skipped)")
    if assessment["infrastructure_schemas"]:
        for schema_name in assessment["infrastructure_schemas"]:
            print(f"  ✗ {schema_name}")
    else:
        print("  (none)")
    print()
    print("OPERATIONS FOUND")
    if assessment["operations"]:
        for group_name, operations in assessment["operations"].items():
            print(f"  {group_name}: {', '.join(operations)}")
    else:
        print("  (none)")
    print()
    print("ASSESSMENT SUMMARY")
    print(f"  Domain entities:         {assessment['summary']['domain_entities']}")
    print(f"  DTOs:                    {assessment['summary']['dtos']}")
    print(f"  Infrastructure skipped:  {assessment['summary']['infrastructure']}")
    print(f"  EdgeForge coverage:     {assessment['summary']['coverage']}")
    print()
    print(
        "NOTE: Run `appbuilder generate` with a manifest referencing this spec_url to generate the application."
    )


def _resolve_cli_manifest_path(path_value: str) -> Path:
    ensure_cli_allowed_roots_if_shared_mode()
    if cli_allowed_roots_active():
        return resolve_allowed_file(path_value, purpose="manifest_path", mode="cli")
    return Path(path_value)


def _resolve_cli_output_path(path_value: str, *, purpose: str) -> Path:
    ensure_cli_allowed_roots_if_shared_mode()
    if cli_allowed_roots_active():
        return resolve_allowed_path(path_value, purpose=purpose, mode="cli")
    return Path(path_value)


def _is_path_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
