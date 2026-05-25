from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rpa_helper.core.models import StepType
from rpa_helper.core.workflow_loader import WorkflowLoadError, load_workflow


def _write(tmp_path: Path, data: dict | str) -> Path:
    target = tmp_path / "workflow.yaml"
    if isinstance(data, str):
        target.write_text(data, encoding="utf-8")
    else:
        target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target


def test_load_minimal_workflow(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "name": "test",
            "steps": [
                {"type": "wait", "seconds": 1},
                {"type": "confirm", "message": "继续？"},
            ],
        },
    )

    workflow = load_workflow(path)

    assert workflow.name == "test"
    assert len(workflow.steps) == 2
    assert workflow.steps[0].type == StepType.WAIT
    assert workflow.steps[1].type == StepType.CONFIRM
    assert workflow.steps[1].message == "继续？"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(WorkflowLoadError, match="流程文件不存在"):
        load_workflow(tmp_path / "missing.yaml")


def test_missing_name_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"steps": [{"type": "wait", "seconds": 1}]})
    with pytest.raises(WorkflowLoadError, match="name"):
        load_workflow(path)


def test_empty_steps_allowed(tmp_path: Path) -> None:
    """空 steps 数组合法 —— 新建流程会先写空再让用户加步骤。"""
    path = _write(tmp_path, {"name": "x", "steps": []})
    workflow = load_workflow(path)
    assert workflow.steps == []


def test_unknown_step_type_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"name": "x", "steps": [{"type": "fly"}]})
    with pytest.raises(WorkflowLoadError, match="type"):
        load_workflow(path)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    # browser_click 必填 selector，缺失时应当报错。
    path = _write(tmp_path, {"name": "x", "steps": [{"type": "browser_click"}]})
    with pytest.raises(WorkflowLoadError, match="selector"):
        load_workflow(path)


def test_default_name_assigned(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"name": "x", "steps": [{"type": "wait", "seconds": 3}]},
    )
    workflow = load_workflow(path)
    assert "3" in workflow.steps[0].name


def test_explicit_name_preserved(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "name": "x",
            "steps": [{"type": "wait", "seconds": 1, "name": "custom-name"}],
        },
    )
    workflow = load_workflow(path)
    assert workflow.steps[0].name == "custom-name"


def test_yaml_is_not_object_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(WorkflowLoadError, match="YAML 对象"):
        load_workflow(path)


def test_safe_load_not_executable(tmp_path: Path) -> None:
    """Ensure yaml.safe_load is used — !!python/object tags must be rejected."""
    dangerous = (
        "name: x\n"
        "steps:\n"
        "  - type: wait\n"
        "    seconds: !!python/object/apply:os.system ['echo pwned']\n"
    )
    path = _write(tmp_path, dangerous)
    with pytest.raises(Exception):
        load_workflow(path)
