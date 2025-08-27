# -*- coding: utf-8 -*-
# app/utils/time_utils.py
"""
时间工具
- 提供将 MicroPython 的基于 2000 年的 time.time() 转为 1970-based UNIX 秒
"""

def get_epoch_unix_s(t=None):
    """将 MicroPython 的 time.time() 值转换为 1970-based UNIX 秒
    - 若 t 为 None, 则读取当前 time.time()
    - 多數 MicroPython 端口的 time.time() 基於 2000-01-01, 需加上 946684800 偏移
    - 若底层已为 1970-based(> 946684800), 则直接返回
    """
    try:
        import utime as time
        val = int(time.time()) if t is None else int(t)
        return val if val >= 946684800 else (val + 946684800)
    except Exception:
        return None

__all__ = ["get_epoch_unix_s"]