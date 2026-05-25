"""步骤类型到表单字段的映射表。

只保留浏览器自动化 + 等待 + 人工确认 + 循环这四个分类。「桌面自动化」
分类（图片点击、OCR 等）整体已从产品中移除，对应的 schema 也一并删除。

新增步骤类型的步骤只有两步：
  1. 在 core/step_handlers 下新建一个 StepHandler 文件并 register
  2. 在本表里追加一个 StepSchema

Author: huaiqing.wang
"""

from __future__ import annotations

from dataclasses import dataclass

from rpa_helper.core.models import StepType
from rpa_helper.ui.form_fields import (
    FormField,
    boolean,
    child_steps,
    choice,
    hint,
    integer,
    multiline,
    number,
    text,
)


@dataclass
class StepSchema:
    """单种步骤在编辑器中的描述。"""

    label: str               # 下拉框中显示给用户的名字
    category: str            # 用于在下拉框里做分组
    default_name: str        # 用户没填名称时的回退值
    fields: list[FormField]  # 渲染该步骤所需的表单字段


# 通用占位符提示文本，多个 schema 复用。
_PLACEHOLDER_HINT = "支持 {{today}} / {{prompt:科室}} / {{order_id}} 等占位符"

SCHEMAS: dict[StepType, StepSchema] = {
    # ---------- 基础 ----------
    StepType.WAIT: StepSchema(
        label="等待",
        category="基础",
        default_name="等待",
        fields=[
            number("seconds", "等待秒数", default=1.0, min=0.1, max=3600.0, step=0.5),
        ],
    ),
    StepType.CONFIRM: StepSchema(
        label="人工确认",
        category="基础",
        default_name="人工确认",
        fields=[
            text("message", "确认文案", default="确认继续？", required=True,
                 help=_PLACEHOLDER_HINT),
        ],
    ),

    # ---------- 浏览器自动化 ----------
    StepType.BROWSER_OPEN: StepSchema(
        label="🌐 打开浏览器",
        category="浏览器自动化",
        default_name="打开浏览器",
        fields=[
            text("url", "URL", placeholder="https://oa.example.com/",
                 help=_PLACEHOLDER_HINT),
            boolean("connect_existing", "用本机浏览器（绕反爬）", default=False,
                    help="勾选后启动你电脑上已安装的浏览器，并通过 CDP 接入；"
                         "可绕过百度等网站对自动化的检测"),
            choice("browser_kind", "使用浏览器",
                   choices=[
                       ("自动检测（推荐 Edge → Chrome → Brave）", "auto"),
                       ("Microsoft Edge", "edge"),
                       ("Google Chrome", "chrome"),
                       ("Brave Browser", "brave"),
                   ],
                   default="auto",
                   help="仅在勾选「用本机浏览器」时生效"),
            text("chrome_path", "浏览器路径（可选）",
                 placeholder=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 help="留空 = 按上面的种类自动探测；指定路径时优先生效"),
            text("user_data_dir", "持久化目录",
                 placeholder="rpa_edge_profile / rpa_chrome_profile",
                 help="保存登录态/Cookie 的独立目录；CDP 模式下留空时按浏览器种类自动生成"),
            boolean("headless", "无界面运行", default=False,
                    help="勾选后浏览器在后台运行（仅默认模式生效；CDP 模式无效）"),
        ],
    ),
    StepType.BROWSER_CLOSE: StepSchema(
        label="🌐 关闭浏览器",
        category="浏览器自动化",
        default_name="关闭浏览器",
        fields=[hint("此步骤无需配置")],
    ),
    StepType.BROWSER_CLICK: StepSchema(
        label="🌐 点击元素",
        category="浏览器自动化",
        default_name="浏览器点击",
        fields=[
            text("selector", "CSS 选择器", required=True,
                 placeholder="button.submit, .row:nth-child(2) a",
                 help="F12 检查元素，右键 → Copy → Copy selector"),
            integer("timeout", "超时秒数", default=10, min=1, max=300),
        ],
    ),
    StepType.BROWSER_INPUT: StepSchema(
        label="🌐 表单输入",
        category="浏览器自动化",
        default_name="浏览器输入",
        fields=[
            text("selector", "CSS 选择器", required=True,
                 placeholder="input#username"),
            text("text", "输入内容", required=True, help=_PLACEHOLDER_HINT),
            integer("timeout", "超时秒数", default=10, min=1, max=300),
        ],
    ),
    StepType.BROWSER_WAIT_FOR: StepSchema(
        label="🌐 等待元素出现",
        category="浏览器自动化",
        default_name="等待元素",
        fields=[
            text("selector", "CSS 选择器", required=True,
                 placeholder=".loading-spinner, table.results"),
            integer("timeout", "超时秒数", default=30, min=1, max=600),
        ],
    ),
    StepType.BROWSER_EXTRACT: StepSchema(
        label="🌐 提取文本到变量",
        category="浏览器自动化",
        default_name="提取变量",
        fields=[
            text("selector", "CSS 选择器", required=True,
                 placeholder=".order-number"),
            text("save_as", "变量名", required=True,
                 placeholder="order_id",
                 help="后续步骤可用 {{order_id}} 引用此值"),
            text("attribute", "读取属性（可选）",
                 placeholder="href, value",
                 help="留空 = 读取文本内容；填 href = 读取链接地址"),
            integer("timeout", "超时秒数", default=10, min=1, max=300),
        ],
    ),
    StepType.BROWSER_DOWNLOAD: StepSchema(
        label="🌐 下载文件",
        category="浏览器自动化",
        default_name="下载文件",
        fields=[
            text("trigger_selector", "触发下载的元素", required=True,
                 placeholder=".attachment a.download"),
            text("save_dir", "保存目录", default="downloads/{{today}}/{{order_id}}",
                 help="支持占位符。相对路径会保存在程序目录下"),
            text("save_as", "保存到变量（可选）",
                 placeholder="downloaded_path",
                 help="将下载文件的完整路径存为变量"),
            integer("timeout", "下载超时秒数", default=30, min=5, max=600),
        ],
    ),
    StepType.BROWSER_GO_BACK: StepSchema(
        label="🌐 返回上一页",
        category="浏览器自动化",
        default_name="返回上一页",
        fields=[hint("浏览器执行 history.back()，无需配置")],
    ),

    # ---------- 控制流 ----------
    StepType.FOR_EACH: StepSchema(
        label="🔁 循环步骤",
        category="控制流",
        default_name="循环",
        fields=[
            hint("两种模式：选择器 = 遍历页面元素；列表 = 遍历给定项"),
            text("selector", "选择器（模式 A）",
                 placeholder="table.list tr.item",
                 help="留空则使用下面的 items 列表"),
            multiline("items", "列表项（模式 B，每行一个）",
                      placeholder="A001\nA002\nA003",
                      help="选择器为空时生效"),
            text("as", "循环变量名", default="item",
                 help="子步骤中可用 {{item}} {{item_index}} {{item_one_based}}"),
            integer("limit", "最多处理多少项", default=0, min=0, max=10000,
                    help="0 = 不限"),
            child_steps(),
        ],
    ),
}


def schema(step_type: StepType) -> StepSchema:
    """根据 StepType 取出对应的 schema。"""
    return SCHEMAS[step_type]


def categories() -> list[str]:
    """按 SCHEMAS 中出现顺序返回去重后的分类列表。"""
    seen: list[str] = []
    for s in SCHEMAS.values():
        if s.category not in seen:
            seen.append(s.category)
    return seen


def types_in_category(category: str) -> list[tuple[StepType, str]]:
    """列出某分类下的所有 (StepType, 显示文本) 元组。"""
    return [(t, s.label) for t, s in SCHEMAS.items() if s.category == category]
