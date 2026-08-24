from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


def test_launcher_routes_all_cache_writes_to_tmp_and_preserves_arguments(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print(json.dumps({"
        "'argv': sys.argv[1:], 'cwd': os.getcwd(), "
        "'uv_cache': os.environ.get('UV_CACHE_DIR'), "
        "'pycache': os.environ.get('PYTHONPYCACHEPREFIX'), "
        "'no_bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE')}))\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    environment = {
        **os.environ,
        "TMPDIR": str(tmp_path / "writable"),
        "MK_PYTEST_PYTHON": str(fake_python),
    }

    completed = subprocess.run(
        [str(repository / "scripts/run_pytest.sh"), "tests/test_example.py", "-q"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["argv"] == [
        "-m", "pytest", "-p", "no:cacheprovider", "tests/test_example.py", "-q",
    ]
    assert result["cwd"] == str(repository)
    assert result["uv_cache"] == str(tmp_path / "writable/memory-knowledge-python-cache/uv")
    assert result["pycache"] == str(tmp_path / "writable/memory-knowledge-python-cache/pycache")
    assert result["no_bytecode"] == "1"


def test_launcher_provisions_dev_dependencies_when_selected_python_lacks_pytest(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    python_without_pytest = tmp_path / "python-without-pytest"
    python_without_pytest.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    python_without_pytest.chmod(0o755)
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print(json.dumps({"
        "'argv': sys.argv[1:], 'cwd': os.getcwd(), "
        "'uv_cache': os.environ.get('UV_CACHE_DIR')}))\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path / "writable"),
        "MK_PYTEST_PYTHON": str(python_without_pytest),
    }

    completed = subprocess.run(
        [str(repository / "scripts/run_pytest.sh"), "tests/test_example.py", "-q"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["argv"] == [
        "run", "--extra", "dev", "pytest", "-p", "no:cacheprovider",
        "tests/test_example.py", "-q",
    ]
    assert result["cwd"] == str(repository)
    assert result["uv_cache"] == str(tmp_path / "writable/memory-knowledge-python-cache/uv")
