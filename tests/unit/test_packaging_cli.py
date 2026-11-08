from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def test_editable_install_appbuilder_command_runs_outside_repo(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python = venv_dir / "bin" / "python"
    appbuilder = venv_dir / "bin" / "appbuilder"

    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-e",
            str(repo_root),
        ],
        check=True,
        cwd=tmp_path,
    )

    site_packages = subprocess.check_output(
        [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
        text=True,
    ).strip()
    editable_pths = sorted(Path(site_packages).glob("__editable__.appbuilder-*.pth"))
    assert editable_pths
    if sys.platform == "darwin" and shutil.which("chflags"):
        for pth in editable_pths:
            subprocess.run(["chflags", "hidden", str(pth)], check=True)

    result = subprocess.run(
        [str(appbuilder), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Generate contract-preserving replacement applications" in result.stdout

    metadata = subprocess.run(
        [str(python), "-c", (
            "from importlib.metadata import distribution; "
            "d=distribution('appbuilder'); "
            "assert d.metadata['Requires-Python'] == '>=3.11'; "
            "assert d.metadata['License-Expression'] == 'Apache-2.0'; "
            "assert set(d.metadata.get_all('License-File')) == {'LICENSE', 'NOTICE'}; "
            "assert not any('Proprietary' in c for c in d.metadata.get_all('Classifier', [])); "
            "assert 'Programming Language :: Python :: 3.10' not in d.metadata.get_all('Classifier', []); "
            "assert 'fastmcp==3.4.10' in d.requires; "
            "files={str(p).split('/')[-1] for p in d.files}; "
            "assert {'LICENSE', 'NOTICE'} <= files"
        )],
        cwd=tmp_path, text=True, capture_output=True,
    )
    assert metadata.returncode == 0, metadata.stderr
