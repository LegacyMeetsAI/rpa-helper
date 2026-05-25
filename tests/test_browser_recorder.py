from __future__ import annotations

from rpa_helper.core.browser_recorder import (
    BrowserRecorder,
    CommandResult,
    RecordedAction,
    _execute_command_on_page,
    _is_real_url,
    _pick_selector,
    _run_test_step,
    _step_to_command,
    normalize_url,
)
from rpa_helper.core.models import StepType, WorkflowStep


def _action(kind: str, **kwargs) -> RecordedAction:
    return RecordedAction(
        kind=kind,
        candidates=kwargs.get("candidates", []),
        name=kwargs.get("name", ""),
        tag=kwargs.get("tag", ""),
        value=kwargs.get("value", ""),
        url=kwargs.get("url", ""),
        ts=kwargs.get("ts", 0.0),
    )


# --- Selector picking ---------------------------------------------------


def test_pick_selector_prefers_data_testid() -> None:
    a = _action("click", candidates=[
        '[data-testid="submit"]',
        '#root > button:nth-of-type(2)',
    ])
    assert _pick_selector(a) == '[data-testid="submit"]'


def test_pick_selector_prefers_aria_over_css_path() -> None:
    a = _action("click", candidates=[
        '[aria-label="保存"]',
        'div.toolbar > button:nth-of-type(1)',
    ])
    assert _pick_selector(a) == '[aria-label="保存"]'


def test_pick_selector_skips_brittle_css_paths() -> None:
    a = _action("click", candidates=[
        'div#main > section > div:nth-of-type(3) > button',
        '#submit',
    ])
    # First clean candidate after the brittle path.
    assert _pick_selector(a) == "#submit"


def test_pick_selector_falls_back_to_last_when_all_brittle() -> None:
    a = _action("click", candidates=[
        'div > div > button:nth-of-type(2)',
        'main > footer > div:nth-of-type(1) > a',
    ])
    # Both have CSS-path markers; fall back to last.
    assert _pick_selector(a) == 'main > footer > div:nth-of-type(1) > a'


def test_pick_selector_empty_returns_empty() -> None:
    assert _pick_selector(_action("click")) == ""


# --- actions_to_steps conversion ---------------------------------------


def test_navigate_at_start_becomes_browser_open() -> None:
    actions = [_action("navigate", value="https://x.com/")]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 1
    assert steps[0].type == StepType.BROWSER_OPEN
    assert steps[0].raw["url"] == "https://x.com/"


def test_navigate_mid_recording_is_skipped() -> None:
    """SPA-style mid-recording navigation should not pile up open steps."""
    actions = [
        _action("navigate", value="https://x.com/"),
        _action("click", candidates=['[data-testid="row1"]'], name="row1"),
        _action("navigate", value="https://x.com/detail/1"),
        _action("click", candidates=['[data-testid="back"]'], name="back"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    types = [s.type for s in steps]
    assert types == [StepType.BROWSER_OPEN, StepType.BROWSER_CLICK, StepType.BROWSER_CLICK]


def test_click_uses_best_selector_and_name() -> None:
    actions = [_action(
        "click",
        candidates=['[data-testid="submit-btn"]'],
        name="提交申请",
    )]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 1
    assert steps[0].type == StepType.BROWSER_CLICK
    assert steps[0].raw["selector"] == '[data-testid="submit-btn"]'
    assert "提交申请" in steps[0].name


def test_click_without_selector_is_dropped() -> None:
    actions = [_action("click", candidates=[], name="ghost")]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert steps == []


def test_input_collapses_repeated_keystrokes() -> None:
    actions = [
        _action("input", candidates=['#user'], value="a"),
        _action("input", candidates=['#user'], value="ab"),
        _action("input", candidates=['#user'], value="abc"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 1
    assert steps[0].type == StepType.BROWSER_INPUT
    assert steps[0].raw["text"] == "abc"  # final value wins


def test_click_breaks_input_collapse() -> None:
    """If a click happens between inputs, the second input gets its own step."""
    actions = [
        _action("input", candidates=['#user'], value="alice"),
        _action("click", candidates=['#submit']),
        _action("input", candidates=['#user'], value="bob"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    types = [s.type for s in steps]
    assert types == [
        StepType.BROWSER_INPUT,
        StepType.BROWSER_CLICK,
        StepType.BROWSER_INPUT,
    ]
    assert steps[0].raw["text"] == "alice"
    assert steps[2].raw["text"] == "bob"


def test_inputs_to_different_fields_kept_separate() -> None:
    actions = [
        _action("input", candidates=['#user'], value="alice"),
        _action("input", candidates=['#password'], value="secret"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 2
    assert steps[0].raw["selector"] == '#user'
    assert steps[1].raw["selector"] == '#password'


def test_realistic_login_flow() -> None:
    """A realistic recording: navigate, type user, type pass, click submit."""
    actions = [
        _action("navigate", value="https://oa.example.com/login"),
        _action("input", candidates=['[data-testid="user"]'], value="alice"),
        _action("input", candidates=['[data-testid="pass"]'], value="secret"),
        _action(
            "click",
            candidates=['[data-testid="login-btn"]'],
            name="登录",
        ),
        _action("navigate", value="https://oa.example.com/home"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    types = [s.type for s in steps]
    assert types == [
        StepType.BROWSER_OPEN,
        StepType.BROWSER_INPUT,
        StepType.BROWSER_INPUT,
        StepType.BROWSER_CLICK,
    ]
    assert steps[0].raw["url"] == "https://oa.example.com/login"
    assert steps[1].raw["text"] == "alice"
    assert steps[2].raw["text"] == "secret"
    assert "登录" in steps[3].name


def test_submit_event_does_not_create_step() -> None:
    actions = [
        _action("click", candidates=['[data-testid="submit"]'], name="Submit"),
        _action("submit", candidates=[], tag="form"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 1
    assert steps[0].type == StepType.BROWSER_CLICK


# --- Command serialization ----------------------------------------------


def test_step_to_command_serializes_click() -> None:
    step = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="click submit",
        raw={
            "type": "browser_click",
            "selector": "#submit",
            "timeout": 15,
        },
    )
    cmd = _step_to_command(step)
    assert cmd == {
        "type": "browser_click",
        "selector": "#submit",
        "text": "",
        "url": "",
        "attribute": "",
        "timeout": 15,
    }


def test_step_to_command_defaults_timeout() -> None:
    step = WorkflowStep(
        type=StepType.BROWSER_INPUT,
        name="input",
        raw={"type": "browser_input", "selector": "#u", "text": "alice"},
    )
    cmd = _step_to_command(step)
    assert cmd["text"] == "alice"
    assert cmd["timeout"] == 10  # default when omitted


def test_step_to_command_handles_extract_attribute() -> None:
    step = WorkflowStep(
        type=StepType.BROWSER_EXTRACT,
        name="extract id",
        raw={
            "type": "browser_extract",
            "selector": ".id",
            "attribute": "data-value",
        },
    )
    cmd = _step_to_command(step)
    assert cmd["attribute"] == "data-value"


# --- _run_test_step against a fake page ---------------------------------


class _FakeLocator:
    def __init__(self, page, selector: str, attr_value: str = "X") -> None:
        self._page = page
        self._selector = selector
        self._attr_value = attr_value
        self.first = self

    def get_attribute(self, name, timeout=None):  # noqa: ARG002
        self._page.calls.append(("get_attribute", self._selector, name))
        return self._attr_value


class _FakePage:
    """Minimal stand-in implementing only the methods _run_test_step calls."""

    def __init__(self, *, raise_on: str | None = None) -> None:
        self.calls: list[tuple] = []
        self.raise_on = raise_on

    def _maybe_raise(self, name: str) -> None:
        if self.raise_on == name:
            raise RuntimeError(f"boom: {name}")

    def goto(self, url, wait_until=None, timeout=None):  # noqa: ARG002
        self._maybe_raise("goto")
        self.calls.append(("goto", url))

    def click(self, selector, timeout=None):  # noqa: ARG002
        self._maybe_raise("click")
        self.calls.append(("click", selector))

    def fill(self, selector, text, timeout=None):  # noqa: ARG002
        self._maybe_raise("fill")
        self.calls.append(("fill", selector, text))

    def wait_for_selector(self, selector, timeout=None):  # noqa: ARG002
        self._maybe_raise("wait_for_selector")
        self.calls.append(("wait_for_selector", selector))

    def text_content(self, selector, timeout=None):  # noqa: ARG002
        self._maybe_raise("text_content")
        self.calls.append(("text_content", selector))
        return "  hello world  "

    def go_back(self):
        self._maybe_raise("go_back")
        self.calls.append(("go_back",))

    def locator(self, selector):
        return _FakeLocator(self, selector)


def test_run_test_step_open_calls_goto() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_open", "url": "https://x.com/", "timeout": 5})
    assert result.ok
    assert ("goto", "https://x.com/") in page.calls


def test_run_test_step_open_requires_url() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_open", "url": "", "timeout": 5})
    assert not result.ok
    assert "url" in result.message


def test_run_test_step_click_succeeds() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_click", "selector": "#go", "timeout": 5})
    assert result.ok
    assert ("click", "#go") in page.calls


def test_run_test_step_click_requires_selector() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_click", "selector": "", "timeout": 5})
    assert not result.ok
    assert "选择器" in result.message


def test_run_test_step_input_fills_value() -> None:
    page = _FakePage()
    result = _run_test_step(
        page,
        {"type": "browser_input", "selector": "#u", "text": "alice", "timeout": 5},
    )
    assert result.ok
    assert ("fill", "#u", "alice") in page.calls


def test_run_test_step_wait_for() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_wait_for", "selector": "#x", "timeout": 5})
    assert result.ok
    assert ("wait_for_selector", "#x") in page.calls


def test_run_test_step_extract_text_trims() -> None:
    page = _FakePage()
    result = _run_test_step(
        page,
        {"type": "browser_extract", "selector": ".x", "attribute": "", "timeout": 5},
    )
    assert result.ok
    assert result.detail == "hello world"


def test_run_test_step_extract_attribute() -> None:
    page = _FakePage()
    result = _run_test_step(
        page,
        {"type": "browser_extract", "selector": ".x", "attribute": "data-id", "timeout": 5},
    )
    assert result.ok
    assert result.detail == "X"
    assert ("get_attribute", ".x", "data-id") in page.calls


def test_run_test_step_go_back() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_go_back", "timeout": 5})
    assert result.ok
    assert ("go_back",) in page.calls


def test_run_test_step_unknown_type() -> None:
    page = _FakePage()
    result = _run_test_step(page, {"type": "browser_screenshot", "timeout": 5})
    assert not result.ok
    assert "不支持" in result.message


def test_run_test_step_wraps_exceptions_into_message() -> None:
    page = _FakePage(raise_on="click")
    result = _run_test_step(
        page, {"type": "browser_click", "selector": "#go", "timeout": 5},
    )
    assert not result.ok
    assert "boom" in result.message


# --- _execute_command_on_page dispatcher --------------------------------


def test_execute_command_unknown_kind() -> None:
    page = _FakePage()
    result = _execute_command_on_page(page, "explode", {})
    assert not result.ok
    assert "未知命令" in result.message


def test_execute_command_highlight_empty_selector_rejected() -> None:
    page = _FakePage()
    result = _execute_command_on_page(page, "highlight", {"selector": "  "})
    assert not result.ok
    assert "选择器为空" in result.message


def test_execute_command_test_step_dispatches() -> None:
    page = _FakePage()
    result = _execute_command_on_page(
        page,
        "test_step",
        {"step": {"type": "browser_click", "selector": "#go", "timeout": 5}},
    )
    assert result.ok
    assert ("click", "#go") in page.calls


# --- BrowserRecorder.submit_command guard rails -------------------------


def test_submit_command_returns_failure_when_not_recording() -> None:
    rec = BrowserRecorder()
    # Without start(), is_recording() is False.
    step = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="x",
        raw={"type": "browser_click", "selector": "#go"},
    )
    result = rec.test_step(step, timeout=0.1)
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert "未运行" in result.message


def test_highlight_selector_returns_failure_when_not_recording() -> None:
    rec = BrowserRecorder()
    result = rec.highlight_selector("#x", timeout=0.1)
    assert not result.ok
    assert "未运行" in result.message


def test_command_result_defaults() -> None:
    r = CommandResult(ok=True)
    assert r.message == ""
    assert r.detail is None


# --- URL normalization --------------------------------------------------


def test_normalize_url_adds_https_when_missing() -> None:
    assert normalize_url("www.baidu.com") == "https://www.baidu.com"
    assert normalize_url("example.com/path") == "https://example.com/path"


def test_normalize_url_preserves_existing_scheme() -> None:
    assert normalize_url("https://x.com") == "https://x.com"
    assert normalize_url("http://x.com") == "http://x.com"
    assert normalize_url("file:///c:/x") == "file:///c:/x"


def test_normalize_url_empty_stays_empty() -> None:
    assert normalize_url("") == ""
    assert normalize_url("   ") == ""


def test_normalize_url_strips_whitespace() -> None:
    assert normalize_url("  www.x.com  ") == "https://www.x.com"


def test_is_real_url_rejects_browser_internal() -> None:
    assert not _is_real_url("about:blank")
    assert not _is_real_url("about:newtab")
    assert not _is_real_url("chrome://newtab")
    assert not _is_real_url("edge://settings")
    assert not _is_real_url("data:text/html,<h1>x</h1>")
    assert not _is_real_url("")


def test_is_real_url_accepts_http_https() -> None:
    assert _is_real_url("http://x.com")
    assert _is_real_url("https://x.com/path?q=1")


# --- Synthesizing browser_open when no navigate event was captured ------


def test_click_without_navigate_synthesizes_browser_open_from_url() -> None:
    """User typed URL into the address bar (no navigate event) then clicked.

    The recorder must still produce a runnable workflow that opens the page.
    """
    actions = [
        _action(
            "click",
            candidates=['#kw'],
            name="搜索框",
            url="https://www.baidu.com/",
        ),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 2
    assert steps[0].type == StepType.BROWSER_OPEN
    assert steps[0].raw["url"] == "https://www.baidu.com/"
    assert steps[1].type == StepType.BROWSER_CLICK


def test_input_without_navigate_synthesizes_browser_open() -> None:
    actions = [
        _action(
            "input",
            candidates=['#q'],
            value="hello",
            url="https://www.baidu.com/",
        ),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 2
    assert steps[0].type == StepType.BROWSER_OPEN
    assert steps[0].raw["url"] == "https://www.baidu.com/"


def test_about_blank_navigate_does_not_become_browser_open() -> None:
    """A navigate event with about:blank should be ignored, not produce a
    broken browser_open step."""
    actions = [
        _action("navigate", value="about:blank", url="about:blank"),
        _action(
            "click",
            candidates=['#kw'],
            url="https://www.baidu.com/",
        ),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    # First step should be open(baidu), not open(about:blank).
    assert steps[0].type == StepType.BROWSER_OPEN
    assert steps[0].raw["url"] == "https://www.baidu.com/"


def test_existing_browser_open_not_duplicated_by_synthesis() -> None:
    """If a real navigate already produced browser_open, subsequent clicks
    must not insert a second one."""
    actions = [
        _action("navigate", value="https://x.com/", url="https://x.com/"),
        _action("click", candidates=['#a'], url="https://x.com/"),
        _action("click", candidates=['#b'], url="https://x.com/"),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    open_count = sum(1 for s in steps if s.type == StepType.BROWSER_OPEN)
    assert open_count == 1


def test_click_with_no_page_url_drops_synthesis_but_keeps_click() -> None:
    """If we somehow have no URL at all, don't synthesize, but the click
    should still be emitted so the user sees something happened."""
    actions = [
        _action("click", candidates=['#a'], url=""),
    ]
    steps = BrowserRecorder.actions_to_steps(actions)
    assert len(steps) == 1
    assert steps[0].type == StepType.BROWSER_CLICK
