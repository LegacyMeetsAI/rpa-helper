"""读取并校验 YAML 流程文件。

加载器只关心结构合法（type、必填字段），具体步骤怎么执行交给
core/step_handlers。新流程允许 steps 为空数组，用户在 UI 中陆续添加。

Author: huaiqing.wang
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rpa_helper.core.models import StepType, Workflow, WorkflowStep
from rpa_helper.core.step_handlers import HandlerNotFoundError, get_handler


class WorkflowLoadError(ValueError):
    """流程 YAML 文件无法加载或校验失败时抛出。"""


def load_workflow(path: Path) -> Workflow:
    """读取一份流程 YAML，返回 Workflow 数据类。"""
    if not path.exists():
        raise WorkflowLoadError(f"流程文件不存在: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise WorkflowLoadError("流程文件必须是 YAML 对象")

    name = data.get("name")
    if not name:
        raise WorkflowLoadError("流程缺少 name")

    # steps 允许缺省或为空列表（新建流程的初始状态）。
    raw_steps = data.get("steps") or []
    if not isinstance(raw_steps, list):
        raise WorkflowLoadError("steps 必须是数组")

    steps = [_parse_step(index, raw_step) for index, raw_step in enumerate(raw_steps, start=1)]
    return Workflow(name=str(name), steps=steps)


def _parse_step(index: int, raw_step: Any) -> WorkflowStep:
    """把 YAML 中的一个步骤字典解析为 WorkflowStep。"""
    if not isinstance(raw_step, dict):
        raise WorkflowLoadError(f"第 {index} 步必须是 YAML 对象")

    raw_type = raw_step.get("type")
    try:
        step_type = StepType(str(raw_type))
    except ValueError as exc:
        raise WorkflowLoadError(f"第 {index} 步 type 不支持: {raw_type}") from exc

    try:
        handler = get_handler(step_type)
    except HandlerNotFoundError as exc:
        raise WorkflowLoadError(f"第 {index} 步无可用处理器: {step_type}") from exc

    # 必填字段缺失时立刻报错，避免在执行阶段才抛 KeyError。
    missing = [field for field in handler.required_fields() if field not in raw_step]
    if missing:
        raise WorkflowLoadError(f"第 {index} 步缺少字段: {', '.join(missing)}")

    default_name = handler.default_name(raw_step, index)
    return WorkflowStep(
        type=step_type,
        name=str(raw_step.get("name") or default_name),
        raw=raw_step,
    )
