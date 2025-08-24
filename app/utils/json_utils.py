# -*- coding: utf-8 -*-
# app/utils/json_utils.py
"""
JSON 序列化工具
- 優先使用 ujson 確保體積與性能
- 回退標準 json
- 最終兜底 str(data)
"""

# 輕量 JSON 序列化工具
try:
    import ujson as _json
except Exception:
    try:
        import json as _json
    except Exception:
        _json = None

def json_dumps(data):
    """將 Python 數據序列化為 JSON 字符串"""
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