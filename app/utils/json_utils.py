# -*- coding: utf-8 -*-
# app/utils/json_utils.py
"""
JSON 序列化工具
- 优先使用 ujson
- 回退标准 json
- 最終兜底 str(data)
"""

# 轻量 JSON 序列化工具
try:
    import ujson as _json
except Exception:
    try:
        import json as _json
    except Exception:
        _json = None

def json_dumps(data):
    """将 Python 数据序列化为 JSON 字符串"""
    if _json is not None:
        try:
            return _json.dumps(data)
        except Exception:
            pass
    try:
        import json as std_json
        return std_json.dumps(data)
    except Exception:
        pass
    try:
        return str(data)
    except Exception:
        return "{}"

__all__ = ["json_dumps"]