# -*- coding: utf-8 -*-
# app/utils/__init__.py
"""
工具函数库
- 聚合常用工具入口, 便于對外 import 簡化
- JSON 序列化與時間戳工具已拆分至子模塊 json_utils 與 time_utils
"""

from .timers import get_hardware_timer_manager
from .json_utils import json_dumps
from .time_utils import get_epoch_unix_s

# ===== 通用工具函數: 內存與溫度 =====

def check_memory():
    """檢查內存狀況
    返回 dict: { free_kb, total_kb, used_kb, percent }
    - 在部分端口上 mem_alloc 不可用時做降級
    """
    try:
        import gc
        free_kb = gc.mem_free() // 1024
        total_kb = (gc.mem_free() + gc.mem_alloc()) // 1024
        used_kb = total_kb - free_kb
        percent = (used_kb / total_kb * 100.0) if total_kb > 0 else 0
        return {
            "free_kb": free_kb,
            "total_kb": total_kb,
            "used_kb": used_kb,
            "percent": percent,
        }
    except Exception:
        try:
            import gc
            return {
                "free_kb": gc.mem_free() // 1024,
                "total_kb": None,
                "used_kb": None,
                "percent": 0,
            }
        except Exception:
            return {"free_kb": 0, "total_kb": None, "used_kb": None, "percent": 0}


def get_temperature():
    """讀取 MCU 內部溫度, 如不支持則返回 None"""
    try:
        import esp32
        if hasattr(esp32, "mcu_temperature"):
            return esp32.mcu_temperature()
    except Exception:
        pass
    return None

__all__ = [
    "get_hardware_timer_manager",
    "json_dumps",
    "check_memory",
    "get_temperature",
    "get_epoch_unix_s",
]
