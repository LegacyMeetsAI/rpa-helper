"""把异常翻译成对用户友好的中文提示。

流程跑失败时，最终会在 QMessageBox 里给一线护士/办事员看到。直接
抛出 traceback 既看不懂也吓人，因此本模块根据异常类型 + 文本特征
推断常见原因，给出「标题 + 说明 + 建议 + 原始详情」的结构化结果。

Author: huaiqing.wang
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FriendlyError:
    """翻译后的友好错误。"""

    title: str   # 弹窗标题
    message: str  # 主体描述（一段话）
    hint: str    # 操作建议
    detail: str  # 原始异常文本，供技术支持排查


def translate(exc: BaseException) -> FriendlyError:
    """把异常映射到 FriendlyError；命中不到规则时回退到通用提示。"""
    raw = str(exc)
    exc_name = type(exc).__name__

    # --- Playwright 相关失败 --------------------------------------------

    # 验证码 / 反爬虫滑块：百度 passMod_slide、Cloudflare turnstile、
    # geetest、hCaptcha 等都通过 selector 名称识别。
    if any(marker in raw for marker in (
        "passMod_slide", "passMod_spin", "geetest", "g-recaptcha",
        "cf-turnstile", "hcaptcha", "nc_iconfont", "captcha",
    )):
        return FriendlyError(
            title="遇到验证码 / 反爬虫滑块",
            message="网站弹出了人机验证滑块或验证码，自动化工具无法绕过。",
            hint=(
                "处理方法：\n"
                "1) 删掉这一步（流程编辑页选中→删除）；\n"
                "2) 在那个位置加一个'确认'步骤，运行到这里会弹窗，"
                "让你手工滑完验证码再点继续；\n"
                "3) 后续操作正常自动化。"
            ),
            detail=raw,
        )

    # Playwright 通用 Timeout：元素没出现或点击目标消失。
    if exc_name in ("TimeoutError", "PlaywrightTimeoutError") \
            or ("Timeout" in raw and "exceeded" in raw and "locator" in raw):
        selector = _extract(raw, r'locator\("([^"]+)"\)')
        selector_hint = f"\n选择器: {selector}" if selector else ""
        return FriendlyError(
            title="找不到网页元素（超时）",
            message=(
                "在限定时间内没找到要操作的元素。常见原因：\n"
                "• 页面还没加载完就执行了这一步；\n"
                "• 录制时选择器选到了不稳定的元素；\n"
                "• 网页改版，元素 id/class 变了；\n"
                "• 跳出了验证码 / 登录弹窗。" + selector_hint
            ),
            hint=(
                "处理方法：\n"
                "1) 前面加一步'browser_wait_for'等关键元素出现；\n"
                "2) 在录制器里重录这一步，'试运行选中步骤'验证 selector；\n"
                "3) 增加超时（步骤编辑里的 timeout 字段）。"
            ),
            detail=raw,
        )

    # 导航失败（DNS、连接被拒、ERR_INTERNET_DISCONNECTED 等）。
    if "net::ERR_" in raw or "page.goto" in raw.lower():
        err = _extract(raw, r"net::ERR_[A-Z_]+")
        return FriendlyError(
            title="网页打不开",
            message=f"浏览器无法访问目标网址。{('错误码: ' + err) if err else ''}",
            hint=(
                "1) 检查网络连接；\n"
                "2) 浏览器里手动试一下这个 URL；\n"
                "3) 公司内网系统确认 VPN 已连上。"
            ),
            detail=raw,
        )

    # --- 通用规则 -------------------------------------------------------

    if exc_name == "InterruptedError" or "执行已停止" in raw or "用户取消" in raw:
        return FriendlyError(
            title="流程已停止",
            message=raw or "流程被手动停止。",
            hint="可以修改流程或调整目标程序后再次启动。",
            detail=raw,
        )

    # YAML 加载错误。
    if exc_name == "WorkflowLoadError" or "流程" in raw and ("缺少" in raw or "不存在" in raw):
        return FriendlyError(
            title="流程文件有问题",
            message=raw,
            hint="请打开 config/ 下的 YAML 文件检查格式，或新建一个空流程重新编辑。",
            detail=raw,
        )

    # 权限相关。
    if exc_name == "PermissionError" or "管理员" in raw:
        return FriendlyError(
            title="权限不足",
            message="操作受限，可能是文件被占用或没有写入权限。",
            hint="请关闭可能占用文件的程序，或右键以管理员身份运行。",
            detail=raw,
        )

    return FriendlyError(
        title="执行失败",
        message=raw or exc_name,
        hint="请查看运行日志了解详情，必要时把日志发给支持人员。",
        detail=f"{exc_name}: {raw}",
    )


def _extract(text: str, pattern: str) -> str:
    """从异常文本中抽出第一段命中的字符串，未命中返回空串。"""
    match = re.search(pattern, text)
    return match.group(0) if match else ""
