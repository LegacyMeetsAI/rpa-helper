"""基于 Playwright 的浏览器控制器。

运行在 WorkflowEngine 的工作线程中，独占 Playwright sync_api 的生命周期。

生命周期：
  - 首个 browser_open 步骤触发懒加载，创建浏览器并打开一个 page；
  - 后续浏览器步骤复用同一 page；
  - 引擎结束（无论成功/失败/中断）时调用 close()，避免 Chromium 进程残留。

两种启动模式：
  1) 默认模式：Playwright 自带 Chromium，独立 Chrome profile；
  2) CDP 连接模式：启动本机 Chrome（用真实指纹），Playwright 通过
     CDP 接入。``connect_existing=True`` 时使用，绕过百度等网站对
     ``navigator.webdriver`` 的反爬检测。

类设计保持极简：每个 StepHandler 只调用一两个方法，方便单元测试。

Author: huaiqing.wang
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rpa_helper.core.chrome_cdp import (
    BrowserKind,
    ChromeConnection,
    ChromeUnavailableError,
    default_profile_dir_for,
    launch_user_chrome,
    parse_browser_kind,
    pick_active_page,
)


class BrowserUnavailableError(RuntimeError):
    """Playwright 没装好 / Chromium 没下载时抛出。"""


class BrowserController:
    def __init__(self, project_root: Path, logger: logging.Logger | None = None) -> None:
        self.project_root = project_root
        self.logger = logger or logging.getLogger(__name__)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        # CDP 模式相关：保存子进程句柄，但 close() 时不会去 kill 它。
        self._chrome_conn: ChromeConnection | None = None
        self._cdp_mode = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(
        self,
        url: str,
        headless: bool = False,
        user_data_dir: str = "",
        connect_existing: bool = False,
        chrome_path: str = "",
        browser_kind: str = "auto",
    ) -> None:
        """打开浏览器并跳转到 URL。

        Args:
            url: 目标 URL；为空时不发起 goto，仅启动浏览器。
            headless: 是否无界面。CDP 模式下该参数被忽略。
            user_data_dir: 持久化 profile 目录；CDP 模式留空时按浏览器
                种类生成默认目录（rpa_chrome_profile / rpa_edge_profile 等）。
            connect_existing: True = 启动本机浏览器 + CDP 连接；
                False = 走 Playwright 自带 Chromium。
            chrome_path: 仅 CDP 模式生效；留空则按 browser_kind 自动探测。
            browser_kind: 仅 CDP 模式生效；可选 auto / chrome / edge / brave。
        """
        if self._page is None:
            if connect_existing:
                kind = parse_browser_kind(browser_kind)
                self._ensure_started_cdp(
                    user_data_dir=user_data_dir,
                    chrome_path=chrome_path,
                    browser_kind=kind,
                )
            else:
                self._ensure_started_bundled(headless=headless, user_data_dir=user_data_dir)
        if url:
            self.logger.info("浏览器打开: %s", url)
            self._page.goto(url)

    def close(self) -> None:
        """关闭浏览器。CDP 模式下只断开连接，不杀 Chrome 进程。"""
        try:
            if self._cdp_mode:
                # CDP 模式：仅断开 Playwright，让 Chrome 窗口留在前台
                # 给用户继续看运行结果。
                if self._browser is not None:
                    self._browser.close()
            else:
                # 自带 Chromium 模式：context / browser 都要关。
                if self._context is not None:
                    self._context.close()
                if self._browser is not None:
                    self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._chrome_conn = None
        self._cdp_mode = False

    def is_open(self) -> bool:
        return self._page is not None

    # ------------------------------------------------------------------
    # Element interaction (raises on failure; handler converts to friendly msg)
    # ------------------------------------------------------------------

    def click(self, selector: str, timeout_ms: int = 10_000) -> None:
        self._require_page()
        self._page.click(selector, timeout=timeout_ms)

    def fill(self, selector: str, text: str, timeout_ms: int = 10_000) -> None:
        self._require_page()
        self._page.fill(selector, text, timeout=timeout_ms)

    def wait_for(self, selector: str, timeout_ms: int = 10_000) -> None:
        self._require_page()
        self._page.wait_for_selector(selector, timeout=timeout_ms)

    def extract_text(self, selector: str, timeout_ms: int = 10_000) -> str:
        self._require_page()
        return (self._page.text_content(selector, timeout=timeout_ms) or "").strip()

    def extract_attribute(self, selector: str, attribute: str, timeout_ms: int = 10_000) -> str:
        self._require_page()
        loc = self._page.locator(selector).first
        return (loc.get_attribute(attribute, timeout=timeout_ms) or "").strip()

    def count(self, selector: str) -> int:
        self._require_page()
        return self._page.locator(selector).count()

    def click_nth(self, selector: str, index: int, timeout_ms: int = 10_000) -> None:
        self._require_page()
        self._page.locator(selector).nth(index).click(timeout=timeout_ms)

    def extract_text_nth(self, selector: str, index: int, timeout_ms: int = 10_000) -> str:
        self._require_page()
        text = self._page.locator(selector).nth(index).text_content(timeout=timeout_ms)
        return (text or "").strip()

    def go_back(self) -> None:
        self._require_page()
        self._page.go_back()

    def download(
        self,
        trigger_selector: str,
        save_dir: Path,
        timeout_ms: int = 30_000,
    ) -> Path:
        """点击触发元素并把下载的文件保存到 save_dir。"""
        self._require_page()
        save_dir.mkdir(parents=True, exist_ok=True)
        with self._page.expect_download(timeout=timeout_ms) as download_info:
            self._page.click(trigger_selector, timeout=timeout_ms)
        download = download_info.value
        target = save_dir / download.suggested_filename
        # 文件名冲突时追加时间戳，避免覆盖既有文件。
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            import time
            target = save_dir / f"{stem}_{int(time.time())}{suffix}"
        download.save_as(target)
        return target

    # ------------------------------------------------------------------
    # Internal: bundled Chromium
    # ------------------------------------------------------------------

    def _ensure_started_bundled(self, headless: bool, user_data_dir: str) -> None:
        """启动 Playwright 自带的 Chromium。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailableError(
                "Playwright 未安装，请安装 playwright 并执行 `python -m playwright install chromium`"
            ) from exc

        self._pw = sync_playwright().start()
        try:
            if user_data_dir:
                data_dir = self._resolve_profile_dir(user_data_dir)
                data_dir.mkdir(parents=True, exist_ok=True)
                self._context = self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(data_dir),
                    headless=headless,
                    accept_downloads=True,
                )
                self._browser = None
                self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            else:
                self._browser = self._pw.chromium.launch(headless=headless)
                self._context = self._browser.new_context(accept_downloads=True)
                self._page = self._context.new_page()
        except Exception as exc:
            # 启动失败先把 partial 状态清掉，再翻译成对用户友好的错误。
            self.close()
            msg = str(exc)
            if "Executable doesn" in msg or "Looks like Playwright" in msg:
                raise BrowserUnavailableError(
                    "Chromium 未下载，请执行 `python -m playwright install chromium`"
                ) from exc
            raise

    # ------------------------------------------------------------------
    # Internal: CDP-attached real Chrome
    # ------------------------------------------------------------------

    def _ensure_started_cdp(
        self,
        user_data_dir: str,
        chrome_path: str,
        browser_kind: BrowserKind,
    ) -> None:
        """启动本机浏览器并用 CDP 接入。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailableError(
                "Playwright 未安装，请先 pip install playwright"
            ) from exc

        # CDP 模式必须有独立的 user_data_dir，否则会与日常浏览器抢锁。
        # 留空时按浏览器种类给个默认目录，让不同浏览器互不污染 profile。
        profile_raw = user_data_dir or default_profile_dir_for(browser_kind)
        profile_path = self._resolve_profile_dir(profile_raw)

        try:
            self._chrome_conn = launch_user_chrome(
                user_data_dir=profile_path,
                chrome_path=chrome_path,
                browser_kind=browser_kind,
                logger=self.logger,
            )
        except ChromeUnavailableError as exc:
            raise BrowserUnavailableError(str(exc)) from exc

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self._chrome_conn.cdp_url)
            # connect_over_cdp 把已有的所有 BrowserContext 暴露出来；
            # 新启动的浏览器通常只有一个默认 context，直接取第一个。
            contexts = self._browser.contexts
            self._context = contexts[0] if contexts else self._browser.new_context()
            self._page = pick_active_page(self._context)
            self._cdp_mode = True
        except Exception as exc:
            self.close()
            raise BrowserUnavailableError(f"连接本机浏览器失败: {exc}") from exc

    def _resolve_profile_dir(self, raw: str) -> Path:
        """把流程里写的 user_data_dir 解析成绝对路径。

        相对路径相对项目根目录；绝对路径原样使用。
        """
        path = Path(raw)
        if not path.is_absolute():
            path = self.project_root / raw
        return path

    def _require_page(self) -> None:
        if self._page is None:
            raise RuntimeError("浏览器尚未打开，请先添加 browser_open 步骤")
