from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rpa_helper.core.models import StepType, Workflow, WorkflowStep
from rpa_helper.core.safety import SafetyManager
from rpa_helper.core.workflow_engine import WorkflowEngine


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test_browser")
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture
def engine_with_mock_browser(tmp_path: Path, logger, monkeypatch):
    """An engine where _get_browser returns a MagicMock."""
    safety = SafetyManager()
    eng = WorkflowEngine(
        project_root=tmp_path, safety=safety, logger=logger, dry_run=False,
    )
    fake_browser = MagicMock()
    monkeypatch.setattr(eng, "_get_browser", lambda: fake_browser)
    return eng, fake_browser, safety


def _wf(*steps: WorkflowStep) -> Workflow:
    return Workflow(name="t", steps=list(steps))


def test_browser_open_calls_browser_open(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.BROWSER_OPEN,
        name="open",
        raw={"type": "browser_open", "url": "https://example.com"},
    )
    engine.run(_wf(step))
    browser.open.assert_called_once()
    assert browser.open.call_args.kwargs["url"] == "https://example.com"


def test_browser_click_uses_selector(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="click",
        raw={"type": "browser_click", "selector": ".btn"},
    )
    engine.run(_wf(step))
    browser.click.assert_called_once()
    assert browser.click.call_args.args[0] == ".btn"


def test_browser_extract_writes_variable(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    browser.extract_text.return_value = "A001"

    extract = WorkflowStep(
        type=StepType.BROWSER_EXTRACT,
        name="extract",
        raw={
            "type": "browser_extract",
            "selector": ".order",
            "save_as": "order_id",
        },
    )
    # Add a follow-up browser_click step whose selector uses {{order_id}}
    click_with_var = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="click var",
        raw={"type": "browser_click", "selector": ".row-{{order_id}}"},
    )
    engine.run(_wf(extract, click_with_var))

    browser.extract_text.assert_called_once()
    # The follow-up click must have rendered {{order_id}} → A001.
    browser.click.assert_called_once()
    assert browser.click.call_args.args[0] == ".row-A001"


def test_browser_download_renders_save_dir_variable(
    engine_with_mock_browser, tmp_path: Path
) -> None:
    engine, browser, _ = engine_with_mock_browser
    browser.download.return_value = tmp_path / "downloads" / "A001" / "file.pdf"

    extract = WorkflowStep(
        type=StepType.BROWSER_EXTRACT,
        name="ex",
        raw={"type": "browser_extract", "selector": ".id", "save_as": "order_id"},
    )
    browser.extract_text.return_value = "A001"

    download = WorkflowStep(
        type=StepType.BROWSER_DOWNLOAD,
        name="dl",
        raw={
            "type": "browser_download",
            "trigger_selector": ".dl-btn",
            "save_dir": "downloads/{{order_id}}",
        },
    )

    engine.run(_wf(extract, download))
    browser.download.assert_called_once()
    save_dir = browser.download.call_args.kwargs["save_dir"]
    # downloads/A001 — must be project-rooted and contain the rendered var.
    assert "A001" in str(save_dir)


def test_browser_go_back_calls_method(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.BROWSER_GO_BACK,
        name="back",
        raw={"type": "browser_go_back"},
    )
    engine.run(_wf(step))
    browser.go_back.assert_called_once()


def test_for_each_with_items_iterates(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop",
        raw={
            "type": "for_each",
            "items": ["A", "B", "C"],
            "as": "code",
            "steps": [
                {"type": "browser_click", "selector": ".row-{{code}}"},
            ],
        },
    )
    engine.run(_wf(step))
    assert browser.click.call_count == 3
    selectors = [c.args[0] for c in browser.click.call_args_list]
    assert selectors == [".row-A", ".row-B", ".row-C"]


def test_for_each_selector_mode_uses_browser_count(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    browser.count.return_value = 2
    step = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop",
        raw={
            "type": "for_each",
            "selector": ".item",
            "as": "row_index",
            "steps": [
                {"type": "browser_click", "selector": ".item:nth-child({{row_index_one_based}})"},
            ],
        },
    )
    engine.run(_wf(step))
    assert browser.click.call_count == 2
    selectors = [c.args[0] for c in browser.click.call_args_list]
    assert selectors == [".item:nth-child(1)", ".item:nth-child(2)"]


def test_for_each_limit_truncates_items(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop",
        raw={
            "type": "for_each",
            "items": ["A", "B", "C", "D", "E"],
            "as": "x",
            "limit": 2,
            "steps": [{"type": "browser_click", "selector": "[data={{x}}]"}],
        },
    )
    engine.run(_wf(step))
    assert browser.click.call_count == 2


def test_for_each_variable_does_not_leak_after_loop(engine_with_mock_browser) -> None:
    engine, browser, _ = engine_with_mock_browser
    step = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop",
        raw={
            "type": "for_each",
            "items": ["A"],
            "as": "x",
            "steps": [{"type": "browser_click", "selector": "[data={{x}}]"}],
        },
    )
    after = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="after",
        raw={"type": "browser_click", "selector": "[data={{x}}]"},
    )
    engine.run(_wf(step, after))
    # 'x' was scoped to the loop, so the after-step's {{x}} stays literal.
    selectors = [c.args[0] for c in browser.click.call_args_list]
    assert selectors == ["[data=A]", "[data={{x}}]"]


def test_for_each_stop_request_interrupts(engine_with_mock_browser) -> None:
    from threading import Thread
    import time

    engine, browser, safety = engine_with_mock_browser

    # Make each click take a moment so the stop has time to land.
    def slow_click(*args, **kwargs):
        time.sleep(0.05)

    browser.click.side_effect = slow_click

    step = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop",
        raw={
            "type": "for_each",
            "items": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "as": "x",
            "steps": [{"type": "browser_click", "selector": "[data={{x}}]"}],
        },
    )

    def stop_after_delay() -> None:
        time.sleep(0.1)
        safety.request_stop()

    Thread(target=stop_after_delay, daemon=True).start()
    with pytest.raises(InterruptedError):
        engine.run(_wf(step))
    # Should have stopped well before all 10 items completed.
    assert browser.click.call_count < 10
