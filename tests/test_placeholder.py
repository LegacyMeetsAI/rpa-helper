from __future__ import annotations

from datetime import datetime

import pytest

from rpa_helper.core.placeholder import PlaceholderRenderer


def _fixed_now() -> datetime:
    return datetime(2026, 5, 24, 14, 30, 0)


def test_no_placeholders_returns_unchanged() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("plain text") == "plain text"
    assert r.render("") == ""


def test_today_substitution() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("date is {{today}}") == "date is 2026-05-24"


def test_now_substitution() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{now}}") == "2026-05-24 14:30:00"


def test_custom_date_format() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{date:%Y%m%d}}") == "20260524"
    assert r.render("{{date:%H-%M}}") == "14-30"


def test_invalid_date_format_kept_literal() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{date:%Q}}") == "{{date:%Q}}"


def test_env_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOSP_USER", "doctor01")
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("user={{env:HOSP_USER}}") == "user=doctor01"


def test_env_missing_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("[{{env:DOES_NOT_EXIST}}]") == "[]"


def test_prompt_calls_callback() -> None:
    calls = []

    def cb(label: str, default: str) -> str:
        calls.append((label, default))
        return "1234"

    r = PlaceholderRenderer(now=_fixed_now(), prompt_callback=cb)
    assert r.render("ID={{prompt:病历号}}") == "ID=1234"
    assert calls == [("病历号", "")]


def test_prompt_cached_per_run() -> None:
    """Same label asked twice within one run prompts only once."""
    call_count = 0

    def cb(label: str, default: str) -> str:
        nonlocal call_count
        call_count += 1
        return "v"

    r = PlaceholderRenderer(now=_fixed_now(), prompt_callback=cb)
    r.render("{{prompt:x}} and {{prompt:x}}")
    assert call_count == 1


def test_prompt_with_default() -> None:
    captured: list[tuple[str, str]] = []

    def cb(label: str, default: str) -> str:
        captured.append((label, default))
        return default

    r = PlaceholderRenderer(now=_fixed_now(), prompt_callback=cb)
    r.render("{{prompt:科室|default=门诊}}")
    assert captured == [("科室", "门诊")]


def test_prompt_callback_exception_uses_default() -> None:
    def cb(label: str, default: str) -> str:
        raise RuntimeError("UI closed")

    r = PlaceholderRenderer(now=_fixed_now(), prompt_callback=cb)
    assert r.render("{{prompt:x|default=fallback}}") == "fallback"


def test_prompt_no_callback_uses_default() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{prompt:x|default=hello}}") == "hello"


def test_unknown_placeholder_kept_literal() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{mystery}}") == "{{mystery}}"


def test_multiple_placeholders_in_one_string() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    result = r.render("{{today}} - {{date:%H%M}}")
    assert result == "2026-05-24 - 1430"


def test_whitespace_in_braces_tolerated() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{  today  }}") == "2026-05-24"


def test_variable_substitution() -> None:
    from rpa_helper.core.variable_store import VariableStore

    vs = VariableStore()
    vs.set("order_id", "A001")
    r = PlaceholderRenderer(now=_fixed_now(), variables=vs)
    assert r.render("downloads/{{order_id}}/") == "downloads/A001/"


def test_variable_undefined_kept_literal() -> None:
    r = PlaceholderRenderer(now=_fixed_now())
    assert r.render("{{undefined_var}}") == "{{undefined_var}}"


def test_variable_with_scope() -> None:
    from rpa_helper.core.variable_store import VariableStore

    vs = VariableStore()
    r = PlaceholderRenderer(now=_fixed_now(), variables=vs)
    with vs.scope(idx="3"):
        assert r.render("row #{{idx}}") == "row #3"
    assert r.render("row #{{idx}}") == "row #{{idx}}"


def test_builtins_take_precedence_over_variables() -> None:
    """A variable named 'today' must not shadow the {{today}} built-in."""
    from rpa_helper.core.variable_store import VariableStore

    vs = VariableStore()
    vs.set("today", "WRONG")
    r = PlaceholderRenderer(now=_fixed_now(), variables=vs)
    assert r.render("{{today}}") == "2026-05-24"
