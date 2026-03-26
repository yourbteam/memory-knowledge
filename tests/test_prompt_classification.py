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
    assert classify_prompt("what was the rationale for this approach") == ("decision_history", 1.0)


def test_conceptual_lookup_default():
    assert classify_prompt("tell me about the logging system") == ("conceptual_lookup", 0.5)


def test_conceptual_lookup_simple():
    assert classify_prompt("explain error handling") == ("conceptual_lookup", 0.5)
