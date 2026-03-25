import uuid

from memory_knowledge.identity.entity_key import (
    NAMESPACE_MK,
    chunk_entity_key,
    file_entity_key,
    learned_record_entity_key,
    symbol_entity_key,
)


def test_namespace_is_uuid():
    assert isinstance(NAMESPACE_MK, uuid.UUID)


def test_file_key_deterministic():
    k1 = file_entity_key("repo1", "abc123", "src/main.py")
    k2 = file_entity_key("repo1", "abc123", "src/main.py")
    assert k1 == k2


def test_file_key_unique_by_path():
    k1 = file_entity_key("repo1", "abc123", "src/main.py")
    k2 = file_entity_key("repo1", "abc123", "src/other.py")
    assert k1 != k2


def test_file_key_unique_by_commit():
    k1 = file_entity_key("repo1", "abc123", "src/main.py")
    k2 = file_entity_key("repo1", "def456", "src/main.py")
    assert k1 != k2


def test_file_key_unique_by_repo():
    k1 = file_entity_key("repo1", "abc123", "src/main.py")
    k2 = file_entity_key("repo2", "abc123", "src/main.py")
    assert k1 != k2


def test_symbol_key_deterministic():
    k1 = symbol_entity_key("r", "c", "f.py", "Foo", "class")
    k2 = symbol_entity_key("r", "c", "f.py", "Foo", "class")
    assert k1 == k2


def test_symbol_key_unique_by_kind():
    k1 = symbol_entity_key("r", "c", "f.py", "foo", "function")
    k2 = symbol_entity_key("r", "c", "f.py", "foo", "variable")
    assert k1 != k2


def test_chunk_key_deterministic():
    k1 = chunk_entity_key("r", "c", "f.py", 0)
    k2 = chunk_entity_key("r", "c", "f.py", 0)
    assert k1 == k2


def test_chunk_key_unique_by_index():
    k1 = chunk_entity_key("r", "c", "f.py", 0)
    k2 = chunk_entity_key("r", "c", "f.py", 1)
    assert k1 != k2


def test_learned_record_key_deterministic():
    k1 = learned_record_entity_key("r", "pattern", "hash1")
    k2 = learned_record_entity_key("r", "pattern", "hash1")
    assert k1 == k2


def test_learned_record_key_unique():
    k1 = learned_record_entity_key("r", "pattern", "hash1")
    k2 = learned_record_entity_key("r", "pattern", "hash2")
    assert k1 != k2


def test_all_keys_are_uuid5():
    keys = [
        file_entity_key("r", "c", "f.py"),
        symbol_entity_key("r", "c", "f.py", "s", "function"),
        chunk_entity_key("r", "c", "f.py", 0),
        learned_record_entity_key("r", "t", "h"),
    ]
    for k in keys:
        assert isinstance(k, uuid.UUID)
        assert k.version == 5
