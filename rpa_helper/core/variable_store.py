"""运行时变量存储。

browser_extract 把页面文本写入这里，后续步骤通过 {{var}} 占位符读取；
for_each 在循环开始前 push 一层作用域，让 {{item}} 等迭代变量只在
子步骤内可见，循环结束后自动出栈。

Author: huaiqing.wang
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


class VariableStore:
    """带作用域栈的变量字典。"""

    def __init__(self) -> None:
        # 最底层是全局作用域，for_each 会在其上再压一层。
        self._scopes: list[dict[str, str]] = [{}]

    def set(self, name: str, value: str) -> None:
        """写入当前最顶层作用域。"""
        self._scopes[-1][name] = value

    def get(self, name: str, default: str = "") -> str:
        """从最内层往外查找；命中即返回。"""
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return default

    def has(self, name: str) -> bool:
        """变量是否存在于任意作用域中。"""
        return any(name in s for s in self._scopes)

    def as_dict(self) -> dict[str, str]:
        """把所有作用域合并成一个 dict（内层覆盖外层），用于调试展示。"""
        merged: dict[str, str] = {}
        for scope in self._scopes:
            merged.update(scope)
        return merged

    @contextmanager
    def scope(self, **initial: str) -> Iterator[None]:
        """临时压入一层子作用域，with 块结束后自动弹出。

        for_each 用它来确保循环变量不会泄漏到循环外。
        """
        self._scopes.append(dict(initial))
        try:
            yield
        finally:
            self._scopes.pop()
