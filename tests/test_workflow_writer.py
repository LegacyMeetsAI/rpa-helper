"""workflow_writer 单元测试。

Author: huaiqing.wang
"""
from __future__ import annotations

from pathlib import Path

import yaml

from rpa_helper.core.models import StepType, Workflow, WorkflowStep
from rpa_helper.core.workflow_loader import load_workflow
from rpa_helper.core.workflow_writer import save_workflow


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    workflow = Workflow(
        name="测试流程",
        steps=[
            WorkflowStep(
                type=StepType.BROWSER_CLICK,
                name="click button",
                raw={"selector": ".submit", "timeout": 5},
            ),
            WorkflowStep(
                type=StepType.BROWSER_INPUT,
                name="type chinese",
                raw={"selector": "#q", "text": "门诊查询"},
            ),
        ],
    )
    path = tmp_path / "wf.yaml"
    save_workflow(path, workflow)

    loaded = load_workflow(path)
    assert loaded.name == "测试流程"
    assert len(loaded.steps) == 2
    assert loaded.steps[0].selector == ".submit"
    assert loaded.steps[0].timeout == 5
    assert loaded.steps[1].text == "门诊查询"


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "wf.yaml"
    workflow = Workflow(
        name="x",
        steps=[WorkflowStep(type=StepType.WAIT, name="w", raw={"seconds": 1})],
    )
    save_workflow(target, workflow)
    assert target.exists()


def test_save_writes_unicode_unescaped(tmp_path: Path) -> None:
    workflow = Workflow(
        name="中文流程",
        steps=[
            WorkflowStep(
                type=StepType.CONFIRM, name="确认", raw={"message": "病历号正确？"}
            )
        ],
    )
    path = tmp_path / "u.yaml"
    save_workflow(path, workflow)
    text = path.read_text(encoding="utf-8")
    assert "中文流程" in text
    assert "病历号" in text


def test_save_preserves_step_type_and_name(tmp_path: Path) -> None:
    workflow = Workflow(
        name="t",
        steps=[
            WorkflowStep(type=StepType.WAIT, name="custom", raw={"seconds": 2})
        ],
    )
    path = tmp_path / "wf.yaml"
    save_workflow(path, workflow)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["steps"][0]["type"] == "wait"
    assert data["steps"][0]["name"] == "custom"
    assert data["steps"][0]["seconds"] == 2
