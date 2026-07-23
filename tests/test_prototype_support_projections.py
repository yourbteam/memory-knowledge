import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/prototype-driven-implementation"
SCRIPT = SKILL_ROOT / "scripts/generate_support_projections.py"
MANIFEST = SKILL_ROOT / "support-projections.json"


def load_generator():
    spec = importlib.util.spec_from_file_location("support_projection_generator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generated_projections_are_current_and_sources_are_pinned():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert [item["role"] for item in manifest["projections"]] == [
        "research",
        "plan",
        "write-code",
        "review",
    ]
    for item in manifest["projections"]:
        source = ROOT / item["source"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["source_sha256"]


def test_projection_contract_is_present_in_every_generated_file():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    common = manifest["common"]
    for item in manifest["projections"]:
        rendered = (SKILL_ROOT / "references" / item["output"]).read_text(
            encoding="utf-8"
        )
        assert item["purpose"] in rendered
        for value in (
            common["required_inputs"]
            + common["required_returns"]
            + common["forbidden"]
        ):
            assert value in rendered


def test_source_drift_fails_closed(tmp_path):
    generator = load_generator()
    manifest = generator.load_manifest(MANIFEST)
    source_root = tmp_path / "repo"
    for item in manifest["projections"]:
        target = source_root / item["source"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / item["source"]).read_bytes())

    first_source = source_root / manifest["projections"][0]["source"]
    first_source.write_text("changed\n", encoding="utf-8")

    try:
        generator.verify_sources(manifest, source_root)
    except generator.ProjectionError as exc:
        assert "source drift" in str(exc)
        assert "review the source change before repinning" in str(exc)
    else:
        raise AssertionError("source drift must fail closed")


def test_rendering_is_deterministic():
    generator = load_generator()
    manifest = generator.load_manifest(MANIFEST)
    first = {
        path.name: content
        for path, content in generator.expected_outputs(
            manifest, SKILL_ROOT / "references"
        ).items()
    }
    second = {
        path.name: content
        for path, content in generator.expected_outputs(
            manifest, SKILL_ROOT / "references"
        ).items()
    }
    assert first == second
