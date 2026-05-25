"""核心数据模型。

定义流程（Workflow）、步骤（WorkflowStep）、步骤类型（StepType）
以及运行状态（WorkflowStatus）。本模块仅依赖标准库，不引入任何
桌面/浏览器/Qt 相关依赖，便于在测试中独立使用。

Author: huaiqing.wang
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepType(str, Enum):
    """流程支持的步骤类型枚举。

    仅保留浏览器自动化 + 基础控制流（等待 / 人工确认 / 循环）。
    桌面自动化、OCR、图像匹配类型已全部移除。
    """

    # --- 基础控制 ---
    WAIT = "wait"            # 等待 N 秒
    CONFIRM = "confirm"      # 人工确认（弹窗等待用户点继续）

    # --- 浏览器自动化（Playwright） ---
    BROWSER_OPEN = "browser_open"
    BROWSER_CLOSE = "browser_close"
    BROWSER_CLICK = "browser_click"
    BROWSER_INPUT = "browser_input"
    BROWSER_WAIT_FOR = "browser_wait_for"
    BROWSER_EXTRACT = "browser_extract"
    BROWSER_DOWNLOAD = "browser_download"
    BROWSER_GO_BACK = "browser_go_back"

    # --- 控制流 ---
    FOR_EACH = "for_each"    # 循环执行子步骤


class WorkflowStatus(str, Enum):
    """流程运行时状态枚举（UI 状态条会读取该值切换显示）。"""

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkflowStep:
    """单个流程步骤。

    设计上保持不可变（frozen=True），原始 YAML 字段全部保存在 ``raw``
    字典里，常用字段通过属性访问以提供默认值与类型转换。新增字段时
    优先添加属性而不是变更构造签名，避免破坏既有调用方。
    """

    type: StepType
    name: str
    raw: dict[str, Any] = field(default_factory=dict)

    # --- 通用字段 ---

    @property
    def timeout(self) -> float:
        """超时秒数（浏览器步骤通用，默认 10 秒）。"""
        return float(self.raw.get("timeout", 10))

    @property
    def seconds(self) -> float:
        """等待秒数（wait 步骤使用，默认 1 秒）。"""
        return float(self.raw.get("seconds", 1))

    @property
    def message(self) -> str:
        """人工确认弹窗的提示文案（confirm 步骤使用）。"""
        return str(self.raw.get("message", "确认继续？"))

    # --- 浏览器步骤字段 ---

    @property
    def url(self) -> str:
        """浏览器打开的目标 URL（browser_open）。"""
        return str(self.raw.get("url", ""))

    @property
    def selector(self) -> str:
        """CSS 选择器（浏览器点击/输入/等待/提取使用）。"""
        return str(self.raw.get("selector", ""))

    @property
    def text(self) -> str:
        """要输入的文本（browser_input 使用，支持占位符）。"""
        return str(self.raw.get("text", ""))

    @property
    def save_as(self) -> str:
        """提取/下载结果保存到的变量名（后续步骤可用占位符引用）。"""
        return str(self.raw.get("save_as", ""))

    @property
    def attribute(self) -> str:
        """browser_extract 读取的属性名（留空则读取文本内容）。"""
        return str(self.raw.get("attribute", ""))

    @property
    def save_dir(self) -> str:
        """browser_download 的保存目录（相对路径相对项目根）。"""
        return str(self.raw.get("save_dir", "downloads"))

    @property
    def trigger_selector(self) -> str:
        """触发浏览器下载的元素选择器。"""
        return str(self.raw.get("trigger_selector", ""))

    @property
    def user_data_dir(self) -> str:
        """Chromium 持久化用户数据目录（留空 = 每次全新会话）。"""
        return str(self.raw.get("user_data_dir", ""))

    @property
    def headless(self) -> bool:
        """是否以无界面模式运行 Chromium。"""
        return bool(self.raw.get("headless", False))

    @property
    def connect_existing(self) -> bool:
        """是否连接本机已安装的 Chrome（而非启动 Playwright 自带 Chromium）。

        勾选后 ``browser_open`` 走 CDP 连接模式，使用真实 Chrome
        的指纹，能绕过百度等网站对 ``navigator.webdriver`` 的反爬检测。
        """
        return bool(self.raw.get("connect_existing", False))

    @property
    def chrome_path(self) -> str:
        """本机浏览器可执行文件路径（仅 connect_existing 模式生效）。

        留空时由 :func:`chrome_cdp.find_browser_executable` 按
        :attr:`browser_kind` 自动探测。
        """
        return str(self.raw.get("chrome_path", ""))

    @property
    def browser_kind(self) -> str:
        """CDP 模式下使用的浏览器种类。

        可选值：``auto`` / ``chrome`` / ``edge`` / ``brave``。
        留空 / 未识别一律回退到 ``auto``。
        """
        return str(self.raw.get("browser_kind", "auto"))

    # --- for_each 循环字段 ---

    @property
    def as_var(self) -> str:
        """循环变量名（YAML 字段名是 ``as``，子步骤里通过该名称引用）。"""
        return str(self.raw.get("as", "item"))

    @property
    def child_steps(self) -> list[dict]:
        """循环体中的子步骤（每项是一个步骤的原始 dict）。"""
        result = self.raw.get("steps", [])
        return result if isinstance(result, list) else []


@dataclass
class Workflow:
    """一整套可串行执行的步骤集合。"""

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)

    def snapshot(self) -> "Workflow":
        """返回深拷贝快照，运行线程持有快照避免与 UI 编辑互相干扰。"""
        return Workflow(
            name=self.name,
            steps=[
                WorkflowStep(type=s.type, name=s.name, raw=copy.deepcopy(s.raw))
                for s in self.steps
            ],
        )
