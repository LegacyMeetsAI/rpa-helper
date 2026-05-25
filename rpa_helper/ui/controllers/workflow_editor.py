"""对 Workflow.steps 列表的增删改查操作。

纯逻辑层，不依赖 Qt；UI 端把这些方法接入按钮和列表控件，并自行处理
弹窗确认与刷新展示。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import Workflow, WorkflowStep


class WorkflowEditor:
    """围绕一个 Workflow 实例进行步骤编辑。"""

    def __init__(self, workflow: Workflow) -> None:
        self.workflow = workflow

    def add(self, step: WorkflowStep) -> None:
        """追加一个步骤到末尾。"""
        self.workflow.steps.append(step)

    def replace(self, index: int, step: WorkflowStep) -> None:
        """用 step 覆盖第 index 项。"""
        self._check_index(index)
        self.workflow.steps[index] = step

    def delete(self, index: int) -> WorkflowStep:
        """删除第 index 项并返回被删除的步骤。"""
        self._check_index(index)
        return self.workflow.steps.pop(index)

    def clear(self) -> None:
        """清空所有步骤。"""
        self.workflow.steps.clear()

    def move(self, index: int, direction: int) -> int:
        """上移 (-1) 或下移 (+1) 一项，返回移动后的新索引。"""
        target = index + direction
        self._check_index(index)
        # 已在两端时静默不动；UI 不必先做边界判断。
        if target < 0 or target >= len(self.workflow.steps):
            return index
        self.workflow.steps[index], self.workflow.steps[target] = (
            self.workflow.steps[target],
            self.workflow.steps[index],
        )
        return target

    def extend(self, steps: list[WorkflowStep]) -> None:
        """批量追加（用于浏览器录制结束后一次性导入）。"""
        self.workflow.steps.extend(steps)

    def _check_index(self, index: int) -> None:
        if index < 0 or index >= len(self.workflow.steps):
            raise IndexError(f"步骤索引越界: {index}")
