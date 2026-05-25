"""StepDialog 表单字段描述符。

把 UI 表单写成「数据结构 + 渲染器」而不是手工搭控件，可以让
step_dialog.py 在新增步骤类型时完全不用改：只在 step_schemas 里
追加 FormField 列表即可。

Author: huaiqing.wang
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FormField:
    """StepDialog 中的一行表单字段。

    key         对应 YAML 中的字段名；hint 类型用空串占位
    label       行首文字（必填字段会自动加 *）
    kind        控件种类：text / multiline / int / float / bool / choice / hint / child_steps
    default     初值
    placeholder 占位提示
    min/max/step 仅数值类型使用
    choices     choice 类型的下拉选项列表 [(显示文本, 真实值), ...]
    required    True 时 StepDialog 会做非空校验
    help        显示在控件下方的灰色说明文字
    """

    key: str
    label: str
    kind: str
    default: Any = None
    placeholder: str = ""
    min: float = 0
    max: float = 1_000_000
    step: float = 1
    choices: list[tuple[str, Any]] = field(default_factory=list)
    required: bool = False
    help: str = ""


# 下面是便捷工厂函数，让 step_schemas 写起来更紧凑。

def text(key: str, label: str, *, default: str = "", placeholder: str = "",
         required: bool = False, help: str = "") -> FormField:
    """单行文本输入框。"""
    return FormField(key=key, label=label, kind="text", default=default,
                     placeholder=placeholder, required=required, help=help)


def multiline(key: str, label: str, *, default: str = "", placeholder: str = "",
              required: bool = False, help: str = "") -> FormField:
    """多行文本输入框（for_each 列表项用）。"""
    return FormField(key=key, label=label, kind="multiline", default=default,
                     placeholder=placeholder, required=required, help=help)


def integer(key: str, label: str, *, default: int = 0, min: int = 0,
            max: int = 1_000_000, help: str = "") -> FormField:
    """整数输入框（超时秒数、最大循环次数等）。"""
    return FormField(key=key, label=label, kind="int", default=default,
                     min=min, max=max, help=help)


def number(key: str, label: str, *, default: float = 0.0, min: float = 0,
           max: float = 1_000_000, step: float = 0.1, help: str = "") -> FormField:
    """浮点数输入框（等待秒数）。"""
    return FormField(key=key, label=label, kind="float", default=default,
                     min=min, max=max, step=step, help=help)


def boolean(key: str, label: str, *, default: bool = False, help: str = "") -> FormField:
    """复选框（无界面运行等开关）。"""
    return FormField(key=key, label=label, kind="bool", default=default, help=help)


def choice(key: str, label: str, choices: list[tuple[str, Any]], *,
           default: Any = None, help: str = "") -> FormField:
    """下拉选择框。"""
    return FormField(key=key, label=label, kind="choice", choices=choices,
                     default=default, help=help)


def hint(label: str) -> FormField:
    """整行说明文字（不带控件）。"""
    return FormField(key="", label=label, kind="hint")


def child_steps(key: str = "steps", label: str = "子步骤") -> FormField:
    """for_each 步骤的子步骤编辑器。"""
    return FormField(key=key, label=label, kind="child_steps")
