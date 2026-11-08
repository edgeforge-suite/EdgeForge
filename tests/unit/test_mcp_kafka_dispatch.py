import shutil
from pathlib import Path

from appbuilder.mcp.tools.generation import _ALLOWED_ROOTS_ENV, generate_app


def test_mcp_generate_app_dispatches_to_kafka_emitter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "kafka-multi-route"
    shutil.copytree(Path("tests/fixtures/kafka-multi-route"), package_root)
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, str(tmp_path))

    manifest = package_root / "manifest.yaml"
    output_dir = tmp_path / "kafka-multi-route-output"

    result = generate_app(str(manifest), str(output_dir))

    assert result.success is True
    assert result.errors == []
    assert (output_dir / "pom.xml").exists()
    assert any(output_dir.rglob("*.java"))
