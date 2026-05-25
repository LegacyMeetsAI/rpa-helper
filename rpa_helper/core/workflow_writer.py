"""把内存中的 Workflow 写回 YAML 文件。

保留 step.raw 中用户填的字段顺序，同时把 type/name 强制写为权威值，
避免 UI 中改名后磁盘里还是旧的。

Author: huaiqing.wang
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rpa_helper.core.models import Workflow


def save_workflow(path: Path, workflow: Workflow) -> None:
    """把 workflow 序列化为 YAML 写到 path。父目录会自动创建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": workflow.name,
        "steps": [dict(step.raw) for step in workflow.steps],
    }
    # raw 里可能还残留旧的 type/name，统一以 WorkflowStep 中的为准。
    for step, raw in zip(workflow.steps, data["steps"], strict=True):
        raw["type"] = step.type.value
        raw["name"] = step.name

    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
