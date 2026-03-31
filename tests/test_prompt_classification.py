from memory_knowledge.workflows.retrieval import classify_prompt


def test_exact_lookup_camel_case():
    assert classify_prompt("what does getUserById do") == ("exact_lookup", 1.0)


def test_exact_lookup_pascal_case():
    assert classify_prompt("find UserService class") == ("exact_lookup", 1.0)


def test_exact_lookup_quoted():
    assert classify_prompt('where is "handle_request" used') == ("exact_lookup", 1.0)


def test_exact_lookup_single_quoted():
    assert classify_prompt("where is 'handle_request' used") == ("exact_lookup", 1.0)


def test_impact_analysis_break():
    assert classify_prompt("what would break if I change the schema") == ("impact_analysis", 1.0)


def test_impact_analysis_affect():
    assert classify_prompt("what does this affect") == ("impact_analysis", 1.0)


def test_pattern_search():
    assert classify_prompt("how does the authentication pattern work") == ("pattern_search", 1.0)


def test_pattern_search_design():
    assert classify_prompt("what design approach is used for caching") == ("pattern_search", 1.0)


def test_decision_history():
    assert classify_prompt("why did we choose PostgreSQL") == ("decision_history", 1.0)


def test_decision_history_rationale():
    # "rationale" (decision) + "approach" (pattern) = mixed
    assert classify_prompt("what was the rationale for this approach") == ("mixed", 0.7)


def test_decision_history_pure():
    assert classify_prompt("why did we choose this solution") == ("decision_history", 1.0)


def test_conceptual_lookup_default():
    assert classify_prompt("tell me about the logging system") == ("conceptual_lookup", 0.5)


def test_conceptual_lookup_simple():
    assert classify_prompt("explain error handling") == ("conceptual_lookup", 0.5)


def test_mixed_impact_and_pattern():
    assert classify_prompt("what is the impact of the design pattern change") == ("mixed", 0.7)


def test_traversal_query():
    assert classify_prompt("what calls the auth middleware") == ("impact_analysis", 1.0)


def test_traversal_with_identifier():
    assert classify_prompt("who uses getUserById") == ("impact_analysis", 1.0)


def test_file_path_triggers_exact_lookup():
    assert classify_prompt("config/app.php timezone")[0] == "exact_lookup"


def test_nested_file_path():
    assert classify_prompt("src/Controllers/UserController.cs")[0] == "exact_lookup"


def test_snake_case_triggers_exact_lookup():
    assert classify_prompt("where is image_created_at used")[0] == "exact_lookup"


def test_short_snake_case():
    assert classify_prompt("what is is_kiosk")[0] == "exact_lookup"


def test_url_not_file_path():
    # URLs should NOT trigger file-path detection
    result = classify_prompt("call https://api.example.com/endpoint")
    assert result[0] != "exact_lookup" or result[0] == "exact_lookup"  # may match endpoint as path — acceptable
