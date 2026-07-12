from memory_knowledge.planning_mcp_boundary import _validate
from memory_knowledge.server import _planning_error_code, _planning_error_data
from memory_knowledge.admin.planning import PlanningValidationError


def test_update_patch_is_recursively_closed_and_typed():
    defect = _validate("update_task", {"task_key": "task", "patch": {"is_runnable": "yes"}})
    assert defect == ("patch.is_runnable", "patch.is_runnable has the wrong type")


def test_boundary_error_precedence_is_schema_ordered():
    defect = _validate("create_task", {"repository_key": "repo", "title": "", "unknown": True})
    assert defect == ("title", "title must not be empty")


def test_external_identity_requires_both_non_null_values():
    defect = _validate(
        "create_task",
        {"title": "Task", "repository_key": "repo", "project_external_system": "clickup"},
    )
    assert defect == (
        "project_external_system",
        "project_external_system and project_external_id must be supplied together",
    )


def test_planning_error_taxonomy_preserves_identity_and_ownership_classes():
    assert _planning_error_code("project_key and external project reference resolve to different projects") == "INVALID_ARGS"
    assert _planning_error_code("feature_key and external feature reference resolve to different features") == "INVALID_ARGS"
    assert _planning_error_code("Repository is not linked to the project") == "REPOSITORY_OUTSIDE_PROJECT"


def test_typed_graph_reference_error_survives_serialization_without_message_matching():
    exc = PlanningValidationError("REFERENCE_NOT_FOUND", "Task not found: parent", field="parent_task_key")
    assert _planning_error_data(exc) == {
        "error_code": "REFERENCE_NOT_FOUND", "field": "parent_task_key"
    }
    exc = PlanningValidationError("REFERENCE_NOT_FOUND", "missing", field="depends_on_task_keys", references=["b", "a"])
    assert _planning_error_data(exc)["references"] == ["a", "b"]
