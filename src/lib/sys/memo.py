# -*- coding: utf-8 -*-
"""
MicroPython 高效内存优化模块 Memory Optimization (v2.2)

为资源受限的 MicroPython 设备 (如 ESP32-C3) 提供一套事件驱动的内存优化方案。
核心目标是通过对象池和静态缓存，在不引入运行时开销的前提下，最大程度地减少
内存碎片和垃圾回收的压力。
"""

import gc
from micropython import const

# --- 模块常量定义 ---
_DICT_POOL_INITIAL_SIZE = const(10)
_STRING_CACHE_MAX_SIZE = const(50)
_BUFFER_POOL_SIZE_PER_TYPE = const(3)
_BUFFER_SIZES = (64, 128, 256, 512, 1024)

_MEM_WARN_THRESHOLD = const(80)    # 80% 内存使用警告
_MEM_CRIT_THRESHOLD = const(90)    # 90% 内存使用严重
_MEM_EMERG_THRESHOLD = const(95)   # 95% 内存使用紧急

# =============================================================================
# 内存监控与优化器 (被动触发)
# =============================================================================
class MemoryOptimizer:
    """
    内存优化器 - 在内存压力下被动触发，执行分级清理策略。
    """
    def __init__(self):
        """初始化内存优化器，设定清理阈值。"""
        self._thresholds = {
            'warning': _MEM_WARN_THRESHOLD,
            'critical': _MEM_CRIT_THRESHOLD,
            'emergency': _MEM_EMERG_THRESHOLD
        }

    def run_cleanup_if_needed(self):
        """
        检查当前内存使用率。如果超过阈值，则运行相应的清理程序。
        """
        try:
            total_memory = gc.mem_alloc() + gc.mem_free()
            if total_memory == 0: return

            used_percent = (gc.mem_alloc() / total_memory) * 100

            if used_percent >= self._thresholds['emergency']:
                self._emergency_cleanup()
            elif used_percent >= self._thresholds['critical']:
                self._critical_cleanup()
            elif used_percent >= self._thresholds['warning']:
                self._warning_cleanup()

        except Exception as e:
            print(f"[MemOpt] CRITICAL ERROR: 内存检查或清理时发生异常: {e}")

    def _emergency_cleanup(self):
        """紧急内存清理：深度GC并清空所有池。"""
        clear_all_pools()
        gc.collect()
        gc.collect()

    def _critical_cleanup(self):
        """严重内存清理：多次GC并重置字符串缓存统计。"""
        gc.collect()
        _string_cache.reset_stats()
        gc.collect()

    def _warning_cleanup(self):
        """警告内存清理：执行一次标准的垃圾回收。"""
        gc.collect()

# =============================================================================
# 对象池和缓存类
# =============================================================================

class DictPool:
    """
    字典对象池 - 预分配字典对象以避免运行时开销。
    """
    def __init__(self, pool_size=_DICT_POOL_INITIAL_SIZE):
        self._pool_size = pool_size
        self._pool = [{} for _ in range(pool_size)]
        self._in_use = set()

    def get_dict(self):
        """从池中获取一个字典。如果池为空，则尝试创建新字典。失败返回 None。"""
        if self._pool:
            dict_obj = self._pool.pop()
            self._in_use.add(id(dict_obj))
            return dict_obj
        else:
            _memory_optimizer.run_cleanup_if_needed()
            try:
                new_dict = {}
                self._in_use.add(id(new_dict))
                return new_dict
            except MemoryError:
                print("[MemOpt] CRITICAL ERROR: DictPool failed to allocate new dict.")
                return None

    def return_dict(self, dict_obj):
        """将使用完毕的字典归还到池中。"""
        if dict_obj is None: return
        dict_id = id(dict_obj)
        if dict_id in self._in_use:
            dict_obj.clear()
            self._in_use.remove(dict_id)
            if len(self._pool) < self._pool_size:
                self._pool.append(dict_obj)

    def clear_pool(self):
        """清空池。"""
        self._pool.clear()
        self._in_use.clear()

    def get_stats(self):
        return {'available': len(self._pool), 'in_use': len(self._in_use)}


class StringCache:
    """
    静态字符串缓存 - 作为只读的字符串常量池。
    """
    def __init__(self, max_size=_STRING_CACHE_MAX_SIZE):
        self._cache = {}
        self._access_count = {}
        self._precache_common_strings()

    def _precache_common_strings(self):
        # ... (内容不变)
        common_strings = [
            'active', 'inactive', 'enabled', 'disabled', 'normal', 'warning', 'error',
            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
            'connected', 'disconnected', 'connecting',
            'free', 'used', 'total', 'percent',
            'timestamp', 'duration',
            'NETWORK_ERROR', 'HARDWARE_ERROR', 'MEMORY_ERROR',
            'Main', 'MQTT', 'WiFi', 'Sensor'
        ]
        for string in common_strings:
            self._cache[string] = string
            self._access_count[string] = 0

    def get_string(self, string_value):
        """获取字符串。若在预缓存中则返回实例，否则返回原值。"""
        if string_value in self._cache:
            self._access_count[string_value] += 1
            return self._cache[string_value]
        return string_value

    def reset_stats(self):
        """重置访问统计信息，但保留预缓存的字符串。"""
        for key in self._access_count:
            self._access_count[key] = 0

    def get_stats(self):
        return {'size': len(self._cache), 'total_hits': sum(self._access_count.values())}


class BufferManager:
    """预分配缓冲区管理器。"""
    def __init__(self):
        self._buffers = {size: [] for size in _BUFFER_SIZES}
        for size in _BUFFER_SIZES:
            for _ in range(_BUFFER_POOL_SIZE_PER_TYPE):
                self._buffers[size].append(bytearray(size))

    def get_buffer(self, size):
        """获取缓冲区。若池空，则尝试创建。失败返回 None。"""
        suitable_size = self._find_suitable_size(size)
        if self._buffers.get(suitable_size) and self._buffers[suitable_size]:
            return self._buffers[suitable_size].pop()
        else:
            if suitable_size not in self._buffers:
                self._buffers[suitable_size] = []
            
            _memory_optimizer.run_cleanup_if_needed()
            try:
                return bytearray(suitable_size)
            except MemoryError:
                print(f"[MemOpt] CRITICAL ERROR: BufferManager failed to allocate {suitable_size} bytes.")
                return None

    def _find_suitable_size(self, size):
        # ... (内容不变)
        for buffer_size in _BUFFER_SIZES:
            if size <= buffer_size:
                return buffer_size
        return size

    def return_buffer(self, buffer):
        """归还缓冲区。"""
        if buffer is None: return
        buffer_size = len(buffer)
        if buffer_size in self._buffers:
            # 清零缓冲区以策安全
            for i in range(buffer_size):
                buffer[i] = 0
            
            if len(self._buffers[buffer_size]) < _BUFFER_POOL_SIZE_PER_TYPE:
                self._buffers[buffer_size].append(buffer)

    def clear_all_buffers(self):
        for size in self._buffers:
            self._buffers[size].clear()

    def get_stats(self):
        return {size: len(pool) for size, pool in self._buffers.items()}

# =============================================================================
# 全局实例和公共接口
# =============================================================================

_memory_optimizer = MemoryOptimizer()
_dict_pool = DictPool()
_string_cache = StringCache()
_buffer_manager = BufferManager()

# --- 公共便捷函数 ---
def get_dict(): return _dict_pool.get_dict()
def return_dict(dict_obj): _dict_pool.return_dict(dict_obj)
def get_string(string_value): return _string_cache.get_string(string_value)
def get_buffer(size): return _buffer_manager.get_buffer(size)
def return_buffer(buffer): _buffer_manager.return_buffer(buffer)

def get_all_stats():
    return {
        'dict_pool': _dict_pool.get_stats(),
        'string_cache': _string_cache.get_stats(),
        'buffer_manager': _buffer_manager.get_stats()
    }

def clear_all_pools():
    """清空所有对象池和缓冲区，但不执行GC。"""
    _dict_pool.clear_pool()
    _string_cache.reset_stats()
    _buffer_manager.clear_all_buffers()

# =============================================================================
# 初始化
# =============================================================================
gc.collect()