"""浏览器录制器后端。

启动一个 Chromium 窗口，注入录制脚本，通过 window.__rpaRecord 收集
用户的点击/输入/导航事件，最终转换为可执行的 WorkflowStep 列表。

生命周期：
  - start(url) 启动 Chromium、安装脚本、打开 URL；
  - 浏览器保持在前台，让用户继续操作；
  - stop() 返回有序的步骤列表并关闭浏览器；
  - 调用方可在任意线程调用 stop()，工作线程通过标志位识别后干净退出。

并发：
  Playwright sync_api 不支持 asyncio，因此把它跑在专属工作线程里。
  事件收集走 JS binding 回调，由 Playwright 线程触发；UI 线程的指令
  （试运行选中步骤、高亮某选择器等）放入线程安全队列，工作线程在
  pump 循环里依次取出执行。

Author: huaiqing.wang
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from pathlib import Path

from rpa_helper.core.browser_recorder_script import RECORDER_SCRIPT
from rpa_helper.core.chrome_cdp import (
    BrowserKind,
    ChromeConnection,
    ChromeUnavailableError,
    default_profile_dir_for,
    launch_user_chrome,
    parse_browser_kind,
    pick_active_page,
)
from rpa_helper.core.models import StepType, WorkflowStep


@dataclass
class RecordedAction:
    kind: str               # click | input | submit | navigate
    candidates: list[str]   # selector candidates, best-first
    name: str               # accessible name (visible text)
    tag: str                # tag name (lowercase)
    value: str              # input value or url for navigate
    url: str                # page url at time of event
    ts: float               # JS timestamp (ms)


@dataclass
class CommandResult:
    """Result of a worker-thread command. Sent back to the caller's queue."""
    ok: bool
    message: str = ""
    detail: Any = None


class BrowserRecorder:
    """Driven by the UI thread. start() spawns a worker thread that owns
    the Playwright browser; stop() joins it.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._actions: list[RecordedAction] = []
        self._actions_lock = threading.Lock()
        self._started_event = threading.Event()
        self._start_error: BaseException | None = None
        # Optional callback invoked from the worker thread on every event.
        # Receives the RecordedAction. UI must marshal to its own thread.
        self.on_action: Callable[[RecordedAction], None] | None = None
        # Command queue: (cmd_id, kind, payload). Worker drains it in pump.
        self._commands: queue.Queue[tuple[str, str, dict]] = queue.Queue()
        # cmd_id -> Queue used to deliver the single result back.
        self._pending: dict[str, queue.Queue[CommandResult]] = {}
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        url: str = "",
        timeout: float = 10.0,
        connect_existing: bool = False,
        chrome_path: str = "",
        user_data_dir: str = "",
        browser_kind: str = "auto",
        project_root: Path | None = None,
    ) -> None:
        """启动录制浏览器。返回时页面已加载完毕。

        Args:
            url: 起始 URL；为空则停留在 about:blank。
            timeout: 启动+加载的最长等待时间（秒）。
            connect_existing: True = 连接本机浏览器（CDP）；False =
                启动 Playwright 自带 Chromium。
            chrome_path: 仅 CDP 模式生效；留空则按 browser_kind 探测。
            user_data_dir: 仅 CDP 模式生效；留空时按浏览器种类用默认
                目录（rpa_chrome_profile / rpa_edge_profile 等）。
            browser_kind: 仅 CDP 模式生效；auto / chrome / edge / brave。
            project_root: 用于解析相对 user_data_dir，默认为当前目录。
        """
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("录制器已在运行")
        self._stop_event.clear()
        self._started_event.clear()
        self._actions = []
        self._start_error = None
        clean_url = normalize_url(url)
        self._thread = threading.Thread(
            target=self._worker,
            args=(clean_url, connect_existing, chrome_path, user_data_dir,
                  browser_kind, project_root or Path.cwd()),
            daemon=True,
            name="BrowserRecorder",
        )
        self._thread.start()
        self._started_event.wait(timeout=timeout)
        if self._start_error is not None:
            err = self._start_error
            self._start_error = None
            raise err

    def stop(self, timeout: float = 5.0) -> list[WorkflowStep]:
        """Signal the worker to close and return the converted steps."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        actions = self.take_actions()
        return self.actions_to_steps(actions)

    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def take_actions(self) -> list[RecordedAction]:
        """Snapshot and clear the buffered actions."""
        with self._actions_lock:
            actions = list(self._actions)
            self._actions = []
        return actions

    # ------------------------------------------------------------------
    # Cross-thread commands (highlight / test step)
    # ------------------------------------------------------------------

    def highlight_selector(self, selector: str, timeout: float = 2.0) -> CommandResult:
        """Ask the recorder browser to flash-outline `selector`. Blocking."""
        return self._submit_command("highlight", {"selector": selector}, timeout=timeout)

    def test_step(self, step: WorkflowStep, timeout: float = 15.0) -> CommandResult:
        """Run a single browser step against the current recorder page.

        Returns CommandResult with ok=True on success. For extract steps,
        result.detail is the extracted text.
        """
        return self._submit_command(
            "test_step",
            {"step": _step_to_command(step)},
            timeout=timeout,
        )

    def _submit_command(self, kind: str, payload: dict, timeout: float) -> CommandResult:
        if not self.is_recording():
            return CommandResult(ok=False, message="录制浏览器未运行")
        cmd_id = uuid.uuid4().hex
        reply: queue.Queue[CommandResult] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[cmd_id] = reply
        self._commands.put((cmd_id, kind, payload))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return CommandResult(ok=False, message=f"命令超时（{timeout}s）")
        finally:
            with self._pending_lock:
                self._pending.pop(cmd_id, None)

    # ------------------------------------------------------------------
    # Action → step conversion (pure)
    # ------------------------------------------------------------------

    @staticmethod
    def actions_to_steps(actions: list[RecordedAction]) -> list[WorkflowStep]:
        """Convert a flat action list into a workflow step list.

        Rules:
          - 'navigate' becomes browser_open (or browser_wait_for if same domain).
          - Consecutive 'input' events on the same selector collapse to one
            browser_input (use the final value).
          - 'click' becomes browser_click.
          - 'submit' is ignored if preceded by a click on the form's submit
            button (avoid duplicates); otherwise emitted as a browser_click
            on the form's submit if discoverable, else dropped.
          - If no usable navigate was seen but the user did interact, we
            synthesize a browser_open from the first action's page url so
            the resulting workflow can stand on its own.
        """
        steps: list[WorkflowStep] = []
        last_input_by_selector: dict[str, int] = {}  # selector -> index in steps

        for idx, action in enumerate(actions):
            selector = _pick_selector(action)

            if action.kind == "navigate":
                # First navigation = browser_open, subsequent ones are typically
                # SPA route changes triggered by clicks above, so skip them
                # unless steps is empty.
                if not steps and _is_real_url(action.value):
                    steps.append(_make_browser_open(action.value))
                continue

            if action.kind == "click":
                if not selector:
                    continue
                # Synthesize a browser_open from the page url if we haven't
                # seen one yet (user typed the URL into the address bar so
                # there's no recorded navigate event).
                if not steps and _is_real_url(action.url):
                    steps.append(_make_browser_open(action.url))
                name = action.name or selector
                steps.append(WorkflowStep(
                    type=StepType.BROWSER_CLICK,
                    name=f"点击 {name[:30]}",
                    raw={
                        "type": "browser_click",
                        "name": f"点击 {name[:30]}",
                        "selector": selector,
                        "timeout": 10,
                    },
                ))
                last_input_by_selector.clear()  # navigation-like reset
                continue

            if action.kind == "input":
                if not selector:
                    continue
                # Synthesize a browser_open before the first interaction so
                # the produced workflow opens the right page when re-run.
                if not steps and _is_real_url(action.url):
                    steps.append(_make_browser_open(action.url))
                # Collapse repeated input on the same selector to one step.
                if selector in last_input_by_selector:
                    step_index = last_input_by_selector[selector]
                    steps[step_index].raw["text"] = action.value
                    continue
                step = WorkflowStep(
                    type=StepType.BROWSER_INPUT,
                    name=f"输入 {selector[:30]}",
                    raw={
                        "type": "browser_input",
                        "name": f"输入 {selector[:30]}",
                        "selector": selector,
                        "text": action.value,
                        "timeout": 10,
                    },
                )
                last_input_by_selector[selector] = len(steps)
                steps.append(step)
                continue

            # submit: skip — usually duplicated by a click already.

        return steps

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker(
        self,
        url: str,
        connect_existing: bool,
        chrome_path: str,
        user_data_dir: str,
        browser_kind: str,
        project_root: Path,
    ) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._start_error = RuntimeError(
                "Playwright 未安装，请安装 playwright 并执行 `python -m playwright install chromium`"
            )
            self._started_event.set()
            return

        pw = None
        browser = None
        context = None
        chrome_conn: ChromeConnection | None = None
        # CDP 模式下不关闭已有浏览器窗口；通过该旗标在 finally 里区分。
        cdp_mode = bool(connect_existing)
        try:
            # ---------- 启动浏览器（两种模式） ----------
            if cdp_mode:
                kind = parse_browser_kind(browser_kind)
                profile_raw = user_data_dir or default_profile_dir_for(kind)
                profile_path = self._resolve_profile_dir(profile_raw, project_root)
                try:
                    chrome_conn = launch_user_chrome(
                        user_data_dir=profile_path,
                        chrome_path=chrome_path,
                        browser_kind=kind,
                        logger=self.logger,
                    )
                except ChromeUnavailableError as exc:
                    self._start_error = RuntimeError(str(exc))
                    self._started_event.set()
                    return

                pw = sync_playwright().start()
                try:
                    browser = pw.chromium.connect_over_cdp(chrome_conn.cdp_url)
                except Exception as exc:
                    self._start_error = RuntimeError(
                        f"连接本机浏览器失败: {exc}"
                    )
                    self._started_event.set()
                    return

                contexts = browser.contexts
                context = contexts[0] if contexts else browser.new_context()
            else:
                pw = sync_playwright().start()
                try:
                    browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
                except Exception as exc:
                    self._start_error = RuntimeError(
                        f"无法启动 Chromium，请确认已运行 `python -m playwright install chromium`: {exc}"
                    )
                    self._started_event.set()
                    return
                context = browser.new_context(no_viewport=True)

            # ---------- 注入录制脚本 ----------
            # add_init_script 让脚本随每个新 page 自动注入；同时给
            # 已存在的 page 手工执行一次，以兼容 CDP 模式下的已有 tab。
            context.add_init_script(RECORDER_SCRIPT)

            def on_event(payload_json: str) -> None:
                try:
                    data = json.loads(payload_json)
                except Exception:
                    return
                action = RecordedAction(
                    kind=str(data.get("kind", "")),
                    candidates=[str(c) for c in (data.get("candidates") or [])],
                    name=str(data.get("name", "")),
                    tag=str(data.get("tag", "")),
                    value=str(data.get("value", "")),
                    url=str(data.get("url", "")),
                    ts=float(data.get("ts", 0)),
                )
                with self._actions_lock:
                    self._actions.append(action)
                self.logger.debug("录制事件: %s", action)
                if self.on_action is not None:
                    try:
                        self.on_action(action)
                    except Exception:
                        pass

            try:
                context.expose_function("__rpaRecord", on_event)
            except Exception as exc:
                # CDP 模式下若同名 binding 已存在，忽略即可。
                self.logger.debug("expose_function 已存在: %s", exc)

            # CDP 模式：取当前活动 tab；其它模式：新建 page。
            if cdp_mode:
                page = pick_active_page(context)
                # 对已有 page 手动注入一次，否则脚本只对刷新后的页生效。
                try:
                    page.evaluate(RECORDER_SCRIPT)
                except Exception as exc:
                    self.logger.debug("手动注入录制脚本失败（可能页面跨域受限）: %s", exc)
            else:
                page = context.new_page()

            if url:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                except Exception as exc:
                    self.logger.warning("跳转 URL 失败: %s", exc)

            self._started_event.set()

            # 主循环：消费 UI 队列里的命令，直到 stop 或浏览器关闭。
            while not self._stop_event.is_set():
                # 用户手动关掉窗口（自带 Chromium）会让 pages 变空；
                # CDP 模式下用户可能关了被录制的 tab，但 Chrome 进程
                # 仍在，pages 不会变空，只是当前 page 不可用。
                if not cdp_mode and context.pages == []:
                    break
                self._drain_commands(context)
                pw.selectors  # noqa: B018 — 保持 sync API 活跃
                time.sleep(0.05)

        except Exception as exc:
            self.logger.error("录制器异常: %s", exc, exc_info=True)
            if not self._started_event.is_set():
                self._start_error = exc
                self._started_event.set()
        finally:
            # CDP 模式：只断开 Playwright，不关 Chrome 窗口、不杀进程。
            if cdp_mode:
                try:
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
            else:
                try:
                    if context is not None:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
            try:
                if pw is not None:
                    pw.stop()
            except Exception:
                pass
            self._fail_pending_commands("录制浏览器已停止")

    @staticmethod
    def _resolve_profile_dir(raw: str, project_root: Path) -> Path:
        """把传入的 user_data_dir 字符串解析成绝对路径。"""
        path = Path(raw)
        if not path.is_absolute():
            path = project_root / path
        return path

    def _drain_commands(self, context) -> None:
        """工作线程消费 UI 端排入的命令（高亮 / 试运行）。"""
        try:
            # 用 pick_active_page 让 CDP 模式拿到最后一个 tab；非 CDP
            # 模式下 pages[-1] 与 pages[0] 等价（只有一个 page）。
            page = pick_active_page(context) if context.pages else None
        except Exception:
            page = None
        while True:
            try:
                cmd_id, kind, payload = self._commands.get_nowait()
            except queue.Empty:
                return
            if page is None:
                result = CommandResult(ok=False, message="没有可用页面")
            else:
                try:
                    result = _execute_command_on_page(page, kind, payload)
                except Exception as exc:
                    result = CommandResult(ok=False, message=f"命令异常: {exc}")
            with self._pending_lock:
                reply = self._pending.get(cmd_id)
            if reply is not None:
                try:
                    reply.put_nowait(result)
                except queue.Full:
                    pass

    def _fail_pending_commands(self, message: str) -> None:
        with self._pending_lock:
            replies = list(self._pending.values())
        for reply in replies:
            try:
                reply.put_nowait(CommandResult(ok=False, message=message))
            except queue.Full:
                pass


def _pick_selector(action: RecordedAction) -> str:
    """Pick the best stable selector from candidates.

    Drop CSS-path candidates that look brittle (long, lots of nth-of-type).
    """
    if not action.candidates:
        return ""
    for c in action.candidates:
        # Prefer the first non-path candidate (data-testid, aria-label, id,
        # role=, text=). CSS paths contain " > " or ":nth-of-type".
        if " > " not in c and ":nth-of-type" not in c:
            return c
    return action.candidates[-1]


# ----------------------------------------------------------------------
# URL helpers
# ----------------------------------------------------------------------

_BROWSER_INTERNAL_URLS = ("about:", "chrome://", "edge://", "data:", "view-source:")


def _is_real_url(url: str) -> bool:
    """True when the url is a real http(s) page we can re-open later."""
    if not url:
        return False
    u = url.strip().lower()
    if u in ("", "about:blank", "about:newtab"):
        return False
    for prefix in _BROWSER_INTERNAL_URLS:
        if u.startswith(prefix):
            return False
    return u.startswith("http://") or u.startswith("https://")


def normalize_url(url: str) -> str:
    """Best-effort canonicalize: add https:// when no scheme is present.

    Users commonly type 'www.baidu.com' into the start-URL box; Playwright
    requires a scheme or it raises. Empty input stays empty (caller skips
    the goto).
    """
    if not url:
        return ""
    u = url.strip()
    if not u:
        return ""
    if "://" in u:
        return u
    return "https://" + u


def _make_browser_open(url: str) -> WorkflowStep:
    return WorkflowStep(
        type=StepType.BROWSER_OPEN,
        name=f"打开 {url}",
        raw={
            "type": "browser_open",
            "name": f"打开 {url}",
            "url": url,
        },
    )


# ----------------------------------------------------------------------
# Cross-thread command helpers
# ----------------------------------------------------------------------


def _step_to_command(step: WorkflowStep) -> dict:
    """Serialize a WorkflowStep into a plain dict the worker can act on.

    We avoid passing WorkflowStep across threads as a precaution; the worker
    only needs the fields it consumes.
    """
    return {
        "type": step.type.value,
        "selector": step.raw.get("selector", "") or "",
        "text": step.raw.get("text", "") or "",
        "url": step.raw.get("url", "") or "",
        "attribute": step.raw.get("attribute", "") or "",
        "timeout": int(step.raw.get("timeout", 10) or 10),
    }


def _execute_command_on_page(page, kind: str, payload: dict) -> CommandResult:
    """Run a command on the Playwright page. Must be called from the
    worker thread that owns the sync_api objects.
    """
    if kind == "highlight":
        selector = (payload.get("selector") or "").strip()
        if not selector:
            return CommandResult(ok=False, message="选择器为空")
        try:
            # If the selector starts with role=/text=, querySelector won't
            # understand it — fall back to Playwright's own locator.
            if selector.startswith(("role=", "text=")):
                count = page.locator(selector).count()
                if count == 0:
                    return CommandResult(ok=False, message="选择器没匹配到元素", detail={"count": 0})
                # Use page.evaluate to flash via JS — but for Playwright
                # selectors we can scroll into view and use the locator's
                # bounding box manually.
                try:
                    page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                # Trigger a flash by calling __rpaHighlightSelector with a
                # CSS substitute — we don't have one, so just report count.
                return CommandResult(ok=True, message=f"匹配 {count} 个元素", detail={"count": count})
            result = page.evaluate(
                "(s) => window.__rpaHighlightSelector && window.__rpaHighlightSelector(s)",
                selector,
            ) or {}
            if not result.get("ok"):
                reason = result.get("reason", "")
                if reason == "invalid_selector":
                    return CommandResult(ok=False, message=f"选择器语法错误: {result.get('error', '')}")
                return CommandResult(ok=False, message="选择器没匹配到元素", detail={"count": 0})
            count = int(result.get("count") or 1)
            return CommandResult(ok=True, message=f"匹配 {count} 个元素", detail={"count": count})
        except Exception as exc:
            return CommandResult(ok=False, message=f"高亮失败: {exc}")

    if kind == "test_step":
        step = payload.get("step") or {}
        return _run_test_step(page, step)

    return CommandResult(ok=False, message=f"未知命令: {kind}")


def _run_test_step(page, step: dict) -> CommandResult:
    """Execute a single browser step against the recorder page."""
    step_type = step.get("type", "")
    selector = step.get("selector", "")
    timeout_ms = int(step.get("timeout", 10) or 10) * 1000

    try:
        if step_type == "browser_open":
            url = step.get("url", "")
            if not url:
                return CommandResult(ok=False, message="缺少 url")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return CommandResult(ok=True, message=f"已打开 {url}")

        if step_type == "browser_click":
            if not selector:
                return CommandResult(ok=False, message="缺少选择器")
            page.click(selector, timeout=timeout_ms)
            return CommandResult(ok=True, message="点击成功")

        if step_type == "browser_input":
            if not selector:
                return CommandResult(ok=False, message="缺少选择器")
            page.fill(selector, step.get("text", ""), timeout=timeout_ms)
            return CommandResult(ok=True, message="输入成功")

        if step_type == "browser_wait_for":
            if not selector:
                return CommandResult(ok=False, message="缺少选择器")
            page.wait_for_selector(selector, timeout=timeout_ms)
            return CommandResult(ok=True, message="元素已出现")

        if step_type == "browser_extract":
            if not selector:
                return CommandResult(ok=False, message="缺少选择器")
            attr = step.get("attribute", "")
            if attr:
                value = page.locator(selector).first.get_attribute(attr, timeout=timeout_ms)
            else:
                value = page.text_content(selector, timeout=timeout_ms)
            value = (value or "").strip()
            return CommandResult(ok=True, message=f"提取到: {value[:60]}", detail=value)

        if step_type == "browser_go_back":
            page.go_back()
            return CommandResult(ok=True, message="已后退")

        return CommandResult(ok=False, message=f"试运行不支持的步骤类型: {step_type}")

    except Exception as exc:
        # Trim noisy Playwright stack but keep the gist.
        msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return CommandResult(ok=False, message=msg)
