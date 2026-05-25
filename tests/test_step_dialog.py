"""Tests for the data-driven step dialog.

These exercise the schema mapping and the form-field round-tripping
without actually instantiating Qt widgets (which requires a QApplication
and a display). Round-trip tests use real Qt widgets behind a shared
QApplication fixture.
"""

from __future__ import annotations

import os
import sys

import pytest

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.ui.step_schemas import SCHEMAS, schema


# --- Schema completeness -----------------------------------------------


def test_every_step_type_has_a_schema() -> None:
    missing = [t for t in StepType if t not in SCHEMAS]
    assert missing == [], f"缺失 schema: {missing}"


def test_required_fields_match_handler_required_fields() -> None:
    """Schema 'required' flags should be a superset of handler required_fields()
    for text-type fields. (Numeric fields always have a default value so
    'required' is a no-op for SpinBoxes.)
    """
    from rpa_helper.core.step_handlers import get_handler

    numeric_kinds = {"int", "float", "bool", "child_steps"}
    for step_type in StepType:
        sch = schema(step_type)
        kind_by_key = {f.key: f.kind for f in sch.fields if f.key}
        handler_required = set(get_handler(step_type).required_fields())
        # Only require schema flags on text-type fields.
        text_required = {k for k in handler_required
                         if kind_by_key.get(k) not in numeric_kinds}
        schema_required = {f.key for f in sch.fields if f.required and f.key}
        missing = text_required - schema_required
        assert not missing, (
            f"{step_type.value}: handler text-requires {text_required}, schema marks {schema_required}"
        )


def test_for_each_schema_has_child_steps_field() -> None:
    sch = schema(StepType.FOR_EACH)
    assert any(f.kind == "child_steps" for f in sch.fields)


def test_browser_schemas_have_browser_category() -> None:
    browser_types = [
        StepType.BROWSER_OPEN, StepType.BROWSER_CLOSE, StepType.BROWSER_CLICK,
        StepType.BROWSER_INPUT, StepType.BROWSER_WAIT_FOR, StepType.BROWSER_EXTRACT,
        StepType.BROWSER_DOWNLOAD, StepType.BROWSER_GO_BACK,
    ]
    for t in browser_types:
        assert schema(t).category == "浏览器自动化", f"{t.value} 类别不对"


# --- Round-trip through StepDialog -------------------------------------

# Skip Qt tests when display is not available (e.g. CI without xvfb).
QT_AVAILABLE = True
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QT_AVAILABLE = False


@pytest.fixture(scope="module")
def qapp():
    if not QT_AVAILABLE:
        pytest.skip("PyQt6 unavailable")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_roundtrip_browser_click(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    original = WorkflowStep(
        type=StepType.BROWSER_CLICK,
        name="click submit",
        raw={
            "type": "browser_click",
            "name": "click submit",
            "selector": "button.submit",
            "timeout": 15,
        },
    )
    dialog = StepDialog(step=original)
    out = dialog.to_step()
    assert out.type == StepType.BROWSER_CLICK
    assert out.name == "click submit"
    assert out.raw["selector"] == "button.submit"
    assert out.raw["timeout"] == 15


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_roundtrip_browser_extract_with_attribute(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    original = WorkflowStep(
        type=StepType.BROWSER_EXTRACT,
        name="get id",
        raw={
            "type": "browser_extract",
            "name": "get id",
            "selector": ".order-id",
            "save_as": "order_id",
            "attribute": "data-value",
        },
    )
    dialog = StepDialog(step=original)
    out = dialog.to_step()
    assert out.raw["selector"] == ".order-id"
    assert out.raw["save_as"] == "order_id"
    assert out.raw["attribute"] == "data-value"


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_roundtrip_for_each_with_children(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    original = WorkflowStep(
        type=StepType.FOR_EACH,
        name="loop rows",
        raw={
            "type": "for_each",
            "name": "loop rows",
            "selector": "table tr",
            "as": "row",
            "limit": 10,
            "steps": [
                {"type": "browser_click", "name": "click row",
                 "selector": ".row-{{row}}", "timeout": 5},
                {"type": "wait", "name": "pause", "seconds": 1.0},
            ],
        },
    )
    dialog = StepDialog(step=original)
    out = dialog.to_step()
    assert out.raw["selector"] == "table tr"
    assert out.raw["as"] == "row"
    assert out.raw["limit"] == 10
    assert len(out.raw["steps"]) == 2
    assert out.raw["steps"][0]["selector"] == ".row-{{row}}"
    assert out.raw["steps"][1]["seconds"] == 1.0


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_roundtrip_for_each_with_items_list(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    original = WorkflowStep(
        type=StepType.FOR_EACH,
        name="iter ids",
        raw={
            "type": "for_each",
            "name": "iter ids",
            "items": ["A001", "A002", "A003"],
            "as": "order_id",
            "steps": [
                {"type": "browser_click", "selector": ".btn"},
            ],
        },
    )
    dialog = StepDialog(step=original)
    out = dialog.to_step()
    # items in multiline widget come back as a list of strings.
    assert out.raw["items"] == ["A001", "A002", "A003"]
    assert out.raw["as"] == "order_id"


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_roundtrip_browser_open_defaults(qapp) -> None:
    """New browser_open with no step provided uses field defaults."""
    from rpa_helper.ui.step_dialog import StepDialog

    dialog = StepDialog()
    # User selects browser_open in the type combo.
    idx = dialog.type_combo.findData(StepType.BROWSER_OPEN)
    assert idx >= 0
    dialog.type_combo.setCurrentIndex(idx)
    # Fill URL and accept.
    dialog.widgets[StepType.BROWSER_OPEN]["url"].setText("https://example.com")
    out = dialog.to_step()
    assert out.type == StepType.BROWSER_OPEN
    assert out.raw["url"] == "https://example.com"
    assert out.raw["headless"] is False  # default


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_validation_blocks_missing_required(qapp) -> None:
    """browser_click without a selector must fail validation."""
    from rpa_helper.ui.step_dialog import StepDialog

    dialog = StepDialog()
    idx = dialog.type_combo.findData(StepType.BROWSER_CLICK)
    dialog.type_combo.setCurrentIndex(idx)
    # Leave selector empty.
    err = dialog._validation_error()
    assert "CSS 选择器" in err or "selector" in err.lower()


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_validation_for_each_needs_children(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    dialog = StepDialog()
    idx = dialog.type_combo.findData(StepType.FOR_EACH)
    dialog.type_combo.setCurrentIndex(idx)
    dialog.widgets[StepType.FOR_EACH]["selector"].setText(".item")
    err = dialog._validation_error()
    assert "子步骤" in err


@pytest.mark.skipif(not QT_AVAILABLE, reason="PyQt6 required")
def test_validation_for_each_needs_selector_or_items(qapp) -> None:
    from rpa_helper.ui.step_dialog import StepDialog

    dialog = StepDialog()
    idx = dialog.type_combo.findData(StepType.FOR_EACH)
    dialog.type_combo.setCurrentIndex(idx)
    # Add a fake child so the no-children check passes.
    dialog.child_data[StepType.FOR_EACH].append(
        {"type": "wait", "name": "w", "seconds": 1}
    )
    err = dialog._validation_error()
    assert "选择器" in err or "列表项" in err
