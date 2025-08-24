# -*- coding: utf-8 -*-
# app/utils/time_utils.py
"""
時間工具
- 提供將 MicroPython 的基於 2000 年的 time.time() 轉為 1970-based UNIX 秒
"""

def get_epoch_unix_s(t=None):
    """將 MicroPython 的 time.time() 值轉換為 1970-based UNIX 秒
    - 若 t 為 None, 則讀取當前 time.time()
    - 多數 MicroPython 端口的 time.time() 基於 2000-01-01, 需加上 946684800 偏移
    - 若底層已為 1970-based(> 946684800), 則直接返回
    """
    try:
        import utime as time
        val = int(time.time()) if t is None else int(t)
        return val if val >= 946684800 else (val + 946684800)
    except Exception:
        return None

__all__ = ["get_epoch_unix_s"]