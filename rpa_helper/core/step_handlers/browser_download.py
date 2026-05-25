"""browser_download：点击触发元素并保存随之产生的下载文件。

save_dir 支持占位符，可写成 ``downloads/{{today}}/{{order_id}}/`` 形式
按业务字段自动分桶；相对路径会落到项目根目录下。

Author: huaiqing.wang
"""

from __future__ import annotations

from pathlib import Path

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


def _sanitize_dir_component(component: str) -> str:
    """把字符串里 Windows 非法的字符替换成下划线，空串回退为 unnamed。"""
    invalid = set('<>:"/\\|?*')
    cleaned = "".join("_" if c in invalid else c for c in component).strip()
    return cleaned or "unnamed"


class BrowserDownloadHandler:
    """监听 Playwright download 事件，把文件保存到 save_dir。"""

    step_type = StepType.BROWSER_DOWNLOAD

    def required_fields(self) -> tuple[str, ...]:
        return ("trigger_selector",)

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 下载文件 ← {raw.get('trigger_selector')}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        trigger = ctx.render(step.trigger_selector)
        timeout_ms = int(step.timeout * 1000) if step.timeout > 0 else 30_000

        # 渲染占位符，让 save_dir 支持 "downloads/{{order_id}}/" 这种写法。
        save_dir_str = ctx.render(step.save_dir or "downloads")
        save_dir = Path(save_dir_str)
        if not save_dir.is_absolute():
            # 相对路径要按段清洗——变量值里可能含非法字符；用户
            # 主动给的绝对路径直接信任，不做改动。
            sanitized_parts = [_sanitize_dir_component(p) for p in save_dir.parts]
            save_dir = ctx.project_root / Path(*sanitized_parts)

        if ctx.dry_run:
            ctx.logger.info("模拟下载: trigger=%s save_dir=%s", trigger, save_dir)
            ctx.wait_interruptibly(0.2)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_download 需要 BrowserController")
        saved = ctx.get_browser().download(trigger, save_dir=save_dir, timeout_ms=timeout_ms)
        ctx.logger.info("已下载: %s", saved)
        if step.save_as:
            ctx.variables.set(step.save_as, str(saved))


register_handler(BrowserDownloadHandler())
