"""config/ 目录下 YAML 流程文件的发现与生命周期管理。

不依赖 Qt，便于单元测试。UI 端把 list_files() 的结果绑定到下拉框，
把 create_blank / duplicate / delete 绑定到按钮。

Author: huaiqing.wang
"""

from __future__ import annotations

from pathlib import Path

from rpa_helper.core.workflow_loader import load_workflow
from rpa_helper.core.workflow_writer import save_workflow


# 合法的流程文件后缀。
VALID_SUFFIXES = {".yaml", ".yml"}


class WorkflowStore:
    """封装 config/ 目录里的流程文件操作。"""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def list_files(self) -> list[Path]:
        """按文件名排序列出所有流程文件。"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        return sorted(
            p for p in self.config_dir.iterdir()
            if p.suffix.lower() in VALID_SUFFIXES
        )

    def display_name(self, path: Path) -> str:
        """读 YAML 拿 name 字段；失败时回退到文件名 stem。"""
        try:
            workflow = load_workflow(path)
            return workflow.name
        except Exception:
            return path.stem

    def create_blank(self, name: str) -> Path:
        """新建一份完全空白的流程（steps 为空），用户进入编辑器再添加。"""
        safe = self._normalize_filename(name)
        if not safe:
            raise ValueError("文件名无效")
        target = self.config_dir / safe
        if target.exists():
            raise FileExistsError(f"文件已存在: {target.name}")

        # 这里不引用 Workflow 数据类，因为它要求 steps 非空——直接写入 YAML。
        import yaml as _yaml
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as file:
            _yaml.safe_dump(
                {"name": Path(safe).stem, "steps": []},
                file,
                allow_unicode=True,
                sort_keys=False,
            )
        return target

    def duplicate(self, source: Path, new_name: str) -> Path:
        """把 source 流程复制到新文件，并以新文件名作为流程名。"""
        if not source.exists():
            raise FileNotFoundError(f"源流程不存在: {source}")
        safe = self._normalize_filename(new_name)
        if not safe:
            raise ValueError("文件名无效")
        target = self.config_dir / safe
        if target.exists():
            raise FileExistsError(f"文件已存在: {target.name}")

        workflow = load_workflow(source)
        # 让 workflow.name 与新文件名一致，下拉框显示才直观。
        workflow.name = Path(safe).stem
        save_workflow(target, workflow)
        return target

    def delete(self, path: Path) -> None:
        """删除流程文件，并拒绝越界路径。"""
        resolved = path.resolve()
        if not str(resolved).startswith(str(self.config_dir.resolve())):
            raise ValueError(f"拒绝删除 config 目录之外的文件: {resolved}")
        resolved.unlink(missing_ok=True)

    @staticmethod
    def _normalize_filename(name: str) -> str:
        """把用户输入的流程名转成安全的文件名；非法返回空串。"""
        if not name:
            return ""
        stem = Path(name.strip()).name
        if not stem:
            return ""
        # 没带 .yaml/.yml 后缀时自动补上。
        if Path(stem).suffix.lower() not in VALID_SUFFIXES:
            stem = f"{Path(stem).stem}.yaml"
        invalid = set('<>:"/\\|?*')
        if any(c in invalid for c in Path(stem).stem):
            return ""
        return stem
