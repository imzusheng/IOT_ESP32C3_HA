# app/fsm/__init__.py
"""
状态机模块导出
- 与当前实现对齐：仅导出 core.py 中存在的接口
"""

from .core import (
    FSM,
)

__all__ = [
    "FSM",
]
