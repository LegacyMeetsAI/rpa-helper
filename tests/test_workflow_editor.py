from __future__ import annotations

import pytest

from rpa_helper.core.models import StepType, Workflow, WorkflowStep
from rpa_helper.ui.controllers.workflow_editor import WorkflowEditor


def _step(name: str) -> WorkflowStep:
    return WorkflowStep(type=StepType.WAIT, name=name, raw={"seconds": 1})


@pytest.fixture
def editor() -> WorkflowEditor:
    wf = Workflow(name="t", steps=[_step("a"), _step("b"), _step("c")])
    return WorkflowEditor(wf)


def test_add_appends(editor: WorkflowEditor) -> None:
    editor.add(_step("d"))
    assert [s.name for s in editor.workflow.steps] == ["a", "b", "c", "d"]


def test_replace_changes_in_place(editor: WorkflowEditor) -> None:
    editor.replace(1, _step("B"))
    assert [s.name for s in editor.workflow.steps] == ["a", "B", "c"]


def test_replace_out_of_range_raises(editor: WorkflowEditor) -> None:
    with pytest.raises(IndexError):
        editor.replace(99, _step("x"))


def test_delete_returns_step(editor: WorkflowEditor) -> None:
    deleted = editor.delete(1)
    assert deleted.name == "b"
    assert [s.name for s in editor.workflow.steps] == ["a", "c"]


def test_clear_empties_list(editor: WorkflowEditor) -> None:
    editor.clear()
    assert editor.workflow.steps == []


def test_move_up(editor: WorkflowEditor) -> None:
    new_index = editor.move(2, -1)
    assert new_index == 1
    assert [s.name for s in editor.workflow.steps] == ["a", "c", "b"]


def test_move_down(editor: WorkflowEditor) -> None:
    new_index = editor.move(0, 1)
    assert new_index == 1
    assert [s.name for s in editor.workflow.steps] == ["b", "a", "c"]


def test_move_at_boundary_returns_same_index(editor: WorkflowEditor) -> None:
    assert editor.move(0, -1) == 0
    assert editor.move(2, 1) == 2
    assert [s.name for s in editor.workflow.steps] == ["a", "b", "c"]


def test_extend_appends_multiple(editor: WorkflowEditor) -> None:
    editor.extend([_step("d"), _step("e")])
    assert [s.name for s in editor.workflow.steps] == ["a", "b", "c", "d", "e"]
