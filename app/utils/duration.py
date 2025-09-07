# -*- coding: utf-8 -*-
# app/utils/duration.py
"""
时长格式化工具（中文友好显示）
- 依据毫秒值自动选择合适的单位并格式化为中文字符串。
- 规则：
  - < 1000 ms -> "X ms"
  - < 60 s -> "X 秒"（取整）
  - < 60 分钟 -> "Y 分钟"（<10 分钟保留1位小数，否则取整）
  - 其他 -> "Z 小时"（保留1位小数）
"""

def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return default


def format_duration_ms(ms) -> str:
    """将毫秒值格式化为中文字符串（带单位）。
    - None 或 非法输入返回 "N/A"
    """
    try:
        if ms is None:
            return "N/A"
        val = _safe_int(ms, -1)
        if val < 0:
            return "N/A"

        if val < 1000:
            return f"{val} ms"
        if val < 60000:
            sec = int(round(val / 1000.0))
            return f"{sec} 秒"
        if val < 3600000:
            minutes = val / 60000.0
            # <10 分钟：保留1位小数，但避免显示 1.0/2.0 这类
            if minutes < 10:
                m = round(minutes, 1)
                # 若近似为整数，则转为整数显示
                if abs(m - int(m)) < 0.05:
                    m = int(m)
            else:
                m = int(round(minutes))
            return f"{m} 分钟"
        hours = round(val / 3600000.0, 1)
        return f"{hours} 小时"
    except Exception:
        return "N/A"


__all__ = ["format_duration_ms"]
