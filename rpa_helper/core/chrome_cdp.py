"""启动本机 Chromium 内核浏览器并通过 CDP（Chrome DevTools Protocol）连接。

设计目的：
  让用户用「自己平时使用的浏览器」做录制和执行，避免 Playwright
  自带 Chromium 被网站（典型如百度）检测为自动化浏览器导致触发反爬
  滑块。真实浏览器自身没有 ``navigator.webdriver === true`` 的特征，
  指纹更像普通用户，反爬通过率显著提升。

支持的浏览器（全是 Chromium 内核，CDP 协议完全兼容）：
  - Microsoft Edge（Win10/11 预装，作为「自动检测」的首选）
  - Google Chrome
  - Brave Browser

工作流程：
  1. 按 BrowserKind 在常见安装路径里探测可执行文件；
  2. 给一个空闲端口、独立 ``user-data-dir``，以子进程方式启动浏览器；
  3. 轮询 ``http://127.0.0.1:<port>/json/version`` 直到返回 200；
  4. 返回 ChromeConnection 供 Playwright ``chromium.connect_over_cdp(...)`` 使用。

关于「不关闭窗口」：
  本模块只负责启动浏览器，不负责关闭它——这是有意为之。Popen 对象
  通过 :func:`launch_user_chrome` 返回给调用方，由调用方决定是否
  保留窗口。`BrowserController.close` 在 CDP 模式下只 ``browser.close()``
  断开 Playwright 连接，浏览器进程留在前台供用户继续查看结果。

Author: huaiqing.wang
"""

from __future__ import annotations

import contextlib
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ChromeUnavailableError(RuntimeError):
    """找不到目标浏览器 / 启动失败 / CDP 端口不通时抛出。"""


class BrowserKind(str, Enum):
    """支持的本机浏览器种类。

    AUTO 表示按 :data:`AUTO_DETECT_ORDER` 的顺序自动探测，命中即用；
    其它枚举值固定使用对应的浏览器，找不到就报错（不做隐式降级，
    免得用户搞不清当前实际用了哪个浏览器）。
    """

    AUTO = "auto"
    EDGE = "edge"
    CHROME = "chrome"
    BRAVE = "brave"


# 自动检测的顺序：
#   1) Edge —— Win10/11 预装，覆盖率最高；
#   2) Chrome —— 次主流，重度用户和开发者常用；
#   3) Brave —— 通常是用户主动安装的，意图明确。
AUTO_DETECT_ORDER: tuple[BrowserKind, ...] = (
    BrowserKind.EDGE,
    BrowserKind.CHROME,
    BrowserKind.BRAVE,
)


# 每种浏览器的标准安装路径（Windows），按优先级从高到低排列。
# 同时会再去查 ``LOCALAPPDATA`` 下的对应目录。
_BROWSER_PATHS: dict[BrowserKind, tuple[str, ...]] = {
    BrowserKind.EDGE: (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ),
    BrowserKind.CHROME: (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ),
    BrowserKind.BRAVE: (
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    ),
}


# 每种浏览器在 LOCALAPPDATA 下的子路径（用户级安装常见位置）。
_LOCALAPP_SUBPATHS: dict[BrowserKind, str] = {
    BrowserKind.EDGE: r"Microsoft\Edge\Application\msedge.exe",
    BrowserKind.CHROME: r"Google\Chrome\Application\chrome.exe",
    BrowserKind.BRAVE: r"BraveSoftware\Brave-Browser\Application\brave.exe",
}


# 各浏览器的默认 profile 目录名（项目根目录下创建），分开放避免互相污染。
_DEFAULT_PROFILE_DIR: dict[BrowserKind, str] = {
    BrowserKind.EDGE: "rpa_edge_profile",
    BrowserKind.CHROME: "rpa_chrome_profile",
    BrowserKind.BRAVE: "rpa_brave_profile",
}


@dataclass
class ChromeConnection:
    """一次成功启动后返回的握手信息。"""

    cdp_url: str                  # 形如 http://127.0.0.1:9223
    user_data_dir: Path           # 实际使用的 profile 目录
    browser_path: Path            # 实际启动的浏览器可执行文件
    browser_kind: BrowserKind     # 当前使用的浏览器种类（解析后的具体值）
    process: subprocess.Popen     # 子进程句柄；调用方负责保管，不必 wait()


def parse_browser_kind(value: str) -> BrowserKind:
    """把流程文件 / UI 里传来的字符串解析为枚举。

    解析失败回退到 :attr:`BrowserKind.AUTO`，避免老流程文件因为
    字段缺失/拼写错误直接报错。
    """
    if not value:
        return BrowserKind.AUTO
    normalized = str(value).strip().lower()
    for kind in BrowserKind:
        if kind.value == normalized:
            return kind
    return BrowserKind.AUTO


def default_profile_dir_for(kind: BrowserKind) -> str:
    """返回某浏览器的默认 profile 目录名（相对路径）。"""
    return _DEFAULT_PROFILE_DIR.get(kind, "rpa_chrome_profile")


def _candidates_for(kind: BrowserKind) -> list[Path]:
    """汇总某浏览器所有可能的可执行文件路径。"""
    paths: list[Path] = []
    for raw in _BROWSER_PATHS.get(kind, ()):
        paths.append(Path(raw))
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app and kind in _LOCALAPP_SUBPATHS:
        paths.append(Path(local_app) / _LOCALAPP_SUBPATHS[kind])
    return paths


def find_browser_executable(
    kind: BrowserKind = BrowserKind.AUTO,
    explicit_path: str = "",
) -> tuple[Path, BrowserKind]:
    """定位浏览器可执行文件。

    返回 ``(可执行路径, 实际使用的浏览器种类)``。AUTO 模式下，第二
    个返回值告诉调用方最终用的是哪种浏览器（用于选 profile 目录
    与日志）。

    优先顺序：
      1. 用户显式传入的路径；
      2. ``CHROME_EXECUTABLE`` 环境变量；
      3. 按 kind 的标准安装路径；
      4. AUTO 模式下，按 :data:`AUTO_DETECT_ORDER` 顺次探测。
    """
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file():
            # 显式路径无法可靠分辨是哪种浏览器，按 kind 给个标签；
            # AUTO 时回退到 CHROME（profile 目录命名也用 chrome）。
            label = kind if kind != BrowserKind.AUTO else BrowserKind.CHROME
            return p, label
        raise ChromeUnavailableError(f"指定的浏览器路径不存在：{explicit_path}")

    env_path = os.environ.get("CHROME_EXECUTABLE", "").strip()
    if env_path and Path(env_path).is_file():
        label = kind if kind != BrowserKind.AUTO else BrowserKind.CHROME
        return Path(env_path), label

    if kind == BrowserKind.AUTO:
        for candidate_kind in AUTO_DETECT_ORDER:
            for path in _candidates_for(candidate_kind):
                if path.is_file():
                    return path, candidate_kind
        raise ChromeUnavailableError(
            "未在常见路径找到 Chrome / Edge / Brave。请安装其中一款，"
            "或在「打开浏览器」步骤里手动填写 chrome_path。"
        )

    for path in _candidates_for(kind):
        if path.is_file():
            return path, kind
    raise ChromeUnavailableError(
        f"未找到 {kind.value} 浏览器。请确认安装到默认目录，"
        f"或在步骤里填写 chrome_path 指向可执行文件。"
    )


def _find_free_port() -> int:
    """让操作系统挑一个空闲端口，避免和别的进程撞车。"""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_cdp_ready(cdp_url: str, timeout: float = 20.0) -> None:
    """等待 ``/json/version`` 返回 200，确认浏览器已经监听端口。"""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    probe = cdp_url.rstrip("/") + "/json/version"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe, timeout=1.0) as resp:
                if 200 <= resp.status < 300:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = exc
        time.sleep(0.2)
    raise ChromeUnavailableError(
        f"浏览器调试端口 {cdp_url} 未就绪（超时 {timeout}s）。"
        f"最后一次错误：{last_err}"
    )


def launch_user_chrome(
    user_data_dir: Path,
    chrome_path: str = "",
    browser_kind: BrowserKind = BrowserKind.AUTO,
    extra_args: list[str] | None = None,
    logger: logging.Logger | None = None,
    timeout: float = 20.0,
) -> ChromeConnection:
    """启动本机 Chromium 内核浏览器并打开 CDP 调试端口。

    Args:
        user_data_dir: profile 目录；不存在会自动创建。建议每种浏览器
            用不同目录（默认见 :func:`default_profile_dir_for`），避免
            和日常使用的浏览器抢锁。
        chrome_path: 可执行文件路径；留空则按 ``browser_kind`` 自动探测。
        browser_kind: 浏览器种类；默认 AUTO（按预设顺序探测）。
        extra_args: 额外的命令行参数（一般用不上）。
        logger: 可选日志器。
        timeout: 等端口就绪的超时秒数。
    """
    log = logger or logging.getLogger(__name__)
    exe, resolved_kind = find_browser_executable(browser_kind, chrome_path)
    user_data_dir.mkdir(parents=True, exist_ok=True)

    port = _find_free_port()
    args: list[str] = [
        str(exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        # 阻止首次启动时跳出来的「默认浏览器/欢迎」对话框。
        "--no-first-run",
        "--no-default-browser-check",
        # 关掉某些会拖累自动化的弹窗（翻译条、密码保存条等）。
        "--disable-features=Translate,InfobarOcrOnSelection",
    ]
    if extra_args:
        args.extend(extra_args)

    log.info(
        "启动本机浏览器: kind=%s, exe=%s, port=%d, profile=%s",
        resolved_kind.value, exe, port, user_data_dir,
    )
    try:
        # Windows 上 CREATE_NEW_PROCESS_GROUP 让浏览器不跟随主进程的
        # Ctrl-C；同时 close_fds 避免句柄泄漏。
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except OSError as exc:
        raise ChromeUnavailableError(f"启动浏览器失败: {exc}") from exc

    cdp_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_cdp_ready(cdp_url, timeout=timeout)
    except ChromeUnavailableError:
        # 端口没就绪时主动终止刚启动的浏览器，避免遗留进程。
        with contextlib.suppress(Exception):
            process.terminate()
        raise
    return ChromeConnection(
        cdp_url=cdp_url,
        user_data_dir=user_data_dir,
        browser_path=exe,
        browser_kind=resolved_kind,
        process=process,
    )


def pick_active_page(context):
    """返回 BrowserContext 里「最后一个 page」作为当前活动 tab。

    Playwright 的 ``connect_over_cdp`` 拿到的 ``BrowserContext.pages``
    按打开顺序排列，没有「激活态」字段。绝大多数场景下用户最后打
    开的 tab 就是要操作的那一个，本函数采取该启发式。

    若 context 里完全没有 page，则新建一个空白 page，避免调用方
    再做 None 判断。
    """
    pages = list(context.pages)
    if pages:
        return pages[-1]
    return context.new_page()


# 兼容旧调用方：保留 find_chrome_executable 名字，转发到新函数。
def find_chrome_executable(explicit_path: str = "") -> Path:
    """[兼容旧接口] 仅返回路径不返回种类。新代码请用 find_browser_executable。"""
    exe, _kind = find_browser_executable(BrowserKind.AUTO, explicit_path)
    return exe
