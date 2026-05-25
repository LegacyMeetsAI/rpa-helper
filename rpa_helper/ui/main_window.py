"""主窗口（Qt 界面）。

只包含浏览器自动化所需的页面：
  * 执行面板：选择流程、查看状态/当前步骤、启动/停止
  * 流程编辑：手工增删改步骤
  * 浏览器录制：启动 Chromium 录制并自动生成 browser_* 步骤
  * 运行日志：实时滚动日志

桌面自动化、OCR、截图模板、全局热键、模拟运行模式均已移除。

Author: huaiqing.wang
"""

from __future__ import annotations

import traceback
from pathlib import Path
from threading import Event

from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rpa_helper.core.app_logger import build_logger
from rpa_helper.core.browser_recorder import BrowserRecorder, RecordedAction
from rpa_helper.core.models import StepType, Workflow, WorkflowStatus, WorkflowStep
from rpa_helper.core.safety import SafetyManager
from rpa_helper.core.workflow_engine import WorkflowEngine
from rpa_helper.core.workflow_loader import WorkflowLoadError, load_workflow
from rpa_helper.core.workflow_writer import save_workflow
from rpa_helper.ui.browser_icons import make_browser_icon
from rpa_helper.ui.controllers.workflow_editor import WorkflowEditor
from rpa_helper.ui.controllers.workflow_store import WorkflowStore
from rpa_helper.ui.step_dialog import StepDialog


_HELP_HTML = """
<h2>🚀 5 分钟跑通第一个流程</h2>
<ol>
  <li><b>新建流程</b>：点顶部「新建」，给流程起个名字（例如 <code>百度搜索测试</code>）。</li>
  <li><b>录制操作</b>：切到「浏览器录制」页 → 起始 URL 填 <code>https://www.baidu.com</code>
      → 勾选 <b>「用本机浏览器（绕反爬）」</b> → 点「开始浏览器录制」。
      在弹出的浏览器里正常搜索/点击，软件自动把动作转成步骤。</li>
  <li><b>停止录制</b>：操作完点「停止并保留」，再点「追加到流程」把步骤同步到当前流程。</li>
  <li><b>保存 & 运行</b>：切到「流程编辑」点「保存流程」→ 回「执行面板」按 <b>F8</b> 或点「开始执行」。</li>
</ol>

<h2>🌐 浏览器模式怎么选</h2>
<ul>
  <li><b>内置 Chromium（默认）</b>：开箱即用，无需另装浏览器。但 <code>navigator.webdriver=true</code>，
      会被百度、淘宝等网站的反爬识别为机器人，弹滑块验证。</li>
  <li><b>用本机浏览器</b>（推荐）：勾选后用你电脑上已装的 Edge / Chrome / Brave，
      通过 CDP 接管。用真实浏览器指纹，能<b>绕过绝大部分反爬</b>，
      登录态也保存在独立 profile 复用，不污染你日常使用的浏览器。</li>
</ul>

<h2>🧩 步骤类型速查</h2>
<ul>
  <li><b>🌐 打开浏览器 / 关闭浏览器</b>：启动 / 关闭浏览器窗口。</li>
  <li><b>🌐 点击元素 / 表单输入</b>：用 CSS 选择器定位元素后操作。
      不会写选择器？直接用「浏览器录制」让软件帮你抓。</li>
  <li><b>🌐 等待元素出现</b>：等到页面加载完目标元素再继续，避免还没出现就点空。</li>
  <li><b>🌐 提取文本到变量</b>：把页面上的文字（订单号、链接 href 等）存为变量，
      后续步骤用 <code>{{变量名}}</code> 引用。</li>
  <li><b>🌐 下载文件</b>：触发下载按钮 → 等下载完 → 自动落到指定目录。
      路径支持 <code>{{today}}</code> <code>{{order_id}}</code> 等占位符。</li>
  <li><b>🔁 循环步骤</b>：两种模式 —— 遍历页面元素（如表格每一行），或遍历给定列表。
      子步骤里用 <code>{{item}}</code> <code>{{item_index}}</code> 引用循环变量。</li>
  <li><b>⏱ 等待 / ✋ 人工确认</b>：固定睡 N 秒；或弹窗等你点「继续」再往下走（适合关键提交前复核）。</li>
</ul>

<h2>🔧 占位符（变量替换）</h2>
<p>很多字段（URL / 输入内容 / 保存路径 / 确认文案…）支持下面的占位符：</p>
<ul>
  <li><code>{{today}}</code> → 当天日期 <code>2026-05-25</code>；<code>{{now}}</code> → 精确到秒。</li>
  <li><code>{{prompt:科室}}</code> → 运行时弹输入框让你填写「科室」。</li>
  <li><code>{{order_id}}</code> → 引用前面「提取文本到变量」或循环里存的变量。</li>
</ul>

<h2>⚠️ 常见问题</h2>
<ul>
  <li><b>百度搜索弹滑块验证</b> → 改用「用本机浏览器」模式，再不会被识别。</li>
  <li><b>启动本机浏览器失败</b> → 关掉那个浏览器所有窗口（profile 被占用），或在「打开浏览器」步骤里手填 <code>chrome_path</code>。</li>
  <li><b>点击 / 输入失败：找不到元素</b> → 多半是页面还没加载完。在前面插一个「🌐 等待元素出现」。</li>
  <li><b>录制时点击没被记下来</b> → 检查页面是不是嵌套在 iframe 里（暂不支持跨 iframe 录制）；或确认你点的是真实可交互元素，不是纯展示的 div。</li>
  <li><b>下载文件没落地</b> → 看「运行日志」里的目标路径是否合理；相对路径会落到 exe 同目录。</li>
</ul>

<h2>⌨️ 快捷键</h2>
<ul>
  <li><b>F8</b>：开始执行当前流程</li>
  <li><b>Ctrl + Shift + Esc</b>：紧急停止运行中的流程</li>
</ul>

<h2>🛡 安全建议</h2>
<ul>
  <li>执行前先<b>手动登录</b>目标系统，登录态会自动保存到独立 profile 复用。</li>
  <li>关键提交（如审批、付款）前加一个「人工确认」步骤，避免误操作。</li>
  <li>发现异常按 <b>Ctrl + Shift + Esc</b> 立即停止。</li>
</ul>
"""


class WorkflowWorker(QThread):
    """流程执行工作线程。

    持有 WorkflowEngine 并在独立线程中跑流程，通过 pyqtSignal 与 UI
    通信。`confirm_requested` / `prompt_requested` 在 UI 弹窗结束后
    通过 answer_* 方法返回结果。
    """

    message = pyqtSignal(str)
    step_started = pyqtSignal(int, object)
    status_changed = pyqtSignal(str)
    confirm_requested = pyqtSignal(str)
    prompt_requested = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, workflow: Workflow, project_root: Path, safety: SafetyManager) -> None:
        super().__init__()
        self.workflow = workflow
        self.project_root = project_root
        self.safety = safety
        # 用于挂起线程等待 UI 回答
        self._confirm_event = Event()
        self._confirm_response = False
        self._prompt_event = Event()
        self._prompt_response = ""

    def run(self) -> None:
        """QThread 入口：构造引擎并执行流程。"""
        logger = build_logger(self.project_root / "logs")
        engine = WorkflowEngine(
            project_root=self.project_root,
            safety=self.safety,
            logger=logger,
            dry_run=False,
        )
        try:
            self.status_changed.emit(WorkflowStatus.RUNNING.value)
            engine.run(
                self.workflow,
                on_step_started=lambda index, step: self.step_started.emit(index, step),
                on_message=self.message.emit,
                on_confirm=self._confirm,
                on_prompt=self._prompt,
            )
        except InterruptedError as exc:
            self.status_changed.emit(WorkflowStatus.STOPPED.value)
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            logger.error("流程执行失败: %s\n%s", exc, traceback.format_exc())
            self.status_changed.emit(WorkflowStatus.FAILED.value)
            self.failed.emit(str(exc))
            return

        self.status_changed.emit(WorkflowStatus.COMPLETED.value)
        self.completed.emit()

    def request_stop(self) -> None:
        """请求停止：触发停止旗标并放行可能挂起的等待。"""
        self.safety.request_stop()
        self._confirm_response = False
        self._confirm_event.set()
        self._prompt_response = ""
        self._prompt_event.set()

    def answer_confirm(self, accepted: bool) -> None:
        """UI 端将人工确认结果回传给运行线程。"""
        self._confirm_response = accepted
        self._confirm_event.set()

    def answer_prompt(self, value: str) -> None:
        """UI 端将提示输入的内容回传给运行线程。"""
        self._prompt_response = value
        self._prompt_event.set()

    def _confirm(self, message: str) -> bool:
        """运行线程：发起确认请求并阻塞等待 UI 答复。"""
        self._confirm_response = False
        self._confirm_event.clear()
        self.confirm_requested.emit(message)
        self._confirm_event.wait()
        self.safety.raise_if_stopped()
        return self._confirm_response

    def _prompt(self, label: str, default: str) -> str:
        """运行线程：发起提示输入并阻塞等待 UI 答复。"""
        self._prompt_response = default
        self._prompt_event.clear()
        self.prompt_requested.emit(label, default)
        self._prompt_event.wait()
        self.safety.raise_if_stopped()
        return self._prompt_response


class MainWindow(QMainWindow):
    """主窗口：导航 + 4 个功能页。"""

    # 浏览器录制线程的事件信号（worker 线程 -> 主线程）
    browser_action_signal = pyqtSignal(object)

    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.safety = SafetyManager()
        self.workflow_dir = self.project_root / "config"
        self.workflow_files: list[Path] = []
        self.workflow_path: Path | None = None  # 启动时无默认流程
        self.workflow: Workflow | None = None
        self.worker: WorkflowWorker | None = None
        self.current_step_index = 0

        self.workflows = WorkflowStore(self.workflow_dir)

        # 浏览器录制相关状态
        self.browser_recorder: BrowserRecorder | None = None
        self.recorded_browser_steps: list[WorkflowStep] = []
        self._live_recorded_actions: list[RecordedAction] = []
        self.browser_action_signal.connect(self._handle_browser_action)

        self.setWindowTitle("RPA Helper")
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)

        self._build_ui()
        self._wire_shortcuts()
        self._load_workflows()

    # ------------------------------------------------------------------
    # UI 构造
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(18)
        outer.addLayout(body, 1)

        self.nav = self._build_nav()
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self.run_page = self._build_run_page()
        self.edit_page = self._build_edit_page()
        self.record_page = self._build_record_page()
        self.logs_page = self._build_logs_page()
        self.help_page = self._build_help_page()

        for page in (self.run_page, self.edit_page, self.record_page,
                     self.logs_page, self.help_page):
            self.stack.addWidget(page)

        self._set_styles()

    def _build_header(self) -> QHBoxLayout:
        """顶部标题 + 当前流程下拉。"""
        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("RPA Helper")
        title.setObjectName("Title")
        subtitle = QLabel("浏览器自动化 / 录制即用 / 本地运行")
        subtitle.setObjectName("Muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        # 当前流程切换条
        switcher = QHBoxLayout()
        switcher.setSpacing(8)
        switcher.addWidget(self._muted_label("当前流程"))
        self.workflow_combo = QComboBox()
        self.workflow_combo.setObjectName("WorkflowCombo")
        self.workflow_combo.setMinimumWidth(260)
        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_selected)
        switcher.addWidget(self.workflow_combo)

        new_btn = QPushButton("新建")
        new_btn.setObjectName("TinyButton")
        new_btn.clicked.connect(self._create_new_workflow)
        switcher.addWidget(new_btn)

        dup_btn = QPushButton("复制")
        dup_btn.setObjectName("TinyButton")
        dup_btn.clicked.connect(self._duplicate_current_workflow)
        switcher.addWidget(dup_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("TinyButton")
        del_btn.clicked.connect(self._delete_current_workflow)
        switcher.addWidget(del_btn)

        header.addLayout(switcher)
        return header

    def _build_nav(self) -> QFrame:
        """左侧 4 项导航栏。"""
        frame = QFrame()
        frame.setObjectName("NavCard")
        frame.setFixedWidth(220)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.nav_buttons: list[QPushButton] = []
        entries = [
            ("执行面板", 0),
            ("流程编辑", 1),
            ("浏览器录制", 2),
            ("运行日志", 3),
            ("使用说明", 4),
        ]
        for label, index in entries:
            button = QPushButton(label)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked=False, page=index: self._select_page(page))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        self._select_page(0)
        return frame

    def _build_run_page(self) -> QWidget:
        """执行面板：状态条 + 启动/停止按钮 + 当前步骤 + 进度条。"""
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 330)

        main_card = self._card("执行面板")
        main_layout = main_card.layout()

        # 状态条
        summary = QFrame()
        summary.setObjectName("InnerCard")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        status_box = QVBoxLayout()
        status_box.addWidget(self._muted_label("状态"))
        self.status_chip = QLabel("待机")
        self.status_chip.setObjectName("StatusChip")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_box.addWidget(self.status_chip)
        summary_layout.addLayout(status_box)
        main_layout.addWidget(summary)

        # 操作按钮（启动 / 停止）
        button_row = QHBoxLayout()
        self.start_button = QPushButton("开始执行 F8")
        self.start_button.setObjectName("PrimaryTallButton")
        self.stop_button = QPushButton("停止 Ctrl+Shift+Esc")
        self.stop_button.setObjectName("SecondaryTallButton")
        self.start_button.clicked.connect(self.start_workflow)
        self.stop_button.clicked.connect(self.stop_workflow)
        for button in (self.start_button, self.stop_button):
            button_row.addWidget(button)
        main_layout.addLayout(button_row)

        # 当前步骤区
        current = QFrame()
        current.setObjectName("SoftPanel")
        current_layout = QVBoxLayout(current)
        current_layout.setContentsMargins(18, 16, 18, 16)
        current_layout.addWidget(self._muted_label("当前步骤"))
        self.current_step_label = QLabel("等待开始")
        self.current_step_label.setObjectName("CurrentStep")
        current_layout.addWidget(self.current_step_label)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        current_layout.addWidget(self.progress)
        main_layout.addWidget(current)
        main_layout.addStretch(1)

        # 安全提示卡
        safety_card = self._card("安全提示")
        safety_layout = safety_card.layout()
        for text in (
            "执行前请手动登录目标系统",
            "找不到元素会自动停止",
            "提交/保存前通过 confirm 步骤确认",
            "按 Ctrl+Shift+Esc 可随时停止",
        ):
            hint = QLabel(text)
            hint.setObjectName("InfoPill")
            safety_layout.addWidget(hint)
        safety_layout.addStretch(1)

        layout.addWidget(main_card, 0, 0)
        layout.addWidget(safety_card, 0, 1)
        return page

    def _build_edit_page(self) -> QWidget:
        """流程编辑器页面。"""
        page = self._card("流程编辑器")
        self.steps_layout = page.layout()

        header = QHBoxLayout()
        header.addStretch(1)
        clear_button = QPushButton("清空流程")
        clear_button.setObjectName("DangerButton")
        clear_button.clicked.connect(self.clear_workflow)
        save_button = QPushButton("保存流程")
        save_button.setObjectName("SecondaryButton")
        save_button.clicked.connect(self.save_current_workflow)
        add_button = QPushButton("添加步骤")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_step)
        header.addWidget(clear_button)
        header.addWidget(save_button)
        header.addWidget(add_button)
        self.steps_layout.addLayout(header)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setObjectName("StepsScroll")
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.steps_widget = QWidget()
        self.steps_container = QVBoxLayout()
        self.steps_container.setContentsMargins(0, 0, 0, 0)
        self.steps_container.setSpacing(10)
        self.steps_widget.setLayout(self.steps_container)
        self.steps_scroll.setWidget(self.steps_widget)
        self.steps_layout.addWidget(self.steps_scroll, 1)
        return page

    def _build_record_page(self) -> QWidget:
        """浏览器录制页面。"""
        page = self._card("浏览器录制器")
        layout = page.layout()

        browser_tips = QLabel(
            "🌐 浏览器录制：点击按钮启动一个独立 Chromium 窗口，"
            "在里面正常点击/输入，软件自动生成 browser_* 步骤。"
        )
        browser_tips.setObjectName("InfoPill")
        browser_tips.setWordWrap(True)
        layout.addWidget(browser_tips)

        # URL 输入 + 启动/停止/追加按钮
        browser_row = QHBoxLayout()
        self.browser_record_url_input = QLineEdit()
        self.browser_record_url_input.setPlaceholderText("起始 URL（可留空）")
        browser_row.addWidget(self.browser_record_url_input, 1)

        self.browser_record_start_button = QPushButton("🌐 开始浏览器录制")
        self.browser_record_start_button.setObjectName("PrimaryTallButton")
        self.browser_record_start_button.clicked.connect(self.start_browser_recording)
        browser_row.addWidget(self.browser_record_start_button)

        self.browser_record_stop_button = QPushButton("停止并保留")
        self.browser_record_stop_button.setObjectName("SecondaryTallButton")
        self.browser_record_stop_button.clicked.connect(self.stop_browser_recording)
        browser_row.addWidget(self.browser_record_stop_button)

        self.browser_record_append_button = QPushButton("追加到流程")
        self.browser_record_append_button.setObjectName("SecondaryButton")
        self.browser_record_append_button.clicked.connect(self.append_browser_recording)
        browser_row.addWidget(self.browser_record_append_button)
        layout.addLayout(browser_row)

        # 「用本机浏览器」勾选 + 浏览器种类下拉：绕过百度等网站对 Playwright Chromium 的反爬检测。
        chrome_row = QHBoxLayout()
        self.browser_record_use_chrome_checkbox = QCheckBox("✅ 用本机浏览器（绕反爬）")
        self.browser_record_use_chrome_checkbox.setToolTip(
            "勾选后启动你电脑上已安装的浏览器进行录制。\n"
            "用真实浏览器指纹，可绕过百度等网站对自动化的检测。\n"
            "首次需手工登录目标网站；登录态保存到独立 profile 目录复用。"
        )
        chrome_row.addWidget(self.browser_record_use_chrome_checkbox)

        chrome_row.addWidget(QLabel("使用浏览器:"))
        self.browser_record_kind_combo = QComboBox()
        # 顺序与 step_schemas 保持一致，AUTO 排第一。
        # 每个条目带上对应浏览器的 SVG 图标，一眼能看清是哪个。
        self.browser_record_kind_combo.setIconSize(QSize(18, 18))
        self.browser_record_kind_combo.addItem(
            make_browser_icon("auto"), "自动检测（Edge → Chrome → Brave）", "auto"
        )
        self.browser_record_kind_combo.addItem(
            make_browser_icon("edge"), "Microsoft Edge", "edge"
        )
        self.browser_record_kind_combo.addItem(
            make_browser_icon("chrome"), "Google Chrome", "chrome"
        )
        self.browser_record_kind_combo.addItem(
            make_browser_icon("brave"), "Brave Browser", "brave"
        )
        self.browser_record_kind_combo.setToolTip(
            "选择具体浏览器；自动检测会按 Edge → Chrome → Brave 顺次探测，命中即用。"
        )
        chrome_row.addWidget(self.browser_record_kind_combo)
        chrome_row.addStretch(1)
        layout.addLayout(chrome_row)

        # 已录步骤列表（双击高亮，选中后可试运行）
        steps_label = QLabel("已录浏览器步骤（双击高亮，选中后可试运行）")
        steps_label.setObjectName("InfoPill")
        layout.addWidget(steps_label)

        self.browser_steps_list = QListWidget()
        self.browser_steps_list.setObjectName("StepList")
        self.browser_steps_list.itemDoubleClicked.connect(self._on_browser_step_double_clicked)
        layout.addWidget(self.browser_steps_list, 1)

        # 列表下方的辅助操作
        test_row = QHBoxLayout()
        self.browser_test_step_button = QPushButton("🔎 试运行选中步骤")
        self.browser_test_step_button.setObjectName("SecondaryButton")
        self.browser_test_step_button.clicked.connect(self.test_selected_recorded_step)
        test_row.addWidget(self.browser_test_step_button)

        self.browser_highlight_button = QPushButton("仅高亮选择器")
        self.browser_highlight_button.setObjectName("SecondaryButton")
        self.browser_highlight_button.clicked.connect(self.highlight_selected_recorded_step)
        test_row.addWidget(self.browser_highlight_button)

        self.browser_clear_steps_button = QPushButton("清空已录步骤")
        self.browser_clear_steps_button.setObjectName("SecondaryButton")
        self.browser_clear_steps_button.clicked.connect(self.clear_recorded_browser_steps)
        test_row.addWidget(self.browser_clear_steps_button)
        test_row.addStretch(1)
        layout.addLayout(test_row)

        # 录制日志预览
        self.record_preview = QPlainTextEdit()
        self.record_preview.setObjectName("LogOutput")
        self.record_preview.setReadOnly(True)
        self.record_preview.setPlaceholderText("录制结果预览会显示在这里...")
        layout.addWidget(self.record_preview, 1)
        return page

    def _build_logs_page(self) -> QWidget:
        """运行日志页面。"""
        page = self._card("运行日志")
        layout = page.layout()

        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("LogOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("运行日志会显示在这里...")
        layout.addWidget(self.log_output, 1)
        return page

    def _build_help_page(self) -> QWidget:
        """使用说明页面：让新用户能快速跑通一个浏览器自动化流程。"""
        page = self._card("使用说明")
        layout = page.layout()

        help_scroll = QScrollArea()
        help_scroll.setObjectName("StepsScroll")
        help_scroll.setWidgetResizable(True)
        help_scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 12, 4)
        body_layout.setSpacing(14)

        help_text = QLabel(_HELP_HTML)
        help_text.setObjectName("HelpText")
        help_text.setWordWrap(True)
        help_text.setTextFormat(Qt.TextFormat.RichText)
        help_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        help_text.setOpenExternalLinks(True)
        help_text.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        body_layout.addWidget(help_text)
        body_layout.addStretch(1)

        help_scroll.setWidget(body)
        layout.addWidget(help_scroll, 1)
        return page

    def _card(self, title: str) -> QFrame:
        """生成带标题的卡片容器。"""
        frame = QFrame()
        frame.setObjectName("Card")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(16)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        layout.addWidget(title_label)
        return frame

    # ------------------------------------------------------------------
    # 流程加载与切换
    # ------------------------------------------------------------------

    def _load_workflows(self) -> None:
        """刷新下拉列表；启动时若无任何流程，则不加载任何流程。"""
        self._refresh_workflow_combo()
        if not self.workflow_files:
            self._append_log("当前没有流程，请点击「新建」创建。")
            self._render_steps()
            return
        # 默认选中第一项
        self.workflow_path = self.workflow_files[0]
        self._load_workflow_file(self.workflow_path)

    def _load_workflow_file(self, path: Path) -> None:
        try:
            self.workflow = load_workflow(path)
        except WorkflowLoadError as exc:
            self._append_log(f"流程加载失败: {exc}")
            QMessageBox.critical(self, "流程加载失败", str(exc))
            self.workflow = None
            return
        self._append_log(f"已加载流程: {self.workflow.name}")
        self._render_steps()

    def _refresh_workflow_combo(self) -> None:
        """重新扫描 config/ 目录，重建下拉列表。"""
        if not hasattr(self, "workflow_combo"):
            return
        self.workflow_files = self.workflows.list_files()
        self.workflow_combo.blockSignals(True)
        try:
            self.workflow_combo.clear()
            if not self.workflow_files:
                # 占位提示项（不可选中）
                self.workflow_combo.addItem("（暂无流程，请点击「新建」）", None)
                self.workflow_combo.setEnabled(False)
                return
            self.workflow_combo.setEnabled(True)
            for path in self.workflow_files:
                self.workflow_combo.addItem(self.workflows.display_name(path), str(path))
            if self.workflow_path in self.workflow_files:
                self.workflow_combo.setCurrentIndex(
                    self.workflow_files.index(self.workflow_path)
                )
        finally:
            self.workflow_combo.blockSignals(False)

    def _on_workflow_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.workflow_files):
            return
        target = self.workflow_files[index]
        if target == self.workflow_path:
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "无法切换", "请先停止当前流程再切换。")
            self._refresh_workflow_combo()
            return
        self.workflow_path = target
        self._load_workflow_file(target)

    def _create_new_workflow(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "新建流程", "新流程文件名（不含扩展名）："
        )
        if not accepted or not name.strip():
            return
        try:
            path = self.workflows.create_blank(name)
        except (ValueError, FileExistsError) as exc:
            QMessageBox.warning(self, "无法创建", str(exc))
            return
        self.workflow_path = path
        self._refresh_workflow_combo()
        self._load_workflow_file(path)
        self._append_log(f"已创建新流程: {path.name}")

    def _duplicate_current_workflow(self) -> None:
        if self.workflow_path is None or not self.workflow_path.exists():
            QMessageBox.warning(self, "无法复制", "当前没有可复制的流程。")
            return
        name, accepted = QInputDialog.getText(
            self, "复制流程", "新流程文件名（不含扩展名）：",
            text=f"{self.workflow_path.stem}_副本",
        )
        if not accepted or not name.strip():
            return
        try:
            path = self.workflows.duplicate(self.workflow_path, name)
        except (ValueError, FileExistsError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "无法复制", str(exc))
            return
        self.workflow_path = path
        self._refresh_workflow_combo()
        self._load_workflow_file(path)
        self._append_log(f"已复制为: {path.name}")

    def _delete_current_workflow(self) -> None:
        if self.workflow_path is None or not self.workflow_path.exists():
            QMessageBox.information(self, "无法删除", "当前没有可删除的流程。")
            return
        result = QMessageBox.question(
            self, "删除流程", f"确定删除 {self.workflow_path.name}？此操作不可恢复。"
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            self.workflows.delete(self.workflow_path)
        except ValueError as exc:
            QMessageBox.warning(self, "无法删除", str(exc))
            return
        self._append_log(f"已删除流程: {self.workflow_path.name}")
        self.workflow_path = None
        self.workflow = None
        self._refresh_workflow_combo()
        # 若还有其它流程，自动加载第一个
        if self.workflow_files:
            self.workflow_path = self.workflow_files[0]
            self._load_workflow_file(self.workflow_path)
        else:
            self._render_steps()

    # ------------------------------------------------------------------
    # 步骤渲染与编辑
    # ------------------------------------------------------------------

    def _render_steps(self) -> None:
        """重新渲染流程编辑页的步骤列表。"""
        self._clear_layout(self.steps_container)
        if not self.workflow:
            return

        for index, step in enumerate(self.workflow.steps, start=1):
            row = QFrame()
            row.setObjectName("StepRow")
            row.setMinimumHeight(76)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row_layout = QGridLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setHorizontalSpacing(14)
            row_layout.setColumnMinimumWidth(0, 58)
            row_layout.setColumnStretch(1, 3)
            row_layout.setColumnStretch(2, 2)
            row_layout.setColumnStretch(3, 2)
            row_layout.setColumnMinimumWidth(4, 200)

            icon = QLabel(self._step_icon(step))
            icon.setObjectName("StepIcon")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_layout.addWidget(icon, 0, 0, 2, 1)

            name = QLabel(f"{index}. {step.name}")
            name.setObjectName("StepName")
            name.setWordWrap(True)
            row_layout.addWidget(name, 0, 1)

            step_type = QLabel(step.type.value)
            step_type.setObjectName("Muted")
            row_layout.addWidget(step_type, 1, 1)

            info = QLabel(self._step_summary(step))
            info.setObjectName("Muted")
            info.setWordWrap(True)
            row_layout.addWidget(info, 0, 2, 2, 2)

            actions = QHBoxLayout()
            actions.setSpacing(6)
            for action in ("上移", "下移", "编辑", "删除"):
                button = QPushButton(action)
                button.setObjectName("TinyButton")
                button.setMinimumWidth(42)
                if action == "上移":
                    button.clicked.connect(lambda checked=False, idx=index - 1: self.move_step(idx, -1))
                elif action == "下移":
                    button.clicked.connect(lambda checked=False, idx=index - 1: self.move_step(idx, 1))
                elif action == "编辑":
                    button.clicked.connect(lambda checked=False, idx=index - 1: self.edit_step(idx))
                else:
                    button.clicked.connect(lambda checked=False, idx=index - 1: self.delete_step(idx))
                actions.addWidget(button)
            row_layout.addLayout(actions, 0, 4, 2, 1)

            self.steps_container.addWidget(row)

    def add_step(self) -> None:
        if not self.workflow:
            QMessageBox.information(self, "无可编辑流程", "请先点击「新建」创建一个流程。")
            return
        dialog = StepDialog(self)
        if dialog.exec() != StepDialog.DialogCode.Accepted:
            return
        WorkflowEditor(self.workflow).add(dialog.to_step())
        self._render_steps()
        self._append_log("已添加步骤，记得保存流程")

    def edit_step(self, step_index: int) -> None:
        if not self.workflow or step_index < 0 or step_index >= len(self.workflow.steps):
            return
        dialog = StepDialog(self, self.workflow.steps[step_index])
        if dialog.exec() != StepDialog.DialogCode.Accepted:
            return
        WorkflowEditor(self.workflow).replace(step_index, dialog.to_step())
        self._render_steps()
        self._append_log(f"已编辑步骤 {step_index + 1}，记得保存流程")

    def move_step(self, step_index: int, direction: int) -> None:
        if not self.workflow:
            return
        editor = WorkflowEditor(self.workflow)
        try:
            new_index = editor.move(step_index, direction)
        except IndexError:
            return
        self.current_step_index = new_index
        self._render_steps()
        self._append_log("已调整步骤顺序，记得保存流程")

    def delete_step(self, step_index: int) -> None:
        if not self.workflow or step_index < 0 or step_index >= len(self.workflow.steps):
            return
        step = self.workflow.steps[step_index]
        result = QMessageBox.question(self, "删除步骤", f"确定删除“{step.name}”？")
        if result != QMessageBox.StandardButton.Yes:
            return
        WorkflowEditor(self.workflow).delete(step_index)
        self.current_step_index = min(self.current_step_index, max(0, len(self.workflow.steps) - 1))
        self._render_steps()
        self._append_log(f"已删除步骤: {step.name}，记得保存流程")

    def clear_workflow(self) -> None:
        if not self.workflow or not self.workflow.steps:
            return
        result = QMessageBox.question(self, "清空流程", "确定清空当前流程的所有步骤？")
        if result != QMessageBox.StandardButton.Yes:
            return
        WorkflowEditor(self.workflow).clear()
        self.current_step_index = 0
        self._render_steps()
        self._append_log("已清空流程，记得保存流程")

    def save_current_workflow(self) -> None:
        if not self.workflow or self.workflow_path is None:
            QMessageBox.information(self, "无可保存流程", "请先创建或选择一个流程。")
            return
        try:
            save_workflow(self.workflow_path, self.workflow)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._append_log(f"已保存流程: {self.workflow_path}")

    # ------------------------------------------------------------------
    # 浏览器录制（Playwright）
    # ------------------------------------------------------------------

    def start_browser_recording(self) -> None:
        if self.browser_recorder is not None and self.browser_recorder.is_recording():
            self._append_record_preview("浏览器录制已在运行")
            return
        url = self.browser_record_url_input.text().strip()
        use_chrome = self.browser_record_use_chrome_checkbox.isChecked()
        browser_kind = self.browser_record_kind_combo.currentData() or "auto"
        recorder = BrowserRecorder()
        # worker 线程产生的事件统一通过 signal 转发到主线程
        recorder.on_action = self._on_browser_action_thread
        if use_chrome:
            kind_label = self.browser_record_kind_combo.currentText()
            mode_hint = f"本机浏览器：{kind_label}"
        else:
            mode_hint = "内置 Chromium"
        self._append_record_preview(
            f"正在启动浏览器录制（{mode_hint}）… "
            f"{('打开 ' + url) if url else '(留空)'}"
        )
        try:
            recorder.start(
                url=url,
                timeout=30.0 if use_chrome else 20.0,
                connect_existing=use_chrome,
                browser_kind=browser_kind,
                project_root=self.project_root,
            )
        except Exception as exc:
            self._append_record_preview(f"浏览器录制启动失败: {exc}")
            if use_chrome:
                QMessageBox.warning(
                    self,
                    "无法启动本机浏览器录制",
                    f"{exc}\n\n常见原因：\n"
                    "1) 没装对应浏览器：请安装 Edge / Chrome / Brave 任意一款\n"
                    "2) 浏览器路径不在默认位置：在「打开浏览器」步骤里填 chrome_path\n"
                    "3) profile 目录被其他实例占用：关闭对应浏览器窗口，或换个浏览器",
                )
            else:
                QMessageBox.warning(
                    self,
                    "无法启动浏览器录制",
                    f"{exc}\n\n常见原因：\n"
                    "1) Playwright 未安装：pip install playwright\n"
                    "2) Chromium 未下载：python -m playwright install chromium",
                )
            return
        self.browser_recorder = recorder
        self._live_recorded_actions = []
        self.recorded_browser_steps = []
        self.browser_steps_list.clear()
        self._append_record_preview("✓ 浏览器录制已开始，请在浏览器中正常操作")
        self.browser_record_start_button.setEnabled(False)

    def stop_browser_recording(self) -> None:
        if self.browser_recorder is None:
            self._append_record_preview("没有在运行的浏览器录制")
            return
        try:
            steps = self.browser_recorder.stop(timeout=8.0)
        except Exception as exc:
            self._append_record_preview(f"停止浏览器录制时出错: {exc}")
            steps = []
        finally:
            self.browser_recorder = None
            self.browser_record_start_button.setEnabled(True)

        self.recorded_browser_steps = steps
        self._refresh_browser_steps_list()
        if not steps:
            self._append_record_preview("浏览器录制已停止，未捕获到任何步骤")
            QMessageBox.information(
                self, "录制结果为空",
                "本次录制没生成任何步骤。可能原因：\n\n"
                "• 你没在录制浏览器里点击/输入\n"
                "• 起始 URL 没填且浏览器还停在 about:blank\n"
                "• 你手动在地址栏跳转——这种跳转不算录制事件，请在跳转后再开始点击",
            )
            return
        self._append_record_preview(
            f"✓ 浏览器录制已停止，共 {len(steps)} 步。"
            f'选中条目可"试运行"或"追加到流程"。'
        )

    def append_browser_recording(self) -> None:
        if not self.workflow:
            self._append_record_preview("当前没有打开的流程")
            QMessageBox.information(
                self, "没有当前流程",
                "请先在「流程编辑」页新建一个流程，再回来追加录制结果。",
            )
            return
        if not self.recorded_browser_steps:
            self._append_record_preview("没有浏览器录制结果可追加")
            QMessageBox.information(
                self, "没有可追加的步骤",
                "录制列表为空。可能原因：\n"
                "• 还没点击/输入过任何元素\n"
                "• 录制时所有点击都被脚本忽略（没找到稳定选择器）\n\n"
                "请先在录制浏览器里点击或输入，列表会实时显示已录步骤。",
            )
            return
        steps = self.recorded_browser_steps
        WorkflowEditor(self.workflow).extend(steps)
        self._render_steps()
        self._append_log(f"已追加 {len(steps)} 个浏览器录制步骤，记得保存流程")
        self._append_record_preview(f"已追加 {len(steps)} 个步骤到流程")
        self.recorded_browser_steps = []
        self.browser_steps_list.clear()

    def clear_recorded_browser_steps(self) -> None:
        self.recorded_browser_steps = []
        self._live_recorded_actions = []
        self.browser_steps_list.clear()
        self._append_record_preview("已清空录制步骤")

    def _on_browser_action_thread(self, action) -> None:
        """录制 worker 线程的回调：统一通过 signal 转发到主线程。"""
        self.browser_action_signal.emit(action)

    def _handle_browser_action(self, action) -> None:
        """主线程：将单条事件追加到 live 列表并重新汇总步骤列表。"""
        kind = getattr(action, "kind", "?")
        name = getattr(action, "name", "")
        value = getattr(action, "value", "")
        candidates = getattr(action, "candidates", []) or []
        selector = candidates[0] if candidates else ""
        if kind == "click":
            self._append_record_preview(f"  + click {selector} ({name[:30]})")
        elif kind == "input":
            self._append_record_preview(f"  + input {selector} = {value[:40]}")
        elif kind == "navigate":
            self._append_record_preview(f"  → navigate {value}")

        self._live_recorded_actions.append(action)
        # 基于完整 action 列表重新折算步骤（含合并规则）
        steps = BrowserRecorder.actions_to_steps(self._live_recorded_actions)
        self.recorded_browser_steps = steps
        self._refresh_browser_steps_list()

    def _refresh_browser_steps_list(self) -> None:
        """从 self.recorded_browser_steps 刷新 QListWidget。"""
        self.browser_steps_list.clear()
        for i, step in enumerate(self.recorded_browser_steps, 1):
            selector = step.raw.get("selector") or step.raw.get("url") or ""
            label = f"{i:>2}. {step.name}"
            if selector:
                label += f"   [{selector[:50]}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, i - 1)
            self.browser_steps_list.addItem(item)

    def _selected_recorded_step(self) -> WorkflowStep | None:
        item = self.browser_steps_list.currentItem()
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx < 0 or idx >= len(self.recorded_browser_steps):
            return None
        return self.recorded_browser_steps[idx]

    def test_selected_recorded_step(self) -> None:
        if self.browser_recorder is None or not self.browser_recorder.is_recording():
            self._append_record_preview("录制浏览器未运行，无法试运行")
            QMessageBox.information(
                self, "试运行步骤",
                "请先点「开始浏览器录制」启动录制浏览器，再试运行步骤。",
            )
            return
        step = self._selected_recorded_step()
        if step is None:
            self._append_record_preview("请先在列表里选中一个步骤")
            return
        self._append_record_preview(f"▶ 试运行: {step.name}")
        result = self.browser_recorder.test_step(step, timeout=15.0)
        prefix = "✓" if result.ok else "✗"
        self._append_record_preview(f"  {prefix} {result.message}")
        if not result.ok:
            QMessageBox.warning(self, "试运行失败", result.message or "执行失败")

    def highlight_selected_recorded_step(self) -> None:
        if self.browser_recorder is None or not self.browser_recorder.is_recording():
            self._append_record_preview("录制浏览器未运行，无法高亮")
            return
        step = self._selected_recorded_step()
        if step is None:
            self._append_record_preview("请先在列表里选中一个步骤")
            return
        selector = step.raw.get("selector", "")
        if not selector:
            self._append_record_preview("该步骤没有可高亮的选择器")
            return
        result = self.browser_recorder.highlight_selector(selector, timeout=3.0)
        prefix = "✓" if result.ok else "✗"
        self._append_record_preview(f"  {prefix} 高亮 {selector[:40]}: {result.message}")

    def _on_browser_step_double_clicked(self, _item) -> None:
        """双击列表项 = 高亮选择器。"""
        self.highlight_selected_recorded_step()

    def _append_record_preview(self, message: str) -> None:
        self.record_preview.appendPlainText(message)

    # ------------------------------------------------------------------
    # 流程运行
    # ------------------------------------------------------------------

    def start_workflow(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.workflow:
            QMessageBox.information(self, "无流程可运行", "请先新建或选择一个流程。")
            return
        if not self.workflow.steps:
            QMessageBox.information(self, "流程为空", "请先在「流程编辑」中至少添加一个步骤。")
            return
        self._run_workflow(self.workflow)

    def _run_workflow(self, workflow: Workflow) -> None:
        """构造 worker 线程并启动；同时只允许一个流程运行。"""
        if self.worker is not None:
            try:
                self.worker.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.worker.isRunning():
                self.worker.request_stop()
                self.worker.wait(1500)
            self.worker.deleteLater()
            self.worker = None

        self.safety = SafetyManager()
        snapshot = workflow.snapshot()
        self.worker = WorkflowWorker(snapshot, self.project_root, self.safety)
        self.worker.message.connect(self._append_log)
        self.worker.step_started.connect(self._on_step_started)
        self.worker.status_changed.connect(self._set_status)
        self.worker.confirm_requested.connect(self._handle_confirm)
        self.worker.prompt_requested.connect(self._handle_prompt)
        self.worker.failed.connect(self._on_failed)
        self.worker.completed.connect(self._on_completed)

        self._set_editing_enabled(False)
        self._set_status(WorkflowStatus.RUNNING.value)
        self.progress.setValue(0)
        self.current_step_label.setText("准备执行")
        self.worker.start()

    def stop_workflow(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self._set_status(WorkflowStatus.STOPPING.value)
            self._append_log("正在停止执行...")
        else:
            self.safety.request_stop()
            self._set_status(WorkflowStatus.STOPPED.value)

    def _on_step_started(self, index: int, step: WorkflowStep) -> None:
        if self.workflow and step in self.workflow.steps:
            self.current_step_index = self.workflow.steps.index(step)
        total = len(self.worker.workflow.steps) if self.worker else 1
        self.current_step_label.setText(step.name)
        self.progress.setValue(int(((index - 1) / total) * 100))

    def _on_completed(self) -> None:
        self.progress.setValue(100)
        self.current_step_label.setText("流程执行完成")
        self._append_log("流程执行完成")
        self._set_editing_enabled(True)

    def _on_failed(self, message: str) -> None:
        self._append_log(f"执行停止: {message}")
        self._set_editing_enabled(True)
        if self.status_chip.text() in ("已停止", "停止中"):
            return
        self._show_friendly_failure(message)

    def _show_friendly_failure(self, raw_message: str) -> None:
        """把异常文案翻译为友好提示。"""
        from rpa_helper.ui.error_translator import translate

        friendly = translate(Exception(raw_message))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(friendly.title)
        box.setText(friendly.message)
        box.setInformativeText(friendly.hint)
        box.setDetailedText(friendly.detail)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()

    def _handle_prompt(self, label: str, default: str) -> None:
        if not self.worker:
            return
        text, accepted = QInputDialog.getText(
            self, "请输入", f"{label}：", text=default
        )
        if not accepted:
            self.worker.answer_prompt(default)
            return
        self.worker.answer_prompt(text)

    def _handle_confirm(self, message: str) -> None:
        if not self.worker:
            return
        result = QMessageBox.question(self, "人工确认", message)
        self.worker.answer_confirm(result == QMessageBox.StandardButton.Yes)

    def _set_status(self, status: str) -> None:
        """同步状态条文字 + 样式属性，触发 QSS 重新计算颜色。"""
        text_by_status = {
            WorkflowStatus.IDLE.value: "待机",
            WorkflowStatus.RUNNING.value: "运行中",
            WorkflowStatus.STOPPING.value: "停止中",
            WorkflowStatus.STOPPED.value: "已停止",
            WorkflowStatus.COMPLETED.value: "已完成",
            WorkflowStatus.FAILED.value: "失败",
        }
        self.status_chip.setText(text_by_status.get(status, status))
        self.status_chip.setProperty("status", status)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

    # ------------------------------------------------------------------
    # 杂项
    # ------------------------------------------------------------------

    def _select_page(self, index: int) -> None:
        if hasattr(self, "stack"):
            self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(getattr(self, "nav_buttons", [])):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence("F8"), self, activated=self.start_workflow)
        QShortcut(QKeySequence("Ctrl+Shift+Esc"), self, activated=self.stop_workflow)

    def _set_editing_enabled(self, enabled: bool) -> None:
        """运行期间禁用编辑/录制按钮，避免误操作。"""
        widgets = (
            getattr(self, "start_button", None),
            getattr(self, "browser_record_start_button", None),
        )
        for widget in widgets:
            if widget is not None:
                widget.setEnabled(enabled)
        scroll = getattr(self, "steps_scroll", None)
        if scroll is not None:
            scroll.setEnabled(enabled)

    def closeEvent(self, event) -> None:
        """关闭窗口时尽量优雅地终止浏览器录制和运行线程。"""
        if self.browser_recorder is not None and self.browser_recorder.is_recording():
            try:
                self.browser_recorder.stop(timeout=3.0)
            except Exception:
                pass
            self.browser_recorder = None
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(3000)
        super().closeEvent(event)

    def _muted_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        return label

    def _step_icon(self, step: WorkflowStep) -> str:
        """步骤行左侧的小图标文字。"""
        icons = {
            "wait": "Wait",
            "confirm": "Check",
            "browser_open": "Open",
            "browser_close": "Close",
            "browser_click": "Click",
            "browser_input": "Input",
            "browser_wait_for": "WaitEl",
            "browser_extract": "Extract",
            "browser_download": "DL",
            "browser_go_back": "Back",
            "for_each": "Loop",
        }
        return icons.get(step.type.value, "Step")

    def _step_summary(self, step: WorkflowStep) -> str:
        """步骤行右侧的一句摘要：尽量显示选择器/URL/秒数等关键信息。"""
        t = step.type.value
        if t == "wait":
            return f"{step.seconds:g} 秒"
        if t == "confirm":
            return step.message
        if t == "browser_open":
            return step.url or "(无 URL)"
        if t in ("browser_click", "browser_input", "browser_wait_for", "browser_extract"):
            return step.selector
        if t == "browser_download":
            return f"{step.trigger_selector} → {step.save_dir}"
        if t == "for_each":
            sel = step.selector
            return f"循环 {sel}" if sel else f"循环 {len(step.child_steps)} 子步骤"
        return ""

    def _clear_layout(self, layout) -> None:
        """递归清空一个布局里的所有 widget / 子布局。"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _set_styles(self) -> None:
        """整窗 QSS。下拉框做了更明显的悬停/聚焦反馈。"""
        self.setStyleSheet(
            """
            #Root {
                background: #f1f5f9;
                color: #0f172a;
                font-family: "Microsoft YaHei", "Segoe UI";
                font-size: 14px;
            }
            #Title {
                color: #0f172a;
                font-size: 30px;
                font-weight: 800;
            }
            #Muted {
                color: #64748b;
                font-size: 13px;
            }
            #NavCard, #Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 22px;
            }
            #CardTitle {
                color: #0f172a;
                font-size: 18px;
                font-weight: 700;
            }
            QPushButton {
                border: 0;
                border-radius: 14px;
                padding: 10px 16px;
                font-weight: 600;
            }
            QPushButton[nav="true"] {
                color: #334155;
                background: transparent;
                text-align: left;
                padding: 13px 16px;
            }
            QPushButton[nav="true"]:hover {
                background: #f1f5f9;
            }
            QPushButton[nav="true"][active="true"] {
                color: #ffffff;
                background: #0f172a;
            }
            #PrimaryButton, #PrimaryTallButton {
                color: #ffffff;
                background: #0f172a;
            }
            #PrimaryButton:hover, #PrimaryTallButton:hover {
                background: #1e293b;
            }
            #SecondaryButton, #SecondaryTallButton, #TinyButton {
                color: #0f172a;
                background: #ffffff;
                border: 1px solid #cbd5e1;
            }
            #SecondaryButton:hover, #SecondaryTallButton:hover, #TinyButton:hover {
                background: #f8fafc;
            }
            #DangerButton {
                color: #991b1b;
                background: #fff1f2;
                border: 1px solid #fecdd3;
            }
            #DangerButton:hover {
                background: #ffe4e6;
            }
            #PrimaryTallButton, #SecondaryTallButton {
                min-height: 48px;
                font-size: 15px;
            }
            #TinyButton {
                padding: 7px 10px;
                border-radius: 10px;
                font-size: 12px;
            }
            #InnerCard, #StepRow {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
            }
            #StepsScroll {
                background: transparent;
                border: 0;
            }
            #SoftPanel {
                background: #f8fafc;
                border-radius: 20px;
            }
            #StatusChip {
                min-width: 80px;
                padding: 6px 14px;
                color: #047857;
                background: #ecfdf5;
                border-radius: 12px;
                font-weight: 700;
            }
            #StatusChip[status="running"] {
                color: #1d4ed8;
                background: #eff6ff;
            }
            #StatusChip[status="failed"] {
                color: #b91c1c;
                background: #fef2f2;
            }
            #StatusChip[status="stopped"], #StatusChip[status="stopping"] {
                color: #92400e;
                background: #fffbeb;
            }
            #CurrentStep {
                color: #0f172a;
                font-size: 24px;
                font-weight: 750;
            }
            /* 当前流程下拉框：更厚实、有悬停/聚焦/禁用三态 */
            #WorkflowCombo {
                min-height: 38px;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 4px 14px;
                background: #ffffff;
                color: #0f172a;
                font-size: 15px;
                font-weight: 650;
            }
            #WorkflowCombo:hover {
                border-color: #94a3b8;
            }
            #WorkflowCombo:focus {
                border-color: #0f172a;
                background: #f8fafc;
            }
            #WorkflowCombo:disabled {
                color: #94a3b8;
                background: #f1f5f9;
            }
            #WorkflowCombo::drop-down {
                width: 30px;
                border: 0;
            }
            #WorkflowCombo::down-arrow {
                width: 10px;
                height: 10px;
            }
            #WorkflowCombo QAbstractItemView {
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 6px 4px;
                background: #ffffff;
                selection-background-color: #0f172a;
                selection-color: #ffffff;
                outline: 0;
            }
            #InfoPill {
                color: #475569;
                background: #f8fafc;
                border-radius: 14px;
                padding: 12px 14px;
            }
            #StepIcon {
                min-width: 46px;
                min-height: 40px;
                color: #334155;
                background: #f1f5f9;
                border-radius: 14px;
                font-weight: 700;
                font-size: 12px;
            }
            #StepName {
                color: #0f172a;
                font-weight: 700;
            }
            #LogOutput {
                color: #e2e8f0;
                background: #020617;
                border-radius: 18px;
                padding: 14px;
                font-family: Consolas, "Microsoft YaHei";
            }
            #HelpText {
                color: #1f2937;
                font-size: 14px;
                line-height: 170%;
                padding: 4px 10px;
            }
            QProgressBar {
                min-height: 12px;
                max-height: 12px;
                border: 0;
                border-radius: 6px;
                background: #e2e8f0;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #0f172a;
            }
            """
        )
