"""What the goal store concludes — the number, the delta, and what a gate does with them.

On 2026-08-06 the goal changed in conversation while the reported number still came from a string
hardcoded in a per-project script, and that number had moved 303 -> 302 -> 303 on identical bytes
the same morning. Kamen: "this yo yo that you are reporting now up and down depletes the whole
purpose of tracking progress and makes you look completely stupid."

These tests assert what a reader is told, not which function ran: what the report says when a KPI
has never been read, what it says when the measured set grew underneath it, and whether a typed
GOAL line survives the gate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import goal_tracker, script_intake


def _clock(minute: int):
    return lambda: datetime(2026, 8, 6, 12, minute, tzinfo=timezone.utc)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "producer.py").write_text("print('{}')\n")
    return tmp_path


def _answers(**overrides):
    base = {
        "statement": "make the harness reliable so the output docs can be sent to UP",
        "set_by": "Kamen",
        "supersede_reason": "none",
        "kpis": [
            {
                "id": "sendable-documents",
                "question": "how many documents a client could receive, of documents produced",
                "producer": "scripts/producer.py",
                "deterministic": True,
                "direction": "up",
            }
        ],
    }
    return {**base, **overrides}


def _reading(value, total, findings, minute):
    def runner(_repo, _producer):
        payload = {
            "value": value,
            "total": total,
            "source": "artifacts/run",
            "findings": findings,
        }
        return payload, json.dumps(payload)

    return runner, _clock(minute)


class TestWhatTheReportSays:
    def test_a_repo_with_no_goal_says_so_instead_of_showing_a_number(self, repo):
        lines = goal_tracker.report_lines(repo)
        assert lines[0].startswith("GOAL    none declared")
        assert "not comparable" in lines[1]

    def test_a_kpi_never_read_is_not_reported_as_zero(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        lines = goal_tracker.report_lines(repo)
        assert "not yet measured" in lines[0]
        assert "never been read" in lines[1]

    def test_the_delta_names_the_document_that_stopped_failing(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(26, 29, [{"item": "strategy-brief.md", "failed": ["a claim is printed twice"]}], 1)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)
        runner, clock = _reading(27, 29, [], 2)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)

        since = goal_tracker.report_lines(repo)[1]
        assert since.startswith("SINCE   +1")
        assert "fixed: strategy-brief.md" in since

    def test_a_set_that_grew_underneath_the_number_is_declared_not_comparable(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(26, 29, [], 1)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)
        runner, clock = _reading(26, 34, [], 2)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)

        since = goal_tracker.report_lines(repo)[1]
        assert "not comparable" in since
        assert "29" in since and "34" in since


class TestWhatTheGateDoes:
    def test_a_typed_goal_line_is_refused(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(26, 29, [], 1)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)

        ok, why = goal_tracker.check_goal_line(
            repo, "GOAL    requirement coverage of UP's library · 303 of 321"
        )
        assert not ok
        assert "26 of 29" in why

    def test_the_line_the_store_renders_is_accepted(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(26, 29, [], 1)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)

        rendered = goal_tracker.report_lines(repo)[0]
        assert goal_tracker.check_goal_line(repo, rendered)[0]


class TestWhatTheStoreKeeps:
    def test_replacing_a_goal_keeps_the_old_one_and_its_readings(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(26, 29, [], 1)
        goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)
        goal_tracker.set_goal(
            repo,
            _answers(supersede_reason="the documents became sendable and the work moved on"),
            clock=_clock(3),
        )

        data = goal_tracker.load(repo)
        assert [row["id"] for row in data["goals"]] == ["g1", "g2"]
        assert data["goals"][0]["superseded_reason"].startswith("the documents became sendable")
        assert len(data["goals"][0]["measurements"]) == 1
        assert goal_tracker.current_goal(data)["id"] == "g2"

    def test_replacing_a_goal_without_saying_why_is_refused(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        with pytest.raises(SystemExit) as caught:
            goal_tracker.set_goal(repo, _answers(), clock=_clock(1))
        assert "needs a reason" in str(caught.value)

    def test_a_kpi_whose_producer_is_not_a_file_is_refused(self, repo):
        """The intake defect below recorded a producer of "." , and a directory exists."""

        answers = _answers()
        answers["kpis"][0]["producer"] = "."
        with pytest.raises(SystemExit) as caught:
            goal_tracker.set_goal(repo, answers, clock=_clock(0))
        assert "is not a file" in str(caught.value)

    def test_the_findings_are_kept_not_only_the_total(self, repo):
        goal_tracker.set_goal(repo, _answers(), clock=_clock(0))
        runner, clock = _reading(
            26, 29, [{"item": "language-standard.md", "failed": ["a fact starts mid-sentence"]}], 1
        )
        reading = goal_tracker.measure(repo, "sendable-documents", runner=runner, clock=clock)
        assert reading["findings"][0]["item"] == "language-standard.md"
        assert goal_tracker.load(repo)["goals"][0]["measurements"][0]["findings"]


class TestTheIntakeCollectsAMultiLineFieldInsideAList:
    """The defect that recorded a KPI whose producing script was "." .

    `_collect_object_list` routed every item field except string_list and object_list to the
    single-line reader, so a `text` item field consumed one line and left its terminator to be
    eaten as the next answer. Every later field in that item shifted by one.
    """

    def test_the_answers_after_a_multi_line_item_field_are_not_shifted(self):
        spec = {
            "schema_version": script_intake.SCHEMA_VERSION,
            "fields": [
                {
                    "id": "kpis",
                    "prompt": "The KPIs",
                    "response_format": "One per entry.",
                    "example": "sendable-documents",
                    "constraints": "Each needs a producer.",
                    "type": "object_list",
                    "required": True,
                    "item_fields": [
                        {
                            "id": "question",
                            "prompt": "The question",
                            "response_format": "One sentence.",
                            "example": "how many documents",
                            "constraints": "Plain words.",
                            "type": "text",
                            "required": True,
                        },
                        {
                            "id": "producer",
                            "prompt": "The producer",
                            "response_format": "One path.",
                            "example": "scripts/producer.py",
                            "constraints": "A checked-in file.",
                            "type": "path",
                            "required": True,
                        },
                    ],
                }
            ],
        }
        answers = iter(["how many documents", ".", "scripts/producer.py", "no"])
        collected = script_intake.collect(
            spec, input_fn=lambda _prompt: next(answers), output_fn=lambda _message: None
        )
        assert collected["kpis"][0]["producer"] == "scripts/producer.py"


class TestGoalDeclarationControllerHandoff:
    def test_default_set_invocation_still_runs_the_existing_interview(
        self, repo, monkeypatch, capsys,
    ):
        monkeypatch.setattr(script_intake, "collect", lambda spec: _answers())

        assert goal_tracker.main(["--repo", str(repo), "set"]) == 0

        assert goal_tracker.current_goal(goal_tracker.load(repo))["statement"].startswith(
            "make the harness reliable"
        )
        assert "goal g1 recorded" in capsys.readouterr().out

    def test_controller_answers_file_requires_dispatch_and_preserves_the_same_contract(
        self, repo, tmp_path, monkeypatch,
    ):
        artifact_root = tmp_path / "sequence-intake"
        artifact_root.mkdir()
        answers_file = artifact_root / "goal-answers.json"
        answers_file.write_text(json.dumps(_answers()))
        monkeypatch.setattr(
            goal_tracker, "SEQUENCE_INTAKE_ARTIFACT_ROOT", artifact_root,
        )

        with pytest.raises(SystemExit, match="reserved for the authorized sequence controller"):
            goal_tracker.main([
                "--repo", str(repo), "set", "--answers-file", str(answers_file),
            ])

        monkeypatch.setenv(goal_tracker.SEQUENCE_INTAKE_DISPATCH_MARKER, "1")
        assert goal_tracker.main([
            "--repo", str(repo), "set", "--answers-file", str(answers_file),
        ]) == 0
        assert goal_tracker.current_goal(goal_tracker.load(repo))["id"] == "g1"

    def test_goal_producer_cannot_escape_the_selected_repository(self, repo, tmp_path):
        outside = tmp_path / "outside.py"
        outside.write_text("print('{}')\n")
        answers = _answers()
        answers["kpis"][0]["producer"] = str(outside)

        with pytest.raises(SystemExit, match="repository-relative"):
            goal_tracker.set_goal(repo, answers)
