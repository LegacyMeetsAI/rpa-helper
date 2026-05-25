"""可视化的步骤编辑对话框。

所有控件都根据 ui.step_schemas.SCHEMAS 中的 FormField 描述自动生成；
新增/删除步骤类型只需要改 SCHEMAS，不必动这个文件。

Author: huaiqing.wang
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.ui.browser_icons import make_browser_icon
from rpa_helper.ui.form_fields import FormField
from rpa_helper.ui.step_schemas import SCHEMAS, categories, schema


class StepDialog(QDialog):
    """数据驱动的步骤编辑器。

    每种 StepType 在 SCHEMAS 中对应一份字段列表，本对话框据此生成 UI、
    校验输入并写回 WorkflowStep。
    """

    def __init__(
        self,
        parent=None,
        step: WorkflowStep | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("编辑步骤" if step else "添加步骤")
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)

        # 顶部：类型选择 + 名称两行公共表单。
        header_form = QFormLayout()
        layout.addLayout(header_form)

        self.type_combo = QComboBox()
        self._populate_type_combo()
        self.type_combo.currentIndexChanged.connect(self._sync_type_page)
        header_form.addRow("类型", self.type_combo)

        self.name_input = QLineEdit()
        header_form.addRow("名称", self.name_input)

        # 中部：根据所选类型切换的 StackedWidget。
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # widgets[step_type][field_key] -> 控件，用于读写字段值。
        self.widgets: dict[StepType, dict[str, QWidget]] = {}
        # 仅 FOR_EACH 用到的子步骤列表与对应数据。
        self.child_lists: dict[StepType, QListWidget] = {}
        self.child_data: dict[StepType, list[dict]] = {}

        self._page_index_by_type: dict[StepType, int] = {}
        for step_type, sch in SCHEMAS.items():
            page = self._build_page_for(step_type, sch.fields)
            self._page_index_by_type[step_type] = self.stack.addWidget(page)

        # 底部确认/取消按钮。
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if step:
            self._load_step(step)
        self._sync_type_page()

    # ------------------------------------------------------------------
    # 对外方法
    # ------------------------------------------------------------------

    def accept(self) -> None:
        """点击「确定」时先做必填校验，再关闭。"""
        error = self._validation_error()
        if error:
            QMessageBox.warning(self, "步骤配置不完整", error)
            return
        super().accept()

    def to_step(self) -> WorkflowStep:
        """根据当前控件值组装出一个 WorkflowStep。"""
        step_type: StepType = self.type_combo.currentData()
        sch = schema(step_type)
        name = self.name_input.text().strip() or sch.default_name
        raw: dict[str, Any] = {"type": step_type.value, "name": name}

        for f in sch.fields:
            if f.kind == "hint" or not f.key:
                continue
            if f.kind == "child_steps":
                raw[f.key] = list(self.child_data.get(step_type, []))
                continue
            widget = self.widgets[step_type].get(f.key)
            if widget is None:
                continue
            raw[f.key] = self._read_widget(widget, f)

        return WorkflowStep(type=step_type, name=name, raw=raw)

    # ------------------------------------------------------------------
    # 构建 UI
    # ------------------------------------------------------------------

    def _populate_type_combo(self) -> None:
        """填充类型下拉框，按 category 分组并插入分隔线。"""
        first = True
        for cat in categories():
            if not first:
                # 用一行分隔条把不同分类分开（不可选）。
                self.type_combo.insertSeparator(self.type_combo.count())
            first = False
            for step_type, label in [
                (t, SCHEMAS[t].label) for t in SCHEMAS if SCHEMAS[t].category == cat
            ]:
                self.type_combo.addItem(f"[{cat}] {label}", step_type)

    def _build_page_for(self, step_type: StepType, fields: list[FormField]) -> QWidget:
        """为单个步骤类型构建表单页面。"""
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.widgets[step_type] = {}

        for f in fields:
            widget, row_label = self._make_widget(step_type, f)
            if f.kind == "hint":
                form.addRow(QLabel(f.label))
                continue
            if f.kind == "child_steps":
                # 子步骤编辑器占整行。
                form.addRow(row_label, widget)
                continue
            if widget is None:
                continue
            self.widgets[step_type][f.key] = widget
            form.addRow(row_label, widget)
            if f.help:
                tip = QLabel(f.help)
                tip.setObjectName("Muted")
                tip.setWordWrap(True)
                form.addRow("", tip)

        return page

    def _make_widget(
        self, step_type: StepType, f: FormField
    ) -> tuple[QWidget | None, str]:
        """根据 FormField.kind 生成对应控件。"""
        label = f"{f.label} *" if f.required else f.label

        if f.kind == "hint":
            return None, ""
        if f.kind == "text":
            w = QLineEdit()
            if f.default:
                w.setText(str(f.default))
            if f.placeholder:
                w.setPlaceholderText(f.placeholder)
            return w, label
        if f.kind == "multiline":
            w = QPlainTextEdit()
            if f.default:
                w.setPlainText(str(f.default))
            if f.placeholder:
                w.setPlaceholderText(f.placeholder)
            w.setFixedHeight(80)
            return w, label
        if f.kind == "int":
            w = QSpinBox()
            w.setRange(int(f.min), int(f.max))
            w.setValue(int(f.default or 0))
            return w, label
        if f.kind == "float":
            w = QDoubleSpinBox()
            w.setRange(float(f.min), float(f.max))
            w.setSingleStep(float(f.step or 0.1))
            w.setValue(float(f.default or 0.0))
            return w, label
        if f.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(f.default))
            return w, label
        if f.kind == "choice":
            w = QComboBox()
            # 浏览器种类下拉特殊处理：每项前缀挂对应浏览器 logo，一眼能看清。
            if f.key == "browser_kind":
                w.setIconSize(QSize(18, 18))
                for display, value in f.choices:
                    w.addItem(make_browser_icon(value), display, value)
            else:
                for display, value in f.choices:
                    w.addItem(display, value)
            if f.default is not None:
                idx = w.findData(f.default)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            return w, label
        if f.kind == "child_steps":
            return self._make_child_steps_widget(step_type), label

        return None, label

    def _make_child_steps_widget(self, step_type: StepType) -> QWidget:
        """为 FOR_EACH 步骤构建子步骤列表 + 操作按钮组合控件。"""
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        list_widget.setMaximumHeight(160)
        self.child_lists[step_type] = list_widget
        self.child_data[step_type] = []
        v.addWidget(list_widget)

        buttons = QHBoxLayout()
        add_btn = QPushButton("添加子步骤")
        edit_btn = QPushButton("编辑")
        remove_btn = QPushButton("删除")
        up_btn = QPushButton("上移")
        down_btn = QPushButton("下移")
        for b in (add_btn, edit_btn, remove_btn, up_btn, down_btn):
            b.setObjectName("TinyButton")
            buttons.addWidget(b)
        v.addLayout(buttons)

        add_btn.clicked.connect(lambda: self._child_add(step_type))
        edit_btn.clicked.connect(lambda: self._child_edit(step_type))
        remove_btn.clicked.connect(lambda: self._child_remove(step_type))
        up_btn.clicked.connect(lambda: self._child_move(step_type, -1))
        down_btn.clicked.connect(lambda: self._child_move(step_type, 1))

        list_widget.itemDoubleClicked.connect(lambda _: self._child_edit(step_type))

        return container

    # ------------------------------------------------------------------
    # 读写控件值
    # ------------------------------------------------------------------

    def _load_step(self, step: WorkflowStep) -> None:
        """把已存在的 step 值回填到对应控件上。"""
        idx = self.type_combo.findData(step.type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.name_input.setText(step.name)

        sch = schema(step.type)
        for f in sch.fields:
            if f.kind == "hint" or not f.key:
                continue
            if f.kind == "child_steps":
                self._load_child_steps(step.type, step.raw.get(f.key) or [])
                continue
            widget = self.widgets[step.type].get(f.key)
            if widget is None:
                continue
            value = step.raw.get(f.key, f.default)
            self._write_widget(widget, f, value)

    def _read_widget(self, widget: QWidget, f: FormField) -> Any:
        """把控件当前值转换为 YAML 可序列化的 Python 值。"""
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QPlainTextEdit):
            text = widget.toPlainText().strip()
            if not text:
                return []
            # 多行文本按行拆分成列表（for_each 的 items 字段）。
            return [line.strip() for line in text.splitlines() if line.strip()]
        if isinstance(widget, QSpinBox):
            return widget.value()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            return data if data is not None else widget.currentText().strip()
        return None

    def _write_widget(self, widget: QWidget, f: FormField, value: Any) -> None:
        """把 YAML 中的值回填到控件，类型不匹配时静默忽略。"""
        if value is None:
            return
        if isinstance(widget, QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, QPlainTextEdit):
            if isinstance(value, list):
                widget.setPlainText("\n".join(str(v) for v in value))
            else:
                widget.setPlainText(str(value))
        elif isinstance(widget, QSpinBox):
            try:
                widget.setValue(int(value))
            except (TypeError, ValueError):
                pass
        elif isinstance(widget, QDoubleSpinBox):
            try:
                widget.setValue(float(value))
            except (TypeError, ValueError):
                pass
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
            idx = widget.findData(value)
            if idx >= 0:
                widget.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # 子步骤管理（仅 for_each 用）
    # ------------------------------------------------------------------

    def _load_child_steps(self, step_type: StepType, raws: list[dict]) -> None:
        """加载已有子步骤列表。"""
        list_widget = self.child_lists.get(step_type)
        if list_widget is None:
            return
        self.child_data[step_type] = list(raws)
        list_widget.clear()
        for raw in raws:
            list_widget.addItem(self._render_child_label(raw))

    def _render_child_label(self, raw: dict) -> str:
        """生成子步骤列表项的显示文字。"""
        type_value = raw.get("type", "?")
        try:
            step_type = StepType(type_value)
            label = SCHEMAS[step_type].label
        except (ValueError, KeyError):
            label = type_value
        name = raw.get("name", "").strip()
        if name:
            return f"{label} — {name}"
        return label

    def _child_add(self, step_type: StepType) -> None:
        """弹出子对话框新建一个子步骤。"""
        dialog = StepDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_step = dialog.to_step()
        self.child_data[step_type].append(dict(new_step.raw))
        self.child_lists[step_type].addItem(self._render_child_label(new_step.raw))

    def _child_edit(self, step_type: StepType) -> None:
        """编辑当前选中的子步骤。"""
        list_widget = self.child_lists[step_type]
        row = list_widget.currentRow()
        if row < 0:
            return
        raw = self.child_data[step_type][row]
        existing_step = WorkflowStep(
            type=StepType(raw["type"]),
            name=raw.get("name", ""),
            raw=raw,
        )
        dialog = StepDialog(self, step=existing_step)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.to_step()
        self.child_data[step_type][row] = dict(updated.raw)
        list_widget.item(row).setText(self._render_child_label(updated.raw))

    def _child_remove(self, step_type: StepType) -> None:
        """删除当前选中的子步骤。"""
        list_widget = self.child_lists[step_type]
        row = list_widget.currentRow()
        if row < 0:
            return
        del self.child_data[step_type][row]
        list_widget.takeItem(row)

    def _child_move(self, step_type: StepType, direction: int) -> None:
        """上移 / 下移当前选中的子步骤。"""
        list_widget = self.child_lists[step_type]
        row = list_widget.currentRow()
        target = row + direction
        steps = self.child_data[step_type]
        if row < 0 or target < 0 or target >= len(steps):
            return
        steps[row], steps[target] = steps[target], steps[row]
        list_widget.item(row).setText(self._render_child_label(steps[row]))
        list_widget.item(target).setText(self._render_child_label(steps[target]))
        list_widget.setCurrentRow(target)

    # ------------------------------------------------------------------
    # 类型切换 / 校验
    # ------------------------------------------------------------------

    def _sync_type_page(self) -> None:
        """切换上方下拉框时，让 stack 显示对应步骤的表单页。"""
        step_type = self.type_combo.currentData()
        if step_type is None:
            return
        self.stack.setCurrentIndex(self._page_index_by_type[step_type])

    def _validation_error(self) -> str:
        """返回第一条校验失败的提示文本；返回空串表示通过。"""
        step_type: StepType = self.type_combo.currentData()
        if step_type is None:
            return "请选择步骤类型。"
        sch = schema(step_type)
        for f in sch.fields:
            if not f.required or not f.key:
                continue
            widget = self.widgets[step_type].get(f.key)
            if widget is None:
                continue
            value = self._read_widget(widget, f)
            if not value and value != 0:
                return f"{f.label} 不能为空。"

        # 循环步骤需要至少一个子步骤，且必须给出选择器或列表项。
        if step_type == StepType.FOR_EACH:
            if not self.child_data.get(step_type):
                return "循环步骤至少需要一个子步骤。"
            sel = self._read_widget(self.widgets[step_type]["selector"],
                                    FormField("selector", "", "text"))
            items = self._read_widget(self.widgets[step_type]["items"],
                                      FormField("items", "", "multiline"))
            if not sel and not items:
                return "循环步骤需要填写选择器或列表项之一。"

        return ""
