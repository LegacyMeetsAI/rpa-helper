"""Workflow / WorkflowStep / StepType 数据模型测试。

Author: huaiqing.wang
"""
from __future__ import annotations

from rpa_helper.core.models import StepType, Workflow, WorkflowStep


def _step(seconds: float = 1) -> WorkflowStep:
    return WorkflowStep(
        type=StepType.WAIT,
        name=f"等待 {seconds}s",
        raw={"type": "wait", "seconds": seconds},
    )


def test_step_property_defaults() -> None:
    s = WorkflowStep(type=StepType.WAIT, name="wait", raw={"seconds": 2})
    assert s.seconds == 2.0
    # timeout 在 wait 步骤里没意义，但属性应当返回默认值。
    assert s.timeout == 10.0


def test_browser_step_property_overrides() -> None:
    s = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="click",
        raw={"selector": ".btn", "timeout": 5},
    )
    assert s.selector == ".btn"
    assert s.timeout == 5.0


def test_workflow_snapshot_is_deep_copy() -> None:
    original = Workflow(name="wf", steps=[_step(1), _step(2)])
    snapshot = original.snapshot()

    assert len(snapshot.steps) == 2
    snapshot.steps.append(_step(3))
    assert len(original.steps) == 2, "snapshot 必须不影响原 workflow"


def test_workflow_snapshot_raw_dict_isolated() -> None:
    """改 snapshot 中的 raw dict 不能影响原 workflow。"""
    original = Workflow(name="wf", steps=[_step(1)])
    snapshot = original.snapshot()

    snapshot.steps[0].raw["seconds"] = 999
    assert original.steps[0].raw["seconds"] == 1


def test_workflow_default_steps_is_empty_list() -> None:
    w = Workflow(name="empty")
    assert w.steps == []


def test_step_type_enum_values() -> None:
    assert StepType.WAIT.value == "wait"
    assert StepType.CONFIRM.value == "confirm"
    assert StepType.BROWSER_OPEN.value == "browser_open"
    assert StepType.BROWSER_CLICK.value == "browser_click"
    assert StepType.FOR_EACH.value == "for_each"
