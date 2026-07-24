from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import sequence_checked_exec


def test_checked_exec_no_argument_main_rejects_generic_command_intake(
    monkeypatch, capsys,
):
    monkeypatch.setattr(
        sequence_checked_exec,
        "run",
        lambda args: pytest.fail("generic no-argument intake must not execute"),
    )

    assert sequence_checked_exec.main([]) == 2
    assert capsys.readouterr().err.strip() == (
        '{"error": "registered-sequence-adapter-required", "ok": false}'
    )


def test_checked_exec_guards_claims_dispatches_exact_argv_and_returns(monkeypatch, tmp_path):
    calls = []
    context = {
        "event_type": "operation_context_recorded", "context_id": "context",
        "repository_roots_hash": "a" * 64,
    }
    start = {"repository_roots": {"memory-knowledge": str(tmp_path)}}
    monkeypatch.setattr(sequence_checked_exec.work_memory, "load_ledger", lambda: ([context], "hash"))
    monkeypatch.setattr(sequence_checked_exec.work_memory, "_run_state", lambda events, run_id: (start, events))
    monkeypatch.setattr(
        sequence_checked_exec.sequence_guard, "cmd_guard",
        lambda args: calls.append(("guard", args.command, args.command_argv)) or {
            "source_ref": str(tmp_path / "scripts/tool.py"),
        },
    )
    monkeypatch.setattr(
        sequence_checked_exec.work_memory, "cmd_execution_claim",
        lambda args: calls.append(("claim", args.argv_json)) or {"execution_id": "execution"},
    )
    monkeypatch.setattr(
        sequence_checked_exec.work_memory, "cmd_execution_return",
        lambda args: calls.append(("return", args.exit_code)) or {},
    )
    monkeypatch.setattr(
        sequence_checked_exec.subprocess, "run",
        lambda argv, cwd, check, shell: calls.append(
            ("dispatch", argv, cwd, check, shell)
        ) or SimpleNamespace(returncode=7),
    )
    args = SimpleNamespace(
        task_id="task", run_id="run", context_id="context", step_ordinal=0,
        step_id="step", source="script", source_ref="scripts/tool.py",
        source_ref_repository="memory-knowledge", evidence_text=None, state=None,
        command=[
            "--", "python3", "scripts/tool.py", "--obligation",
            "Update `src/memory_knowledge/db/health.py`.",
        ],
    )

    assert sequence_checked_exec.run(args) == 7
    assert calls == [
        (
            "guard",
            "python3 scripts/tool.py --obligation 'Update `src/memory_knowledge/db/health.py`.'",
            [
                "python3", "scripts/tool.py", "--obligation",
                "Update `src/memory_knowledge/db/health.py`.",
            ],
        ),
        (
            "claim",
            '["python3", "scripts/tool.py", "--obligation", '
            '"Update `src/memory_knowledge/db/health.py`."]',
        ),
        (
            "dispatch",
            [
                "python3", "scripts/tool.py", "--obligation",
                "Update `src/memory_knowledge/db/health.py`.",
            ],
            str(tmp_path), False, False,
        ),
        ("return", 7),
    ]


def test_checked_exec_rejects_repository_different_from_guarded_source(
    monkeypatch, tmp_path,
):
    root_a = tmp_path / "repo-a"
    root_b = tmp_path / "repo-b"
    for root in (root_a, root_b):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts/tool.py").write_text("print('ok')\n")
    context = {
        "event_type": "operation_context_recorded", "context_id": "context",
        "repository_roots_hash": "a" * 64,
    }
    start = {"repository_roots": {"repo-a": str(root_a), "repo-b": str(root_b)}}
    monkeypatch.setattr(sequence_checked_exec.work_memory, "load_ledger", lambda: ([context], "hash"))
    monkeypatch.setattr(sequence_checked_exec.work_memory, "_run_state", lambda events, run_id: (start, events))
    monkeypatch.setattr(
        sequence_checked_exec.sequence_guard, "cmd_guard",
        lambda args: {"source_ref": str(root_a / "scripts/tool.py")},
    )
    monkeypatch.setattr(
        sequence_checked_exec.work_memory, "cmd_execution_claim",
        lambda args: pytest.fail("mismatched source must not be claimed"),
    )
    monkeypatch.setattr(
        sequence_checked_exec.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("mismatched source must not execute"),
    )
    args = SimpleNamespace(
        task_id="task", run_id="run", context_id="context", step_ordinal=0,
        step_id="step", source="script", source_ref="scripts/tool.py",
        source_ref_repository="repo-b", evidence_text=None, state=None,
        command=["python3", "scripts/tool.py"],
    )

    with pytest.raises(
        sequence_checked_exec.work_memory.WorkMemoryError,
        match="authorized-source-repository-mismatch",
    ):
        sequence_checked_exec.run(args)


def test_checked_exec_rejects_script_path_different_from_guarded_source(
    monkeypatch, tmp_path,
):
    root_a = tmp_path / "repo-a"
    root_b = tmp_path / "repo-b"
    for root in (root_a, root_b):
        (root / "scripts").mkdir(parents=True)
        (root / "scripts/tool.py").write_text("print('ok')\n")
    context = {
        "event_type": "operation_context_recorded", "context_id": "context",
        "repository_roots_hash": "a" * 64,
    }
    start = {"repository_roots": {"repo-a": str(root_a), "repo-b": str(root_b)}}
    monkeypatch.setattr(sequence_checked_exec.work_memory, "load_ledger", lambda: ([context], "hash"))
    monkeypatch.setattr(sequence_checked_exec.work_memory, "_run_state", lambda events, run_id: (start, events))
    monkeypatch.setattr(
        sequence_checked_exec.sequence_guard, "cmd_guard",
        lambda args: {"source_ref": str(root_a / "scripts/tool.py")},
    )
    monkeypatch.setattr(
        sequence_checked_exec.work_memory, "cmd_execution_claim",
        lambda args: pytest.fail("mismatched script must not be claimed"),
    )
    monkeypatch.setattr(
        sequence_checked_exec.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("mismatched script must not execute"),
    )
    args = SimpleNamespace(
        task_id="task", run_id="run", context_id="context", step_ordinal=0,
        step_id="step", source="script", source_ref="scripts/tool.py",
        source_ref_repository="repo-a", evidence_text=None, state=None,
        command=["python3", str(root_b / "scripts/tool.py")],
    )

    with pytest.raises(
        sequence_checked_exec.work_memory.WorkMemoryError,
        match="executed-source-does-not-match-authorized-source",
    ):
        sequence_checked_exec.run(args)


def test_checked_exec_never_dispatches_without_context(monkeypatch):
    monkeypatch.setattr(sequence_checked_exec.work_memory, "load_ledger", lambda: ([], "hash"))
    monkeypatch.setattr(sequence_checked_exec.work_memory, "_run_state", lambda events, run_id: ({}, []))
    args = SimpleNamespace(
        task_id="task", run_id="run", context_id="missing", step_ordinal=0,
        step_id="step", source="script", source_ref="scripts/tool.py",
        source_ref_repository="memory-knowledge", evidence_text=None, state=None,
        command=["true"],
    )
    try:
        sequence_checked_exec.run(args)
    except sequence_checked_exec.work_memory.WorkMemoryError as exc:
        assert exc.code == "operation-context-not-found"
    else:
        raise AssertionError("missing context did not fail")
