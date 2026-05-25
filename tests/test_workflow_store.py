"""WorkflowStore 单元测试。

Author: huaiqing.wang
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rpa_helper.ui.controllers.workflow_store import WorkflowStore


def _write_workflow(path: Path, name: str = "wf") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "steps": [{"type": "wait", "seconds": 1}]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def store(tmp_path: Path) -> WorkflowStore:
    return WorkflowStore(tmp_path / "config")


def test_list_empty(store: WorkflowStore) -> None:
    assert store.list_files() == []


def test_list_alphabetical(store: WorkflowStore) -> None:
    _write_workflow(store.config_dir / "zzz.yaml", "z")
    _write_workflow(store.config_dir / "alpha.yaml", "a")

    files = store.list_files()
    assert [p.name for p in files] == ["alpha.yaml", "zzz.yaml"]


def test_list_filters_non_yaml(store: WorkflowStore) -> None:
    store.config_dir.mkdir(parents=True)
    _write_workflow(store.config_dir / "a.yaml", "a")
    (store.config_dir / "notes.txt").write_text("hi")
    files = store.list_files()
    assert [p.name for p in files] == ["a.yaml"]


def test_display_name_uses_workflow_name(store: WorkflowStore) -> None:
    path = store.config_dir / "x.yaml"
    _write_workflow(path, "门诊每日导出")
    assert store.display_name(path) == "门诊每日导出"


def test_display_name_falls_back_to_stem_on_error(store: WorkflowStore) -> None:
    bad = store.config_dir / "broken.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("not: a: workflow\n  - bad\n", encoding="utf-8")
    assert store.display_name(bad) == "broken"


def test_create_blank_writes_yaml_with_empty_steps(store: WorkflowStore) -> None:
    path = store.create_blank("new_flow")
    assert path.exists()
    assert path.suffix == ".yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["name"] == "new_flow"
    assert data["steps"] == []


def test_create_blank_rejects_duplicate(store: WorkflowStore) -> None:
    store.create_blank("x")
    with pytest.raises(FileExistsError):
        store.create_blank("x")


def test_create_blank_normalizes_filename(store: WorkflowStore) -> None:
    path = store.create_blank("门诊流程")
    assert path.suffix == ".yaml"


def test_create_blank_empty_rejected(store: WorkflowStore) -> None:
    with pytest.raises(ValueError):
        store.create_blank("")


def test_duplicate_preserves_steps(store: WorkflowStore) -> None:
    source = store.config_dir / "src.yaml"
    _write_workflow(source, "原")
    new_path = store.duplicate(source, "copy.yaml")
    text = new_path.read_text(encoding="utf-8")
    assert "wait" in text
    assert "copy" in new_path.stem


def test_duplicate_rejects_when_target_exists(store: WorkflowStore) -> None:
    source = store.config_dir / "src.yaml"
    _write_workflow(source, "a")
    _write_workflow(store.config_dir / "copy.yaml", "b")
    with pytest.raises(FileExistsError):
        store.duplicate(source, "copy.yaml")


def test_delete_removes_file(store: WorkflowStore) -> None:
    extra = store.config_dir / "extra.yaml"
    _write_workflow(extra, "x")
    store.delete(extra)
    assert not extra.exists()


def test_delete_refuses_outside_config(tmp_path: Path, store: WorkflowStore) -> None:
    outside = tmp_path / "outside.yaml"
    _write_workflow(outside, "o")
    with pytest.raises(ValueError):
        store.delete(outside)
    assert outside.exists()
