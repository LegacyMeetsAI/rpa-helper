"""error_translator 单元测试。

只覆盖现存规则：浏览器超时 / 验证码 / 网络 / 中断 / YAML / 通用兜底。
Author: huaiqing.wang
"""
from __future__ import annotations

from rpa_helper.core.workflow_loader import WorkflowLoadError
from rpa_helper.ui.error_translator import translate


def test_workflow_load_error() -> None:
    e = WorkflowLoadError("流程缺少 name")
    out = translate(e)
    assert "流程" in out.title


def test_user_cancelled() -> None:
    e = InterruptedError("用户取消执行")
    out = translate(e)
    assert "停止" in out.title


def test_unknown_exception_uses_generic_message() -> None:
    e = ValueError("something exotic")
    out = translate(e)
    assert out.title == "执行失败"
    assert "ValueError" in out.detail


# --- Playwright 相关 -----------------------------------------------------


def test_baidu_passmod_slider_recognized_as_captcha() -> None:
    """实测百度场景下抛出的 passMod_slide 错误必须命中验证码规则。"""
    msg = (
        'Page.click: Timeout 10000ms exceeded.\n'
        'Call log:\n'
        '  - waiting for locator("div.passMod_spin-context-wrap:nth-of-type(2) > '
        'div.passMod_spin-footer:nth-of-type(2) > div.passMod_slide-control:nth-of-type(1)")'
    )
    out = translate(RuntimeError(msg))
    assert "验证码" in out.title or "滑块" in out.title
    assert "确认" in out.hint


def test_geetest_captcha_recognized() -> None:
    out = translate(RuntimeError("click failed on .geetest_slider"))
    assert "验证码" in out.title or "滑块" in out.title


def test_recaptcha_recognized() -> None:
    out = translate(RuntimeError("waiting for #g-recaptcha-response"))
    assert "验证码" in out.title or "滑块" in out.title


def test_playwright_timeout_generic_helpful_message() -> None:
    msg = (
        'Page.click: Timeout 10000ms exceeded.\n'
        'Call log:\n'
        '  - waiting for locator("button.normal-button")'
    )
    out = translate(RuntimeError(msg))
    assert "超时" in out.title or "找不到" in out.title
    assert "button.normal-button" in out.message
    assert "browser_wait_for" in out.hint or "试运行" in out.hint


def test_playwright_timeout_does_not_mask_captcha_match() -> None:
    """命中验证码规则的优先级必须高于通用 Timeout 规则。"""
    msg = (
        'Page.click: Timeout 10000ms exceeded.\n'
        'Call log:\n  - waiting for locator(".passMod_slide-btn")'
    )
    out = translate(RuntimeError(msg))
    assert "验证码" in out.title or "滑块" in out.title


def test_network_error_recognized() -> None:
    out = translate(RuntimeError("page.goto: net::ERR_NAME_NOT_RESOLVED at https://nope.invalid/"))
    assert "打不开" in out.title or "网" in out.title
    assert "ERR_NAME_NOT_RESOLVED" in out.message
