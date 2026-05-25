"""浏览器种类的内联 SVG 图标。

用内联 SVG 而不是位图文件：
  1) 不污染仓库（无需 assets 目录 / 资源 qrc）；
  2) 任意 DPI 都清晰；
  3) PyInstaller 打包零额外配置——字符串随源码一起进 PYZ。

主窗口的「使用浏览器」下拉、步骤编辑对话框里的 ``browser_kind`` 字段
都通过 :func:`make_browser_icon` 拿同一份图标。

Author: huaiqing.wang
"""

from __future__ import annotations

from PyQt6.QtGui import QIcon, QPixmap


# 每个 SVG 是 24×24 的彩色圆形 logo 简化版，足够在下拉条目里一眼辨认。
_BROWSER_ICONS_SVG: dict[str, str] = {
    "auto": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="10" fill="#64748b"/>'
        '<text x="12" y="16" font-family="Segoe UI,Arial" font-size="11" font-weight="700"'
        ' text-anchor="middle" fill="#ffffff">A</text></svg>'
    ),
    "edge": (
        # Microsoft Edge：青-蓝渐变圆 + 白色"e"风格弧
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        '<defs><linearGradient id="edgeG" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%" stop-color="#3cc7f5"/>'
        '<stop offset="100%" stop-color="#0078d4"/></linearGradient></defs>'
        '<circle cx="12" cy="12" r="10" fill="url(#edgeG)"/>'
        '<path d="M7 13c0-3 2-5 5-5 2.5 0 4 1.5 4.5 3.5H10c-.5 1 0 2 1.5 2.5 2 .7 4.5.3 5.5-.5'
        '-.5 3-3 5-6 5-3 0-5-2-5-5.5z" fill="#ffffff"/></svg>'
    ),
    "chrome": (
        # Google Chrome：红/黄/绿三扇形 + 蓝色圆心
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        '<circle cx="12" cy="12" r="10" fill="#ffffff"/>'
        '<path d="M12 2a10 10 0 0 1 8.66 5H12a5 5 0 0 0-4.33 2.5L4.34 7.5A10 10 0 0 1 12 2z"'
        ' fill="#ea4335"/>'
        '<path d="M3.34 7.5L7 13.5a5 5 0 0 0 5 2.5 5 5 0 0 0 .8-.07L9.5 21.7A10 10 0 0 1 3.34 7.5z"'
        ' fill="#fbbc04"/>'
        '<path d="M20.66 7H12.8l3.7 6.5a5 5 0 0 1-3 7.7L17 14.5a10 10 0 0 0 3.66-7.5z"'
        ' fill="#34a853"/>'
        '<circle cx="12" cy="12" r="3.5" fill="#4285f4"/></svg>'
    ),
    "brave": (
        # Brave：橙色狮子盾牌的简化版
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
        '<path d="M12 2L20 5v7c0 4.5-3.5 8.5-8 10-4.5-1.5-8-5.5-8-10V5l8-3z"'
        ' fill="#fb542b"/>'
        '<path d="M12 6l4.5 1.5v4c0 2.8-2 5.3-4.5 6.2-2.5-.9-4.5-3.4-4.5-6.2v-4L12 6z"'
        ' fill="#ffffff"/>'
        '<path d="M12 9l2 1v2.5c0 1.4-1 2.6-2 3-1-.4-2-1.6-2-3V10l2-1z" fill="#fb542b"/></svg>'
    ),
}


def make_browser_icon(kind: str) -> QIcon:
    """根据浏览器种类返回一个 QIcon。

    内联 SVG → QPixmap → QIcon；未识别的 ``kind`` 回退到 ``auto``。
    """
    svg = _BROWSER_ICONS_SVG.get(kind, _BROWSER_ICONS_SVG["auto"])
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pixmap)
