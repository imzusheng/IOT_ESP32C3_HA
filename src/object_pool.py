# -*- coding: utf-8 -*-
"""
对象池和缓存优化模块

为ESP32C3设备提供高效的对象池和缓存管理，减少内存分配和垃圾回收开销：
- 字典对象池管理
- 字符串缓存优化
- 预分配缓冲区管理
- 内存友好的数据结构

内存优化说明：
- 避免频繁创建销毁对象
- 重用预分配的内存空间
- 减少垃圾回收压力
- 提高系统响应性
"""

import gc
import time

# =============================================================================
# 字典对象池类
# =============================================================================

class DictPool:
    """字典对象池 - 避免频繁创建销毁字典对象"""
    
    def __init__(self, pool_size=5):
        """
        初始化字典对象池
        
        Args:
            pool_size: 池大小，默认5个字典
        """
        self._pool = []
        self._pool_size = pool_size
        self._in_use = []
        
        # 预分配字典对象
        for _ in range(pool_size):
            self._pool.append({})
        
        print(f"[DictPool] 字典对象池初始化完成，池大小: {pool_size}")
    
    def get_dict(self):
        """从池中获取字典对象"""
        if self._pool:
            dict_obj = self._pool.pop()
            self._in_use.append(dict_obj)
            return dict_obj
        else:
            # 池为空时创建新对象（但记录警告）
            print(f"[DictPool] 警告：对象池已空，创建新字典")
            new_dict = {}
            self._in_use.append(new_dict)
            return new_dict
    
    def return_dict(self, dict_obj):
        """归还字典对象到池中"""
        if dict_obj in self._in_use:
            # 清空字典内容
            dict_obj.clear()
            self._in_use.remove(dict_obj)
            
            # 如果池未满，归还到池中
            if len(self._pool) < self._pool_size:
                self._pool.append(dict_obj)
    
    def clear_pool(self):
        """清空对象池"""
        self._pool.clear()
        self._in_use.clear()
        gc.collect()
    
    def get_stats(self):
        """获取对象池统计信息"""
        return {
            'pool_size': len(self._pool),
            'in_use': len(self._in_use),
            'max_pool_size': self._pool_size
        }

# =============================================================================
# 字符串缓存类
# =============================================================================

class StringCache:
    """字符串缓存 - 缓存常用字符串减少内存分配"""
    
    def __init__(self, max_size=50):
        """
        初始化字符串缓存
        
        Args:
            max_size: 最大缓存大小，默认50个字符串
        """
        self._cache = {}
        self._max_size = max_size
        self._access_count = {}
        
        # 预缓存常用字符串
        self._precache_common_strings()
        
        print(f"[StringCache] 字符串缓存初始化完成，最大大小: {max_size}")
    
    def _precache_common_strings(self):
        """预缓存常用字符串"""
        common_strings = [
            # 系统状态字符串
            'active', 'inactive', 'enabled', 'disabled', 'normal', 'warning', 'error',
            # 日志级别字符串
            'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL',
            # 网络状态字符串
            'connected', 'disconnected', 'connecting', 'scanning',
            # 内存状态字符串
            'free', 'used', 'total', 'percent',
            # 时间相关字符串
            'uptime', 'timestamp', 'duration',
            # 错误类型字符串
            'NETWORK_ERROR', 'HARDWARE_ERROR', 'MEMORY_ERROR', 'SYSTEM_ERROR',
            # 模块名称字符串
            'Main', 'Daemon', 'MQTT', 'WiFi', 'ErrorHandler'
        ]
        
        for string in common_strings:
            self._cache[string] = string
            self._access_count[string] = 0
    
    def get_string(self, string_value):
        """获取缓存的字符串"""
        if string_value in self._cache:
            self._access_count[string_value] += 1
            return self._cache[string_value]
        else:
            # 缓存未命中，添加到缓存
            if len(self._cache) < self._max_size:
                self._cache[string_value] = string_value
                self._access_count[string_value] = 1
            return string_value
    
    def get_cached_string(self, template, *args):
        """获取格式化的缓存字符串"""
        try:
            # 如果模板是固定的，尝试缓存格式化结果
            if args:
                formatted = template.format(*args)
                return self.get_string(formatted)
            else:
                return self.get_string(template)
        except:
            return template
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._access_count.clear()
        gc.collect()
    
    def get_stats(self):
        """获取缓存统计信息"""
        return {
            'cache_size': len(self._cache),
            'max_size': self._max_size,
            'hit_count': sum(self._access_count.values())
        }

# =============================================================================
# 预分配缓冲区管理类
# =============================================================================

class BufferManager:
    """预分配缓冲区管理器 - 管理各种大小的预分配缓冲区"""
    
    def __init__(self):
        """初始化缓冲区管理器"""
        self._buffers = {}
        self._buffer_sizes = [64, 128, 256, 512, 1024]  # 常用缓冲区大小
        
        # 预分配各种大小的缓冲区
        for size in self._buffer_sizes:
            self._buffers[size] = []
            for _ in range(3):  # 每种大小预分配3个缓冲区
                self._buffers[size].append(bytearray(size))
        
        print(f"[BufferManager] 缓冲区管理器初始化完成，预分配大小: {self._buffer_sizes}")
    
    def get_buffer(self, size):
        """获取指定大小的缓冲区"""
        # 找到最接近的较大缓冲区
        buffer_size = self._find_suitable_buffer(size)
        
        if buffer_size in self._buffers and self._buffers[buffer_size]:
            buffer = self._buffers[buffer_size].pop()
            # 清空缓冲区
            buffer.clear()
            return buffer
        else:
            # 没有可用的缓冲区，创建新的
            print(f"[BufferManager] 创建新缓冲区，大小: {buffer_size}")
            return bytearray(buffer_size)
    
    def _find_suitable_buffer(self, size):
        """找到合适大小的缓冲区"""
        for buffer_size in self._buffer_sizes:
            if size <= buffer_size:
                return buffer_size
        
        # 如果请求的缓冲区太大，返回原始大小
        return size
    
    def return_buffer(self, buffer):
        """归还缓冲区"""
        buffer_size = len(buffer)
        
        # 只回收预定义大小的缓冲区
        if buffer_size in self._buffers:
            if len(self._buffers[buffer_size]) < 3:  # 每种大小最多保留3个
                buffer.clear()
                self._buffers[buffer_size].append(buffer)
    
    def clear_all_buffers(self):
        """清空所有缓冲区"""
        for size in self._buffers:
            self._buffers[size].clear()
        gc.collect()
    
    def get_stats(self):
        """获取缓冲区统计信息"""
        stats = {}
        for size in self._buffers:
            stats[size] = len(self._buffers[size])
        return stats

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局对象池实例
_dict_pool = DictPool(pool_size=5)
_string_cache = StringCache(max_size=50)
_buffer_manager = BufferManager()

# =============================================================================
# 公共接口
# =============================================================================

def get_dict():
    """获取字典对象的便捷函数"""
    return _dict_pool.get_dict()

def return_dict(dict_obj):
    """归还字典对象的便捷函数"""
    _dict_pool.return_dict(dict_obj)

def get_string(string_value):
    """获取缓存字符串的便捷函数"""
    return _string_cache.get_string(string_value)

def get_cached_string(template, *args):
    """获取格式化缓存字符串的便捷函数"""
    return _string_cache.get_cached_string(template, *args)

def get_buffer(size):
    """获取缓冲区的便捷函数"""
    return _buffer_manager.get_buffer(size)

def return_buffer(buffer):
    """归还缓冲区的便捷函数"""
    _buffer_manager.return_buffer(buffer)

def get_object_pool_stats():
    """获取对象池统计信息"""
    return {
        'dict_pool': _dict_pool.get_stats(),
        'string_cache': _string_cache.get_stats(),
        'buffer_manager': _buffer_manager.get_stats()
    }

def clear_all_pools():
    """清空所有对象池"""
    _dict_pool.clear_pool()
    _string_cache.clear_cache()
    _buffer_manager.clear_all_buffers()
    print("[ObjectPool] 所有对象池已清空")

# =============================================================================
# 内存监控和优化工具
# =============================================================================

class MemoryOptimizer:
    """内存优化器 - 提供内存监控和优化功能"""
    
    def __init__(self):
        """初始化内存优化器"""
        self._last_gc_time = 0
        self._gc_interval = 30000  # 30秒垃圾回收间隔
        self._memory_thresholds = {
            'warning': 80,    # 80%内存使用警告
            'critical': 90,   # 90%内存使用严重
            'emergency': 95   # 95%内存使用紧急
        }
        
        print("[MemoryOptimizer] 内存优化器初始化完成")
    
    def check_memory(self):
        """检查内存状态并执行优化"""
        try:
            free_memory = gc.mem_free()
            total_memory = 264192  # ESP32C3总内存约264KB
            used_memory = total_memory - free_memory
            memory_percent = (used_memory / total_memory) * 100
            
            current_time = time.ticks_ms()
            
            # 根据内存使用情况执行相应操作
            if memory_percent >= self._memory_thresholds['emergency']:
                print(f"[MemoryOptimizer] 紧急内存清理: {memory_percent:.1f}%")
                self._emergency_cleanup()
            elif memory_percent >= self._memory_thresholds['critical']:
                print(f"[MemoryOptimizer] 严重内存清理: {memory_percent:.1f}%")
                self._critical_cleanup()
            elif memory_percent >= self._memory_thresholds['warning']:
                print(f"[MemoryOptimizer] 警告内存清理: {memory_percent:.1f}%")
                self._warning_cleanup()
            
            # 定期垃圾回收
            if time.ticks_diff(current_time, self._last_gc_time) > self._gc_interval:
                gc.collect()
                self._last_gc_time = current_time
            
            return {
                'free': free_memory,
                'used': used_memory,
                'total': total_memory,
                'percent': memory_percent
            }
            
        except Exception as e:
            print(f"[MemoryOptimizer] 内存检查失败: {e}")
            return None
    
    def _emergency_cleanup(self):
        """紧急内存清理"""
        print("[MemoryOptimizer] 执行紧急内存清理")
        
        # 深度垃圾回收
        for _ in range(5):
            gc.collect()
            time.sleep_ms(50)
        
        # 清空对象池
        clear_all_pools()
        
        # 重新初始化核心对象池
        global _dict_pool, _string_cache, _buffer_manager
        _dict_pool = DictPool(pool_size=3)  # 减少池大小
        _string_cache = StringCache(max_size=30)  # 减少缓存大小
        _buffer_manager = BufferManager()
    
    def _critical_cleanup(self):
        """严重内存清理"""
        print("[MemoryOptimizer] 执行严重内存清理")
        
        # 多次垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(100)
        
        # 清理字符串缓存
        _string_cache.clear_cache()
    
    def _warning_cleanup(self):
        """警告内存清理"""
        print("[MemoryOptimizer] 执行警告内存清理")
        
        # 单次垃圾回收
        gc.collect()
        
        # 清理字典池中未使用的字典
        while len(_dict_pool._pool) > 2:
            _dict_pool._pool.pop()
    
    def get_memory_stats(self):
        """获取内存统计信息"""
        return {
            'memory': self.check_memory(),
            'object_pools': get_object_pool_stats(),
            'thresholds': self._memory_thresholds
        }

# 创建全局内存优化器实例
_memory_optimizer = MemoryOptimizer()

def check_memory():
    """检查内存的便捷函数"""
    return _memory_optimizer.check_memory()

def get_memory_stats():
    """获取内存统计的便捷函数"""
    return _memory_optimizer.get_memory_stats()

# =============================================================================
# 初始化
# =============================================================================

# 执行初始垃圾回收
gc.collect()

print("[ObjectPool] 对象池和缓存优化模块加载完成")