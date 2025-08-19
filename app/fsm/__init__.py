# app/fsm/__init__.py
"""
状态机模块导出
- 与当前实现对齐：仅导出 core.py 中存在的接口
- 兼容性：提供 create_state_machine/get_state_machine 工厂与全局访问
"""

from .core import (
    FSM,
    create_state_machine,
    get_state_machine,
)

__all__ = [
    "FSM",
    "create_state_machine",
    "get_state_machine",
]
