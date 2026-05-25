"""流程文本字段的占位符渲染器。

把步骤里 {{today}} / {{prompt:label}} / {{env:VAR}} / {{var_name}}
之类的标记替换成具体值。静态占位符立即解析；prompt 类型回调到
UI 弹窗让用户实时输入。

语法：
  {{today}}                   -> YYYY-MM-DD
  {{now}}                     -> YYYY-MM-DD HH:MM:SS
  {{date:%Y%m%d}}             -> 自定义 strftime 格式
  {{env:HOSTNAME}}            -> os.environ.get("HOSTNAME", "")
  {{prompt:label}}            -> 运行时由用户输入（同一次执行只问一次）
  {{prompt:label|default=X}}  -> 同上，附带默认值
  {{order_id}}                -> 取自 VariableStore（browser_extract / for_each 写入）

Author: huaiqing.wang
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from rpa_helper.core.variable_store import VariableStore


PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

PromptCallback = Callable[[str, str], str]


@dataclass
class PlaceholderRenderer:
    """渲染 {{...}} 占位符；每次流程执行新建一个实例。

    _prompt_cache 让同一次执行内重复出现的 {{prompt:病历号}} 只弹一次窗。
    """

    prompt_callback: PromptCallback | None = None
    now: datetime = field(default_factory=datetime.now)
    variables: VariableStore = field(default_factory=VariableStore)
    _prompt_cache: dict[str, str] = field(default_factory=dict)

    def render(self, template: str) -> str:
        if not template or "{{" not in template:
            return template
        return PLACEHOLDER_RE.sub(self._resolve, template)

    def _resolve(self, match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body:
            return match.group(0)

        if ":" in body:
            kind, _, rest = body.partition(":")
            kind = kind.strip().lower()
            rest = rest.strip()
        else:
            kind, rest = body.lower(), ""

        if kind == "today":
            return self.now.strftime("%Y-%m-%d")
        if kind == "now":
            return self.now.strftime("%Y-%m-%d %H:%M:%S")
        if kind == "date":
            fmt = rest or "%Y-%m-%d"
            try:
                return self.now.strftime(fmt)
            except (ValueError, TypeError):
                return match.group(0)
        if kind == "env":
            return os.environ.get(rest, "")
        if kind == "prompt":
            return self._handle_prompt(rest)

        # Fall back to variable lookup. Bare {{name}} reads VariableStore.
        if self.variables.has(body):
            return self.variables.get(body)

        return match.group(0)

    def _handle_prompt(self, spec: str) -> str:
        label, default = spec, ""
        if "|" in spec:
            label, _, options = spec.partition("|")
            label = label.strip()
            for opt in options.split("|"):
                key, _, val = opt.partition("=")
                if key.strip().lower() == "default":
                    default = val.strip()
        if label in self._prompt_cache:
            return self._prompt_cache[label]

        if self.prompt_callback is None:
            return default
        try:
            value = self.prompt_callback(label, default)
        except Exception:
            value = default
        self._prompt_cache[label] = value
        return value
