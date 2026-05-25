"""流程执行引擎。

负责按顺序执行 Workflow 中的步骤，通过 step_handlers 注册中心查表分发，
不在引擎内部硬编码任何步骤分支。引擎在工作线程中运行，UI 通过回调
拿到逐步进度和消息。

Author: huaiqing.wang
"""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from rpa_helper.core.browser_controller import BrowserController
from rpa_helper.core.models import Workflow, WorkflowStep
from rpa_helper.core.placeholder import PlaceholderRenderer, PromptCallback
from rpa_helper.core.safety import SafetyManager
from rpa_helper.core.step_handlers import StepContext, get_handler
from rpa_helper.core.variable_store import VariableStore


ConfirmCallback = Callable[[str], bool]
StepCallback = Callable[[int, WorkflowStep], None]
MessageCallback = Callable[[str], None]


class WorkflowEngine:
    """串行执行流程步骤的引擎。

    构造时只依赖 project_root + safety + logger，所有桌面/图像/OCR
    协作对象都已移除。浏览器控制器在首个 browser_* 步骤触发时懒加载，
    流程结束（成功/失败/中断）后统一关闭。
    """

    def __init__(
        self,
        project_root: Path,
        safety: SafetyManager,
        logger: logging.Logger,
        dry_run: bool = False,
    ) -> None:
        self.project_root = project_root
        self.safety = safety
        self.logger = logger
        self.dry_run = dry_run
        self._browser: BrowserController | None = None

    def run(
        self,
        workflow: Workflow,
        on_step_started: StepCallback | None = None,
        on_message: MessageCallback | None = None,
        on_confirm: ConfirmCallback | None = None,
        on_prompt: PromptCallback | None = None,
    ) -> None:
        """执行整个流程。任何步骤抛出异常都会向上冒泡到调用线程。"""
        self.safety.reset()
        self._emit(on_message, f"加载流程: {workflow.name}")
        variables = VariableStore()
        placeholder = PlaceholderRenderer(prompt_callback=on_prompt, variables=variables)

        try:
            for index, step in enumerate(workflow.steps, start=1):
                self.safety.raise_if_stopped()
                if on_step_started:
                    on_step_started(index, step)
                self.logger.info("开始步骤 %s/%s: %s", index, len(workflow.steps), step.name)
                self._emit(on_message, f"开始步骤 {index}: {step.name}")

                started = time.monotonic()
                try:
                    self._execute_step(step, on_confirm, on_message, placeholder, variables)
                except InterruptedError:
                    raise
                except Exception as exc:
                    self.logger.error(
                        "步骤 %s 失败: %s\n%s", step.name, exc, traceback.format_exc()
                    )
                    raise
                elapsed = time.monotonic() - started

                self.logger.info("完成步骤 %s: %.2fs", step.name, elapsed)
                self._emit(on_message, f"完成步骤 {index}: {step.name} ({elapsed:.2f}s)")

            self._emit(on_message, "流程执行完成")
            self.logger.info("流程执行完成: %s", workflow.name)
        finally:
            # 无论成功失败都释放浏览器，避免 Chromium 进程残留。
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None

    def _execute_step(
        self,
        step: WorkflowStep,
        on_confirm: ConfirmCallback | None,
        on_message: MessageCallback | None,
        placeholder: PlaceholderRenderer,
        variables: VariableStore,
    ) -> None:
        """单步执行入口；for_each 通过 ctx.run_child_step 递归调用本函数。"""
        handler = get_handler(step.type)
        ctx = StepContext(
            project_root=self.project_root,
            safety=self.safety,
            logger=self.logger,
            dry_run=self.dry_run,
            on_confirm=on_confirm,
            on_message=on_message,
            placeholder=placeholder,
            variables=variables,
            get_browser=self._get_browser,
            run_child_step=lambda child: self._execute_step(
                child, on_confirm, on_message, placeholder, variables
            ),
        )
        handler.execute(step, ctx)

    def _emit(self, callback: MessageCallback | None, message: str) -> None:
        self.logger.info(message)
        if callback:
            callback(message)

    def _get_browser(self) -> BrowserController:
        """懒加载浏览器控制器，避免不含浏览器步骤的流程也启动 Chromium。"""
        if self._browser is None:
            self._browser = BrowserController(self.project_root, logger=self.logger)
        return self._browser
