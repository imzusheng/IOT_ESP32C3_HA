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

# 兼容性文件系统模块
try:
    import uos as _os
except Exception:
    try:
        import os as _os
    except Exception:
        _os = None

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

# 追加: 轻量文件读写与原子写入

def load_json_file(path, default=None):
    """从文件读取 JSON 内容, 失败返回 default"""
    if default is None:
        default = {}
    try:
        with open(path, "r") as f:
            s = f.read()
        if _json is not None:
            try:
                return _json.loads(s)
            except Exception:
                pass
        try:
            import json as std_json
            return std_json.loads(s)
        except Exception:
            return default
    except Exception:
        return default

def json_dump_to_file(path, data):
    """将对象写入文件(JSON), 尽力而为模式"""
    try:
        s = json_dumps(data)
        with open(path, "w") as f:
            f.write(s)
            try:
                f.flush()
            except Exception:
                pass
        return True
    except Exception:
        return False

def atomic_write_json(path, data, tmp_suffix=".tmp"):
    """原子写入 JSON 文件: 写入到临时文件后重命名覆盖
    注意: 在部分文件系统上 rename 是原子的, 若不支持, 也尽力而为。
    """
    if _os is None:
        # 无文件系统模块, 回退为普通写
        return json_dump_to_file(path, data)
    tmp_path = path + tmp_suffix
    try:
        # 先写入临时文件
        s = json_dumps(data)
        with open(tmp_path, "w") as f:
            f.write(s)
            try:
                f.flush()
            except Exception:
                pass
        # 重命名覆盖
        try:
            _os.rename(tmp_path, path)
        except Exception:
            # 某些实现使用 replace
            try:
                replace = getattr(_os, "replace", None)
                if replace:
                    replace(tmp_path, path)
                else:
                    # 无法替换则回退为直接写
                    return json_dump_to_file(path, data)
            except Exception:
                return False
        return True
    except Exception:
        # 清理临时文件(尽力而为)
        try:
            if _os and hasattr(_os, "remove"):
                _os.remove(tmp_path)
        except Exception:
            pass
        return False

__all__ = ["json_dumps", "load_json_file", "json_dump_to_file", "atomic_write_json"]