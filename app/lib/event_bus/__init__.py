# app/lib/event_bus/__init__.py
"""
事件总线模块
提供发布-订阅模式的异步非阻塞事件处理
"""

# 从core模块导入EventBus类,这是事件总线的核心实现
from .core import EventBus

# 从events_const模块导入事件常量EVENTS和相关函数
from .events_const import (
    EVENTS, 
    get_all_events, 
    validate_event_count
)

# __all__定义了这个包可以被外部导入的内容
# 包括:
# - EventBus: 事件总线类
# - EVENTS: 事件常量类，包含所有18个原有事件
# - get_all_events: 获取所有事件的函数
# - validate_event_count: 验证事件数量的函数
__all__ = [
    'EventBus', 
    'EVENTS', 
    'get_all_events', 
    'validate_event_count'
]