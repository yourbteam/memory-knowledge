"""Real child processes test the reader's timeout boundary, not model semantics."""
import importlib.util
import subprocess
import sys
import time
from pathlib import Path
import pytest

@pytest.fixture
def critic():
    path = Path(__file__).resolve().parents[1] / 'skills/critique-machinery/scripts/critique.py'
    spec = importlib.util.spec_from_file_location('lifecycle_critic', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_successful_reader_preserves_both_output_streams(critic, tmp_path):
    result = critic.run_reader_process([sys.executable, '-c', 'import sys; print(sys.stdin.read()); print("error evidence", file=sys.stderr)'], input='captured input', text=True, capture_output=True, timeout=3, cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout == 'captured input\n'
    assert result.stderr == 'error evidence\n'

def test_timeout_terminates_inherited_pipe_child_and_preserves_partial_output(critic, tmp_path):
    marker = tmp_path / 'child-survived'
    child = f'import time; from pathlib import Path; time.sleep(0.8); Path({str(marker)!r}).write_text("survived")'
    launcher = f'import subprocess, sys, time; subprocess.Popen([sys.executable,"-c",{child!r}]); print("partial",flush=True); time.sleep(10)'
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        critic.run_reader_process([sys.executable, '-c', launcher], input='', text=True, capture_output=True, timeout=.2, cwd=tmp_path)
    assert time.monotonic() - started < 1.5
    assert 'partial' in caught.value.stdout
    time.sleep(.9)
    assert not marker.exists()

def test_nonzero_exit_is_not_reinterpreted_as_success(critic, tmp_path):
    result = critic.run_reader_process([sys.executable, '-c', 'import sys; print("failure"); sys.exit(7)'], input='', text=True, capture_output=True, timeout=3, cwd=tmp_path)
    assert result.returncode == 7
    assert result.stdout == 'failure\n'
