from __future__ import annotations

from rpa_helper.core.variable_store import VariableStore


def test_set_get_basic() -> None:
    s = VariableStore()
    s.set("a", "1")
    assert s.get("a") == "1"


def test_get_missing_returns_default() -> None:
    s = VariableStore()
    assert s.get("missing") == ""
    assert s.get("missing", "fallback") == "fallback"


def test_has_returns_correctly() -> None:
    s = VariableStore()
    s.set("a", "1")
    assert s.has("a") is True
    assert s.has("b") is False


def test_scope_isolates_writes() -> None:
    s = VariableStore()
    s.set("outer", "O")
    with s.scope(item="X"):
        assert s.get("item") == "X"
        assert s.get("outer") == "O"  # outer still visible
        s.set("inner_only", "Y")
    # After scope exit, scope-local vars are gone.
    assert s.get("item") == ""
    assert s.get("inner_only") == ""
    assert s.get("outer") == "O"


def test_nested_scopes() -> None:
    s = VariableStore()
    with s.scope(a="A1"):
        with s.scope(a="A2"):
            assert s.get("a") == "A2"  # inner shadows outer
        assert s.get("a") == "A1"
    assert s.get("a") == ""


def test_as_dict_merges_scopes() -> None:
    s = VariableStore()
    s.set("a", "1")
    with s.scope(b="2"):
        merged = s.as_dict()
        assert merged == {"a": "1", "b": "2"}
