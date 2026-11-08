from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.smoke import l5_orchestrator


def test_l5_orchestrator_skips_when_sibling_repo_env_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDGEFORGE_STUDIO_REPO", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_REPO", raising=False)

    report = l5_orchestrator.run_suite_l5_acceptance(root=tmp_path)

    assert report["status"] == "skipped"
    assert "EDGEFORGE_STUDIO_REPO" in report["warnings"][0]["warning"]
    assert "EDGEFORGE_KS_REPO" in report["warnings"][0]["warning"]
    assert (tmp_path / "l5-run-manifest.json").is_file()
    assert (tmp_path / "l5-report.json").is_file()
    run_manifest = json.loads(
        (tmp_path / "l5-run-manifest.json").read_text(encoding="utf-8")
    )
    assert run_manifest["schema_version"] == "1.0"


def test_l5_orchestrator_fails_missing_repos_when_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDGEFORGE_STUDIO_REPO", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_REPO", raising=False)

    report = l5_orchestrator.run_suite_l5_acceptance(
        root=tmp_path,
        require_sibling_repos=True,
    )

    assert report["status"] == "failed"
    assert "requires sibling repo env vars" in report["error"]


def test_l5_orchestrator_requires_ks_repo_before_studio_leaf_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    studio_repo = tmp_path / "studio"
    studio_repo.mkdir()
    monkeypatch.setenv("EDGEFORGE_STUDIO_REPO", studio_repo.as_posix())
    monkeypatch.delenv("EDGEFORGE_KS_REPO", raising=False)

    def fail_if_called(**_: object) -> l5_orchestrator.OrchestratorResult:
        raise AssertionError("Studio leaf must not run without a pinned KS repo")

    monkeypatch.setattr(l5_orchestrator, "_run_studio_l5", fail_if_called)

    report = l5_orchestrator.run_suite_l5_acceptance(
        root=tmp_path / "run",
        require_sibling_repos=True,
    )

    assert report["status"] == "failed"
    assert "EDGEFORGE_KS_REPO" in report["error"]


def test_l5_orchestrator_cli_skipped_run_exits_nonzero_by_default(monkeypatch) -> None:
    monkeypatch.delenv("EDGEFORGE_STUDIO_REPO", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_REPO", raising=False)

    assert l5_orchestrator.main([]) == 1
    assert l5_orchestrator.main(["--allow-skipped-success"]) == 0


def test_l5_orchestrator_collects_leaf_results_and_sha_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    studio_repo = tmp_path / "studio"
    ks_repo = tmp_path / "ks"
    studio_repo.mkdir()
    ks_repo.mkdir()
    monkeypatch.setenv("EDGEFORGE_STUDIO_REPO", str(studio_repo))
    monkeypatch.setenv("EDGEFORGE_KS_REPO", str(ks_repo))
    monkeypatch.setattr(l5_orchestrator, "_git_sha", lambda repo: f"sha-{repo.name}")
    monkeypatch.setattr(l5_orchestrator, "_run_engine_runtime", lambda **_: _passed_engine_runtime())
    monkeypatch.setattr(l5_orchestrator, "_run_engine_regen", lambda **_: _passed_engine_regen())
    monkeypatch.setattr(l5_orchestrator, "_run_engine_change_plan", _passed_engine_plan)
    monkeypatch.setattr(l5_orchestrator, "_run_engine_apply_isolation", _passed_engine_apply_isolation)
    monkeypatch.setattr(l5_orchestrator, "_run_studio_l5", lambda **_: _passed_studio())
    monkeypatch.setattr(l5_orchestrator, "_run_ks_l5", lambda **_: _passed_ks())

    report = l5_orchestrator.run_suite_l5_acceptance(root=tmp_path / "run")

    assert report["status"] == "passed"
    assert {item["status"] for item in report["checklist"]} == {"pass"}
    manifest = json.loads((tmp_path / "run" / "l5-run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    # Bound to the orchestrator's own engine root, not a literal directory name:
    # the checkout is not always called "EdgeForge" (worktrees, renamed clones).
    assert manifest["repos"]["engine"]["sha"] == f"sha-{l5_orchestrator.REPO_ROOT.name}"
    assert manifest["repos"]["studio"]["sha"] == "sha-studio"
    assert manifest["repos"]["ks"]["sha"] == "sha-ks"
    assert manifest["topology"]["postgres"]["image"]
    assert manifest["topology"]["mock_soap"]["version"] == "in-process-v1"


def test_l5_orchestrator_rejects_empty_studio_scenarios(tmp_path: Path, monkeypatch) -> None:
    completed = subprocess.CompletedProcess(
        args=["python", "-c"],
        returncode=0,
        stdout='{"scenarios": []}\n',
    )
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", lambda *_, **__: completed)

    ks_repo = _ks_repo_with_venv(tmp_path)

    result = l5_orchestrator._run_studio_l5(
        studio_repo=tmp_path,
        ks_repo=ks_repo,
        root=tmp_path / "studio",
    )

    assert result.status == "failed"
    assert "non-empty scenarios list" in (result.error or "")


def test_l5_orchestrator_rejects_studio_artifact_root_contract_drift(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    combined = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == "combined edge-contract author-generate"
    )
    combined["detail"].pop("generated_dir")

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert "combined edge-contract author-generate" in error
    assert "generated_dir" in error


def test_l5_orchestrator_rejects_studio_regen_apply_contract_drift(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    regen_apply["detail"]["alpha"]["applied"] = False

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO in error
    assert "alpha did not apply successfully" in error


def test_l5_orchestrator_rejects_studio_regen_apply_outside_workspace(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    outside = tmp_path / "outside" / "generated-app"
    regen_apply["detail"]["alpha"]["refreshed_package"] = outside.as_posix()

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert "outside workspace_root" in error


def test_l5_orchestrator_rejects_studio_regen_apply_cross_bleed(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    regen_apply["detail"]["beta_cross_bleed"] = True

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert "cross-session bleed" in error


def test_l5_orchestrator_rejects_studio_regen_apply_bad_summary_metadata(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    regen_apply["detail"]["alpha"]["apply_summary"]["baseline_present"] = "true"

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert "baseline_present is not boolean" in error


def test_l5_orchestrator_rejects_studio_regen_apply_pending_summary_status(tmp_path: Path) -> None:
    payload = _studio_payload(package_dir=tmp_path / "package")
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    regen_apply["detail"]["alpha"]["apply_summary"]["status"] = "regenerate-ready"

    error = l5_orchestrator._validate_studio_payload(payload)

    assert error is not None
    assert "post-apply regen status 'none'" in error


def test_l5_orchestrator_studio_invocation_does_not_set_parent_allowed_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_env = {}
    ks_repo = _ks_repo_with_venv(tmp_path)
    ks_command = ks_repo.resolve() / ".venv" / "bin" / "python"

    def fake_run_python_snippet(*_, env: dict, **__) -> subprocess.CompletedProcess:
        captured_env.update(env)
        return subprocess.CompletedProcess(
            args=["python", "-c"],
            returncode=0,
            stdout=json.dumps(
                _studio_payload(
                    package_dir=tmp_path / "package",
                    ks_repo=ks_repo,
                    ks_command=ks_command,
                )
            )
            + "\n",
        )

    package_dir = tmp_path / "package"
    generated_dir = package_dir / "generated-app"
    generated_dir.mkdir(parents=True)
    (package_dir / "evidence-trail.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", fake_run_python_snippet)
    monkeypatch.delenv("EDGEFORGE_MCP_ALLOWED_ROOTS", raising=False)
    monkeypatch.delenv("EDGEFORGE_KS_PYTHON", raising=False)

    result = l5_orchestrator._run_studio_l5(
        studio_repo=tmp_path,
        ks_repo=ks_repo,
        root=tmp_path / "studio",
    )

    assert result.status == "passed"
    assert captured_env["EDGEFORGE_STUDIO_ENGINE_REPO"]
    assert captured_env["EDGEFORGE_STUDIO_ENGINE_MCP_COMMAND"]
    assert captured_env["EDGEFORGE_STUDIO_KS_REPO"] == ks_repo.resolve().as_posix()
    assert captured_env["EDGEFORGE_STUDIO_KS_COMMAND"] == (
        ks_repo.resolve() / ".venv" / "bin" / "python"
    ).as_posix()
    assert captured_env["EDGEFORGE_SHARED_MODE"] == "1"
    assert "EDGEFORGE_MCP_ALLOWED_ROOTS" not in captured_env


def test_l5_orchestrator_studio_ks_command_uses_edgeforge_ks_python(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_env = {}
    configured_ks_python = tmp_path / "pinned-ks-python"
    configured_ks_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    ks_repo = tmp_path / "ks"
    ks_repo.mkdir()
    package_dir = tmp_path / "package"
    (package_dir / "generated-app").mkdir(parents=True)
    (package_dir / "evidence-trail.json").write_text("{}", encoding="utf-8")

    def fake_run_python_snippet(*_, env: dict, **__) -> subprocess.CompletedProcess:
        captured_env.update(env)
        return subprocess.CompletedProcess(
            args=["python", "-c"],
            returncode=0,
            stdout=json.dumps(
                _studio_payload(
                    package_dir=package_dir,
                    ks_repo=ks_repo,
                    ks_command=configured_ks_python,
                )
            )
            + "\n",
        )

    monkeypatch.setenv("EDGEFORGE_KS_PYTHON", configured_ks_python.as_posix())
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", fake_run_python_snippet)

    result = l5_orchestrator._run_studio_l5(
        studio_repo=tmp_path,
        ks_repo=ks_repo,
        root=tmp_path / "studio",
    )

    assert result.status == "passed"
    assert captured_env["EDGEFORGE_STUDIO_KS_COMMAND"] == configured_ks_python.as_posix()
    assert result.detail["orchestrator_pinned_ks"]["command_from_edgeforge_ks_python"] is True
    assert result.detail["studio_resolved_ks"]["command"] == configured_ks_python.resolve(
        strict=False
    ).as_posix()


def test_l5_orchestrator_rejects_studio_payload_without_actual_ks_resolution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    (package_dir / "generated-app").mkdir(parents=True)
    (package_dir / "evidence-trail.json").write_text("{}", encoding="utf-8")
    ks_repo = _ks_repo_with_venv(tmp_path)

    completed = subprocess.CompletedProcess(
        args=["python", "-c"],
        returncode=0,
        stdout=json.dumps(_studio_payload(package_dir=package_dir)) + "\n",
    )
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", lambda *_, **__: completed)

    result = l5_orchestrator._run_studio_l5(
        studio_repo=tmp_path,
        ks_repo=ks_repo,
        root=tmp_path / "studio",
    )

    assert result.status == "failed"
    assert "did not report the KS command/repo" in (result.error or "")


def test_l5_orchestrator_rejects_studio_resolved_ambient_ks_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    (package_dir / "generated-app").mkdir(parents=True)
    (package_dir / "evidence-trail.json").write_text("{}", encoding="utf-8")
    ks_repo = _ks_repo_with_venv(tmp_path)
    ambient_command = tmp_path / "ambient" / "python"
    ambient_command.parent.mkdir()
    ambient_command.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    completed = subprocess.CompletedProcess(
        args=["python", "-c"],
        returncode=0,
        stdout=json.dumps(
            _studio_payload(
                package_dir=package_dir,
                ks_repo=ks_repo,
                ks_command=ambient_command,
            )
        )
        + "\n",
    )
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", lambda *_, **__: completed)

    result = l5_orchestrator._run_studio_l5(
        studio_repo=tmp_path,
        ks_repo=ks_repo,
        root=tmp_path / "studio",
    )

    assert result.status == "failed"
    assert "does not match the orchestrator-pinned command" in (result.error or "")


def test_l5_orchestrator_rejects_ambient_studio_ks_command(tmp_path: Path) -> None:
    ks_repo = tmp_path / "pinned-ks"
    ambient_python = tmp_path / "ambient" / "python"
    ks_repo.mkdir()
    ambient_python.parent.mkdir()
    ambient_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    detail = l5_orchestrator._ks_pin_detail(
        ks_repo=ks_repo,
        command=ambient_python,
        env={},
    )

    assert detail["valid"] is False
    assert "not pinned" in (detail["error"] or "")


def test_l5_orchestrator_rejects_missing_ks_l5_check(tmp_path: Path, monkeypatch) -> None:
    completed = subprocess.CompletedProcess(
        args=["python", "-c"],
        returncode=0,
        stdout=json.dumps(_ks_payload(exclude={"per_session_db_isolation"})) + "\n",
    )
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", lambda *_, **__: completed)

    result = l5_orchestrator._run_ks_l5(ks_repo=tmp_path)

    assert result.status == "failed"
    assert "per_session_db_isolation" in (result.error or "")


def test_l5_orchestrator_rejects_failed_ks_l5_check(tmp_path: Path, monkeypatch) -> None:
    completed = subprocess.CompletedProcess(
        args=["python", "-c"],
        returncode=0,
        stdout=json.dumps(_ks_payload(fail={"shared_mode_requires_explicit_db_path"})) + "\n",
    )
    monkeypatch.setattr(l5_orchestrator, "_run_python_snippet", lambda *_, **__: completed)

    result = l5_orchestrator._run_ks_l5(ks_repo=tmp_path)

    assert result.status == "failed"
    assert "shared_mode_requires_explicit_db_path" in (result.error or "")


def test_l5_orchestrator_hard_fail_gate_detects_failed_leaf() -> None:
    results = [
        _passed_engine_runtime(),
        _passed_engine_regen(),
        _passed_engine_plan(),
        _passed_engine_apply_isolation(),
        l5_orchestrator.OrchestratorResult(
            name="studio.l5",
            status="failed",
            detail={"scenarios": [{"scenario": "multi-session isolation", "ok": False}]},
        ),
        _passed_ks(),
    ]

    checklist = l5_orchestrator._build_hard_fail_checklist(results)

    failures = {item["name"] for item in checklist if item["status"] == "fail"}
    assert "session bleed" in failures
    assert "read/write outside server-owned root" in failures
    assert "absolute local path leak in evidence/artifacts" in failures


def test_l5_orchestrator_absolute_path_gate_requires_explicit_studio_evidence() -> None:
    studio_without_evidence = _passed_studio(include_no_leak=False)

    assert l5_orchestrator._studio_no_absolute_path_leak(studio_without_evidence) is False

    checklist = l5_orchestrator._build_hard_fail_checklist(
        [
            _passed_engine_runtime(),
            _passed_engine_regen(),
            _passed_engine_plan(),
            _passed_engine_apply_isolation(),
            studio_without_evidence,
            _passed_ks(),
        ]
    )

    failures = {item["name"] for item in checklist if item["status"] == "fail"}
    assert "absolute local path leak in evidence/artifacts" in failures


def test_l5_orchestrator_session_bleed_requires_named_ks_isolation_checks() -> None:
    ks_missing_db_isolation = l5_orchestrator.OrchestratorResult(
        name="ks.l5",
        status="failed",
        detail=_ks_payload(exclude={"per_session_db_isolation"}),
        error="KS L5 payload is missing expected check(s): per_session_db_isolation",
    )

    checklist = l5_orchestrator._build_hard_fail_checklist(
        [
            _passed_engine_runtime(),
            _passed_engine_regen(),
            _passed_engine_plan(),
            _passed_engine_apply_isolation(),
            _passed_studio(),
            ks_missing_db_isolation,
        ]
    )

    failures = {item["name"] for item in checklist if item["status"] == "fail"}
    assert "session bleed" in failures


def test_l5_orchestrator_scans_studio_artifact_roots_for_absolute_paths(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "evidence-trail.json").write_text('{"source":"contracts/account.csv"}\n', encoding="utf-8")
    payload = _studio_payload(package_dir=package_dir)

    clean_scan = l5_orchestrator._scan_studio_artifacts_for_absolute_paths(payload)

    assert clean_scan["ok"] is True
    assert clean_scan["scanned_files"] == 1

    local_user_path = "/" + "Users/example/leaked/account.csv"
    (package_dir / "evidence-trail.json").write_text(
        f'{{"source":"{local_user_path}"}}\n',
        encoding="utf-8",
    )
    leak_scan = l5_orchestrator._scan_studio_artifacts_for_absolute_paths(payload)

    assert leak_scan["ok"] is False
    assert leak_scan["findings"][0]["marker"] == "/" + "Users/"


def test_l5_orchestrator_scans_regen_apply_per_session_artifact_roots(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    payload = _studio_payload(package_dir=package_dir)
    regen_apply = next(
        scenario
        for scenario in payload["scenarios"]
        if scenario["scenario"] == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO
    )
    for session_name in ("alpha", "beta"):
        session = regen_apply["detail"][session_name]
        for key in (
            "export_package",
            "generated_output",
            "initial_managed_package",
            "refreshed_package",
            "workspace_root",
        ):
            Path(session[key]).mkdir(parents=True, exist_ok=True)
    alpha_file = Path(regen_apply["detail"]["alpha"]["refreshed_package"]) / "evidence-trail.json"
    alpha_file.write_text('{"source":"contracts/account.csv"}\n', encoding="utf-8")

    scan = l5_orchestrator._scan_studio_artifacts_for_absolute_paths(payload)

    scanned_roots = set(scan["scanned_roots"])
    assert scan["ok"] is True
    assert alpha_file.parent.resolve().as_posix() in scanned_roots
    assert Path(regen_apply["detail"]["beta"]["generated_output"]).resolve().as_posix() in scanned_roots


def test_l5_orchestrator_checklist_marks_missing_runtime_dependency_as_skip() -> None:
    results = [
        l5_orchestrator.OrchestratorResult(name="engine.runtime", status="skipped"),
        _passed_engine_regen(),
        _passed_engine_plan(),
        _passed_engine_apply_isolation(),
        _passed_studio(),
        _passed_ks(),
    ]

    checklist = l5_orchestrator._build_hard_fail_checklist(results)

    runtime = next(item for item in checklist if item["name"] == "generated-app runtime failure")
    ka_off = next(item for item in checklist if item["name"] == "hidden KS/KA/LLM call when KA is OFF")
    assert runtime["status"] == "skip"
    assert ka_off["status"] == "skip"


def test_l5_orchestrator_read_write_gate_requires_apply_isolation_leaf() -> None:
    checklist = l5_orchestrator._build_hard_fail_checklist(
        [
            _passed_engine_runtime(),
            _passed_engine_regen(),
            _passed_engine_plan(),
            _passed_studio(),
            _passed_ks(),
        ]
    )

    read_write = next(item for item in checklist if item["name"] == "read/write outside server-owned root")
    assert read_write["status"] == "skip"

    failed_apply = l5_orchestrator.OrchestratorResult(
        name="engine.apply_isolation",
        status="failed",
        error="apply out-of-root accepted",
    )
    checklist = l5_orchestrator._build_hard_fail_checklist(
        [
            _passed_engine_runtime(),
            _passed_engine_regen(),
            _passed_engine_plan(),
            failed_apply,
            _passed_studio(),
            _passed_ks(),
        ]
    )

    read_write = next(item for item in checklist if item["name"] == "read/write outside server-owned root")
    assert read_write["status"] == "fail"


def test_l5_orchestrator_python_selection_uses_explicit_repo_override(tmp_path: Path) -> None:
    repo = tmp_path / "studio"
    configured = tmp_path / "python3.11"
    repo.mkdir()
    configured.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    selected = l5_orchestrator._python_for_repo(
        repo,
        env={"EDGEFORGE_STUDIO_PYTHON": configured.as_posix()},
        python_env_var="EDGEFORGE_STUDIO_PYTHON",
    )

    assert selected == configured


def test_l5_orchestrator_python_selection_uses_repo_venv(tmp_path: Path) -> None:
    repo = tmp_path / "ks"
    venv_python = repo / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    selected = l5_orchestrator._python_for_repo(repo, env={})

    assert selected == venv_python


def test_l5_orchestrator_python_selection_uses_path_python311(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "studio"
    path_python = tmp_path / "bin" / "python3.11"
    path_python.parent.mkdir()
    path_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    repo.mkdir()
    monkeypatch.setattr(l5_orchestrator.shutil, "which", lambda command: path_python.as_posix())

    selected = l5_orchestrator._python_for_repo(repo, env={})

    assert selected == path_python


def _passed_engine_runtime() -> l5_orchestrator.OrchestratorResult:
    return l5_orchestrator.OrchestratorResult(
        name="engine.runtime",
        status="passed",
        detail={"steps": ["confirmed KA/KS/MCP-off artifact posture"]},
    )


def _passed_engine_regen() -> l5_orchestrator.OrchestratorResult:
    return l5_orchestrator.OrchestratorResult(
        name="engine.regenerate",
        status="passed",
        detail={
            "steps": [
                "destructive apply and plan-hash drift refused",
                "KA/KS/MCP-off posture positively asserted",
            ]
        },
    )


def _passed_engine_plan() -> l5_orchestrator.OrchestratorResult:
    return l5_orchestrator.OrchestratorResult(
        name="engine.change_plan",
        status="passed",
        detail={"steps": ["destructive/unsafe classification and edge-contract impact surfaced"]},
    )


def _passed_engine_apply_isolation() -> l5_orchestrator.OrchestratorResult:
    return l5_orchestrator.OrchestratorResult(
        name="engine.apply_isolation",
        status="passed",
        detail={
            "steps": [
                "apply shared-mode no allowed roots fail-closed",
                "apply out-of-root manifest rejected",
                "apply out-of-root package rejected",
                "apply wrote only under resolved package path",
            ]
        },
    )


def _passed_studio(*, include_no_leak: bool = True) -> l5_orchestrator.OrchestratorResult:
    scenarios = [
        "multi-session isolation",
        "Studio-to-Engine per-session outputs",
        "shared-mode security",
        "KS/KA per-session isolation",
        "Engine fail-closed out-of-root",
        "KA-OFF strict",
        "combined edge-contract author-generate",
        l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO,
    ]
    if include_no_leak:
        scenarios.append("absolute local path leak scan")
    entries = []
    for scenario in scenarios:
        entry = {"scenario": scenario, "ok": True}
        if scenario == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO:
            entry["detail"] = _studio_regen_apply_detail(Path("/tmp/studio-workspace"))
        entries.append(entry)
    return l5_orchestrator.OrchestratorResult(
        name="studio.l5",
        status="passed",
        detail={"scenarios": entries},
    )


def _passed_ks() -> l5_orchestrator.OrchestratorResult:
    return l5_orchestrator.OrchestratorResult(
        name="ks.l5",
        status="passed",
        detail={
            "success": True,
            "tool_name": "run_ks_l5_isolation",
            "checks": _ks_checks(),
        },
    )


def _studio_payload(
    *,
    package_dir: Path,
    ks_repo: Path | None = None,
    ks_command: Path | None = None,
) -> dict:
    generated_dir = package_dir / "generated-app"
    scenarios = []
    for scenario in sorted(l5_orchestrator.EXPECTED_STUDIO_SCENARIOS):
        entry: dict = {"scenario": scenario, "ok": True}
        if scenario == "combined edge-contract author-generate":
            entry["detail"] = {
                "generated_dir": generated_dir.as_posix(),
                "package_dir": package_dir.as_posix(),
            }
        if scenario == l5_orchestrator.STUDIO_REGEN_APPLY_SCENARIO:
            entry["detail"] = _studio_regen_apply_detail(package_dir / "workspace")
        scenarios.append(entry)
    payload: dict = {"scenarios": scenarios}
    if ks_repo is not None and ks_command is not None:
        payload["studio_resolved_ks"] = {
            "repo": ks_repo.expanduser().resolve(strict=False).as_posix(),
            "command": ks_command.expanduser().resolve(strict=False).as_posix(),
            "source": "app.integrations.ks_integration",
        }
    return payload


def _studio_regen_apply_detail(workspace_root: Path) -> dict:
    alpha_workspace = workspace_root / "alpha-workspace"
    beta_workspace = workspace_root / "beta-workspace"
    return {
        "ok": True,
        "ka_off_silent": True,
        "ks_calls": [],
        "distinct_workspaces": True,
        "distinct_generated_outputs": True,
        "distinct_managed_packages": True,
        "alpha_under_workspace": True,
        "beta_under_workspace": True,
        "alpha_cross_bleed": False,
        "beta_cross_bleed": False,
        "alpha": _studio_regen_apply_session_detail(alpha_workspace, "alpha"),
        "beta": _studio_regen_apply_session_detail(beta_workspace, "beta"),
    }


def _studio_regen_apply_session_detail(workspace_root: Path, name: str) -> dict:
    generated_output = workspace_root / "generated-output"
    initial_package = workspace_root / "managed" / "initial-package"
    refreshed_package = workspace_root / "managed" / "refreshed-package"
    export_package = workspace_root / "export-package"
    migration_needle = f"{name}_regen_apply_note"
    return {
        "workspace_root": workspace_root.as_posix(),
        "export_package": export_package.as_posix(),
        "generated_output": generated_output.as_posix(),
        "initial_managed_package": initial_package.as_posix(),
        "refreshed_package": refreshed_package.as_posix(),
        "applied": True,
        "new_migration_count": 1,
        "migration_contains_field": True,
        "migration_needle": migration_needle,
        "apply_summary": {
            "generation_run_id": f"{name}-regen-apply-run",
            "managed_package_ref": f"managed/{name}-refreshed-package",
            "manifest_hash": f"{name}-manifest-hash",
            "baseline_hash": f"{name}-baseline-hash",
            "baseline_present": True,
            "status": "none",
        },
    }


def _ks_payload(
    *,
    exclude: set[str] | None = None,
    fail: set[str] | None = None,
) -> dict:
    return {
        "success": True,
        "tool_name": "run_ks_l5_isolation",
        "checks": _ks_checks(exclude=exclude, fail=fail),
    }


def _ks_checks(
    *,
    exclude: set[str] | None = None,
    fail: set[str] | None = None,
) -> list[dict]:
    exclude = exclude or set()
    fail = fail or set()
    return [
        {"name": name, "success": name not in fail}
        for name in sorted(l5_orchestrator.EXPECTED_KS_CHECKS - exclude)
    ]


def _ks_repo_with_venv(tmp_path: Path) -> Path:
    ks_repo = tmp_path / "ks"
    ks_python = ks_repo / ".venv" / "bin" / "python"
    ks_python.parent.mkdir(parents=True, exist_ok=True)
    ks_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return ks_repo
