"""Effective interpreter optimization must refuse before any proof side effect."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULES = (
    "boot41_batch_preview_proof",
    "boot41_batch_name_collision_proof",
    "boot41_batch_durability",
    "boot41_batch_cases",
    "boot41_batch_early_crash",
)


@pytest.mark.parametrize("module", MODULES)
@pytest.mark.parametrize("flags,level", [(["-O"], "0"), (["-OO"], "0"), ([], "1"), ([], "2"), ([], "7")])
@pytest.mark.parametrize("invocation", ["module", "helper"])
def test_optimized_proof_refuses_before_side_effects(tmp_path, module, flags, level, invocation):
    marker = tmp_path / "side-effect"
    env = dict(os.environ, PYTHONOPTIMIZE=level)
    if invocation == "module":
        args = ["-m", "scripts.smoke." + module, "--work-dir", str(marker)]
    else:
        # Direct import/helper use must refuse even when main() is never called.
        args = ["-c", f"import scripts.smoke.{module}; from pathlib import Path; Path({str(marker)!r}).mkdir()"]
    result = subprocess.run([sys.executable, *flags, *args], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "Batch proof requires unoptimized Python" in result.stderr
    assert "remove -O/-OO" in result.stderr
    assert "effective PYTHONOPTIMIZE" in result.stderr
    assert not marker.exists()
    assert "receipt" not in result.stdout


@pytest.mark.parametrize("level", [None, "", "0"])
def test_unoptimized_imported_helpers_remain_valid(tmp_path, level):
    marker = tmp_path / "normal"
    env = os.environ.copy()
    env.pop("PYTHONOPTIMIZE", None)
    if level is not None:
        env["PYTHONOPTIMIZE"] = level
    result = subprocess.run(
        [sys.executable, "-c", f"from scripts.smoke.boot41_batch_durability import require_complete; require_complete((200, {{'status': 'COMPLETED'}})); from pathlib import Path; Path({str(marker)!r}).mkdir()"],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert marker.is_dir()


def test_guard_is_explicit_not_an_assertion():
    source = Path("scripts/smoke/boot41_batch_guard.py").read_text()
    assert "sys.flags.optimize" in source
    assert "raise RuntimeError" in source
    assert "assert " not in source
