"""Tests for batched summary generation."""
from memory_knowledge.llm.openai_client import (
    _extract_json_array,
    _format_batch_prompt,
)


def _make_items(n):
    return [
        {
            "index": i + 1,
            "name": f"func_{i}",
            "kind": "function",
            "file": f"src/mod{i}.py",
            "source": f"def func_{i}(): pass",
        }
        for i in range(n)
    ]


def test_format_batch_prompt():
    items = _make_items(3)
    prompt = _format_batch_prompt(items, "python")
    assert "[1] func_0 (function) from src/mod0.py" in prompt
    assert "[2] func_1 (function) from src/mod1.py" in prompt
    assert "[3] func_2 (function) from src/mod2.py" in prompt
    assert "def func_0(): pass" in prompt
    assert "JSON array" in prompt


def test_extract_json_array_clean():
    text = '[{"index": 1, "summary": "Does something."}, {"index": 2, "summary": "Does another."}]'
    result = _extract_json_array(text)
    assert result is not None
    assert len(result) == 2
    assert result[0]["index"] == 1
    assert result[1]["summary"] == "Does another."


def test_extract_json_array_with_fences():
    text = '```json\n[{"index": 1, "summary": "test"}]\n```'
    result = _extract_json_array(text)
    assert result is not None
    assert len(result) == 1
    assert result[0]["summary"] == "test"


def test_extract_json_array_with_preamble():
    text = 'Here are the summaries:\n\n[{"index": 1, "summary": "A summary."}]'
    result = _extract_json_array(text)
    assert result is not None
    assert result[0]["summary"] == "A summary."


def test_extract_json_array_malformed():
    text = "This is not JSON at all. Just some text."
    result = _extract_json_array(text)
    assert result is None


def test_extract_json_array_empty_brackets():
    """Empty array returns None (no summaries to extract)."""
    text = "[]"
    result = _extract_json_array(text)
    # Empty array has no {"index":...} objects, so returns None — correct behavior
    assert result is None


def test_batch_index_matching():
    """Verify items are matched by index, not name."""
    text = '[{"index": 2, "summary": "Second"}, {"index": 1, "summary": "First"}]'
    result = _extract_json_array(text)
    index_map = {r["index"]: r["summary"] for r in result}
    assert index_map[1] == "First"
    assert index_map[2] == "Second"


def test_extract_json_array_with_source_code_brackets():
    """Source code in the prompt echo may contain [ ] that confuse naive parsing."""
    text = (
        'The code uses array[0] and list[i] patterns.\n\n'
        '[{"index": 1, "summary": "Handles arrays."}, {"index": 2, "summary": "Processes lists."}]'
    )
    result = _extract_json_array(text)
    assert result is not None
    assert len(result) == 2
    assert result[0]["index"] == 1


def test_extract_json_array_individual_objects():
    """Some LLMs return one JSON object per line instead of an array."""
    text = (
        '{"index": 1, "summary": "First function."}\n'
        '{"index": 2, "summary": "Second function."}\n'
        '{"index": 3, "summary": "Third function."}'
    )
    result = _extract_json_array(text)
    assert result is not None
    assert len(result) == 3


def test_extract_json_array_with_agent_commentary():
    """Full agent response with reasoning before the JSON."""
    text = (
        "I'll analyze each symbol and provide summaries.\n\n"
        "Here are my findings:\n\n"
        '```json\n'
        '[{"index": 1, "summary": "Validates user input."}, '
        '{"index": 2, "summary": "Sends email notification."}]\n'
        '```\n\n'
        "Let me know if you need more detail."
    )
    result = _extract_json_array(text)
    assert result is not None
    assert len(result) == 2
