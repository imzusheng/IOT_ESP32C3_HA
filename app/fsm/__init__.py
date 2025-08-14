# app/fsm/__init__.py
"""
函数式状态机模块
基于函数和字典查找的简化状态机架构, 解决事件风暴问题
"""

# 从core模块导入核心状态机类和工厂函数
from .core import FunctionalStateMachine, StateMachine, create_state_machine, get_state_machine


# 从state_const模块导入状态常量和工具函数（合并后）
from .state_const import (
    STATE_BOOT, STATE_INIT, STATE_NETWORKING, STATE_RUNNING,
    STATE_WARNING, STATE_ERROR, STATE_SAFE_MODE, STATE_RECOVERY, STATE_SHUTDOWN,
    STATE_NAMES, get_state_name, get_all_states as get_all_state_ids
)

# __all__定义了这个包可以被外部导入的内容
__all__ = [
    # 核心状态机类
    'FunctionalStateMachine',
    'StateMachine',  # 别名, 保持兼容性
    
    # 工厂函数
    'create_state_machine',
    'get_state_machine',
    
    # 兼容性状态常量
    
    # 新的状态常量
    'STATE_BOOT', 'STATE_INIT', 'STATE_NETWORKING', 'STATE_RUNNING',
    'STATE_WARNING', 'STATE_ERROR', 'STATE_SAFE_MODE', 'STATE_RECOVERY', 'STATE_SHUTDOWN',
    
    # 工具函数
    'STATE_NAMES',
    'get_state_name',
    'get_all_state_ids'
]