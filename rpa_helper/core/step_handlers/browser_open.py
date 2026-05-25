"""browser_open：启动浏览器，并可选地跳转到指定 URL。

两种启动模式：
  1) 默认（Playwright 自带 Chromium）——开箱即用，但 ``navigator.webdriver``
     为 True，会被百度等网站识别为自动化浏览器，触发反爬滑块；
  2) ``connect_existing=True`` ——启动本机 Chrome 并通过 CDP 连接。
     用真实 Chrome 的指纹，能绕过绝大多数反爬检测。建议配合
     ``user_data_dir`` 持久化登录态。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserOpenHandler:
    """打开浏览器；url 留空时仅创建空白窗口，留给后续步骤导航。"""

    step_type = StepType.BROWSER_OPEN

    def required_fields(self) -> tuple[str, ...]:
        # url 不是必填——允许先 open 再用其它方式跳转。
        return ()

    def default_name(self, raw: dict, index: int) -> str:
        url = raw.get("url") or "空白页"
        return f"{index}. 打开浏览器 {url}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        url = ctx.render(step.url)
        if ctx.dry_run:
            ctx.logger.info("模拟打开浏览器: %s", url or "空白页")
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_open 需要 BrowserController")
        browser = ctx.get_browser()
        browser.open(
            url=url,
            headless=step.headless,
            user_data_dir=step.user_data_dir,
            connect_existing=step.connect_existing,
            chrome_path=step.chrome_path,
            browser_kind=step.browser_kind,
        )


register_handler(BrowserOpenHandler())
