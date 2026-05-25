"""WorkflowEngine 单元测试。

Author: huaiqing.wang
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock

import pytest

from rpa_helper.core.models import StepType, Workflow, WorkflowStep
from rpa_helper.core.safety import SafetyManager
from rpa_helper.core.workflow_engine import WorkflowEngine


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test_engine")
    log.handlers.clear()
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture
def engine_factory(tmp_path: Path, logger: logging.Logger):
    def make(dry_run: bool = True) -> tuple[WorkflowEngine, SafetyManager]:
        safety = SafetyManager()
        eng = WorkflowEngine(
            project_root=tmp_path,
            safety=safety,
            logger=logger,
            dry_run=dry_run,
        )
        return eng, safety

    return make


def _wf(*steps: WorkflowStep) -> Workflow:
    return Workflow(name="t", steps=list(steps))


def test_dry_run_wait_step_completes_without_error(engine_factory) -> None:
    engine, _ = engine_factory(dry_run=True)
    wf = _wf(
        WorkflowStep(type=StepType.WAIT, name="w", raw={"type": "wait", "seconds": 0.05})
    )
    # 不抛异常即视为通过。
    engine.run(wf)


def test_stop_during_wait_interrupts_quickly(engine_factory) -> None:
    """长 wait 期间请求停止应在 ~0.2s 内被打断。"""
    import time

    engine, safety = engine_factory(dry_run=False)
    wf = _wf(
        WorkflowStep(type=StepType.WAIT, name="w", raw={"type": "wait", "seconds": 60})
    )

    def stop_after_delay() -> None:
        time.sleep(0.15)
        safety.request_stop()

    Thread(target=stop_after_delay, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(InterruptedError):
        engine.run(wf)
    elapsed = time.monotonic() - started
    assert elapsed < 2, f"中断应该 <2s 内生效，实际 {elapsed:.2f}s"


def test_confirm_callback_invoked(engine_factory) -> None:
    engine, _ = engine_factory(dry_run=False)
    wf = _wf(
        WorkflowStep(
            type=StepType.CONFIRM,
            name="c",
            raw={"type": "confirm", "message": "继续？"},
        )
    )
    callback = MagicMock(return_value=True)
    engine.run(wf, on_confirm=callback)
    callback.assert_called_once_with("继续？")


def test_confirm_returning_false_aborts(engine_factory) -> None:
    engine, _ = engine_factory(dry_run=False)
    wf = _wf(
        WorkflowStep(
            type=StepType.CONFIRM,
            name="c",
            raw={"type": "confirm", "message": "继续？"},
        )
    )
    with pytest.raises(InterruptedError):
        engine.run(wf, on_confirm=lambda msg: False)


def test_step_started_callback_fires_for_each_step(engine_factory) -> None:
    engine, _ = engine_factory(dry_run=True)
    wf = _wf(
        WorkflowStep(type=StepType.WAIT, name="a", raw={"type": "wait", "seconds": 0.01}),
        WorkflowStep(type=StepType.WAIT, name="b", raw={"type": "wait", "seconds": 0.01}),
    )
    callback = MagicMock()
    engine.run(wf, on_step_started=callback)
    assert callback.call_count == 2
    # 步骤序号是 1-based
    assert callback.call_args_list[0].args[0] == 1
    assert callback.call_args_list[1].args[0] == 2
