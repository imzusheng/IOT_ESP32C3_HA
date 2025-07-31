# -*- coding: utf-8 -*-
"""
内存优化和性能监控模块

为ESP32C3设备提供高级内存管理和性能监控：
- 内存使用分析
- 智能垃圾回收
- 性能指标监控
- 内存泄漏检测
- 优化建议
"""

import time
import gc
import sys
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# 导入依赖
try:
    import config
    import error_handler
except ImportError:
    # 简化配置
    class MockConfig:
        SystemConfig = type('SystemConfig', (), {
            'MEMORY_MONITOR_INTERVAL': 30000,
            'MEMORY_WARNING_THRESHOLD': 80,
            'MEMORY_CRITICAL_THRESHOLD': 90,
            'GC_FORCE_THRESHOLD': 95,
            'MEMORY_LEAK_DETECTION_ENABLED': True,
            'PERFORMANCE_MONITORING_ENABLED': True
        })()
    config = MockConfig()
    
    class MockErrorHandler:
        def debug(self, msg, module=""): print(f"[DEBUG] {msg}")
        def info(self, msg, module=""): print(f"[INFO] {msg}")
        def warning(self, msg, module=""): print(f"[WARNING] {msg}")
        def error(self, msg, module=""): print(f"[ERROR] {msg}")
        def critical(self, msg, module=""): print(f"[CRITICAL] {msg}")
    
    error_handler = MockErrorHandler()

# =============================================================================
# 内存统计类
# =============================================================================

class MemoryStats:
    """内存统计管理器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._history_size = 100
        self._memory_history = []
        self._allocation_stats = defaultdict(int)
        self._object_counts = {}
        self._baseline_memory = None
        self._last_measurement = 0
        
    def measure_memory(self) -> Dict:
        """测量内存使用情况"""
        try:
            # 强制垃圾回收以获得准确的内存数据
            gc.collect()
            
            # 获取内存数据
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            
            if total == 0:
                return {}
            
            # 计算百分比
            percent = (alloc / total) * 100
            
            # 创建内存快照
            snapshot = {
                'timestamp': time.time(),
                'alloc': alloc,
                'free': free,
                'total': total,
                'percent': percent,
                'gc_count': getattr(gc, 'collect_count', 0)
            }
            
            # 添加到历史记录
            self._memory_history.append(snapshot)
            
            # 保持历史记录大小
            if len(self._memory_history) > self._history_size:
                self._memory_history.pop(0)
            
            # 更新对象计数
            self._update_object_counts()
            
            # 检测内存泄漏
            if config.SystemConfig.MEMORY_LEAK_DETECTION_ENABLED:
                self._detect_memory_leak(snapshot)
            
            self._last_measurement = time.time()
            return snapshot
            
        except Exception as e:
            self._logger.error(f"内存测量失败: {e}", "MemoryStats")
            return {}
    
    def _update_object_counts(self):
        """更新对象计数"""
        try:
            # 简化版本：统计主要对象类型
            current_objects = {
                'list': len([obj for obj in gc.objects() if type(obj).__name__ == 'list']),
                'dict': len([obj for obj in gc.objects() if type(obj).__name__ == 'dict']),
                'str': len([obj for obj in gc.objects() if type(obj).__name__ == 'str']),
                'bytearray': len([obj for obj in gc.objects() if type(obj).__name__ == 'bytearray']),
                'total_objects': len(gc.objects())
            }
            
            self._object_counts = current_objects
            
        except Exception as e:
            self._logger.error(f"对象计数失败: {e}", "MemoryStats")
    
    def _detect_memory_leak(self, current_snapshot: Dict):
        """检测内存泄漏"""
        try:
            if len(self._memory_history) < 10:
                return
            
            # 获取最近10次测量
            recent_snapshots = self._memory_history[-10:]
            
            # 计算内存增长趋势
            if len(recent_snapshots) >= 5:
                # 计算线性回归斜率
                timestamps = [s['timestamp'] for s in recent_snapshots]
                memory_values = [s['alloc'] for s in recent_snapshots]
                
                # 简单的斜率计算
                if len(timestamps) > 1:
                    time_diff = timestamps[-1] - timestamps[0]
                    memory_diff = memory_values[-1] - memory_values[0]
                    
                    if time_diff > 0:
                        growth_rate = memory_diff / time_diff  # 字节/秒
                        
                        # 如果增长过快，可能是内存泄漏
                        if growth_rate > 100:  # 每秒增长超过100字节
                            self._logger.warning(
                                f"检测到可能的内存泄漏，增长速率: {growth_rate:.1f}字节/秒",
                                "MemoryLeakDetector"
                            )
                            
                            # 触发深度清理
                            self._deep_cleanup()
            
        except Exception as e:
            self._logger.error(f"内存泄漏检测失败: {e}", "MemoryLeakDetector")
    
    def _deep_cleanup(self):
        """深度清理内存"""
        try:
            self._logger.info("执行深度内存清理", "MemoryStats")
            
            # 多次垃圾回收
            for i in range(3):
                gc.collect()
                time.sleep_ms(100)
            
            # 清理历史记录
            if len(self._memory_history) > 50:
                self._memory_history = self._memory_history[-25:]
            
            # 重置基线
            self._baseline_memory = None
            
            self._logger.info("深度内存清理完成", "MemoryStats")
            
        except Exception as e:
            self._logger.error(f"深度清理失败: {e}", "MemoryStats")
    
    def get_memory_trend(self) -> Dict:
        """获取内存趋势"""
        try:
            if len(self._memory_history) < 2:
                return {}
            
            # 计算趋势
            recent = self._memory_history[-10:]
            
            min_memory = min(s['alloc'] for s in recent)
            max_memory = max(s['alloc'] for s in recent)
            avg_memory = sum(s['alloc'] for s in recent) / len(recent)
            
            current_memory = self._memory_history[-1]['alloc']
            
            return {
                'min': min_memory,
                'max': max_memory,
                'avg': avg_memory,
                'current': current_memory,
                'trend': 'increasing' if current_memory > avg_memory else 'stable',
                'variance': max_memory - min_memory
            }
            
        except Exception as e:
            self._logger.error(f"内存趋势计算失败: {e}", "MemoryStats")
            return {}
    
    def get_object_stats(self) -> Dict:
        """获取对象统计"""
        return self._object_counts.copy()
    
    def get_history(self, count: int = 10) -> List[Dict]:
        """获取内存历史"""
        return self._memory_history[-count:]
    
    def set_baseline(self):
        """设置内存基线"""
        snapshot = self.measure_memory()
        if snapshot:
            self._baseline_memory = snapshot
            self._logger.info(f"内存基线已设置: {snapshot['alloc']}字节", "MemoryStats")
    
    def get_baseline_comparison(self) -> Dict:
        """获取与基线的比较"""
        if not self._baseline_memory:
            return {}
        
        current = self.measure_memory()
        if not current:
            return {}
        
        baseline = self._baseline_memory
        
        return {
            'baseline_alloc': baseline['alloc'],
            'current_alloc': current['alloc'],
            'difference': current['alloc'] - baseline['alloc'],
            'percent_change': ((current['alloc'] - baseline['alloc']) / baseline['alloc']) * 100 if baseline['alloc'] > 0 else 0
        }

# =============================================================================
# 智能垃圾回收器
# =============================================================================

class SmartGarbageCollector:
    """智能垃圾回收器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._memory_stats = MemoryStats()
        self._collection_history = []
        self._adaptive_threshold = 80  # 自适应阈值
        self._collection_count = 0
        self._last_collection = 0
        self._forced_collections = 0
        
    def collect_if_needed(self, force: bool = False) -> bool:
        """按需执行垃圾回收"""
        try:
            current_time = time.time()
            
            # 获取当前内存状态
            memory_snapshot = self._memory_stats.measure_memory()
            if not memory_snapshot:
                return False
            
            memory_percent = memory_snapshot['percent']
            
            # 决定是否需要垃圾回收
            should_collect = force or self._should_collect(memory_percent, current_time)
            
            if should_collect:
                return self._perform_collection(memory_snapshot, current_time)
            
            return False
            
        except Exception as e:
            self._logger.error(f"垃圾回收决策失败: {e}", "SmartGC")
            return False
    
    def _should_collect(self, memory_percent: float, current_time: float) -> bool:
        """决定是否需要垃圾回收"""
        try:
            # 强制回收条件
            if memory_percent >= config.SystemConfig.GC_FORCE_THRESHOLD:
                self._logger.warning(f"内存使用过高 ({memory_percent:.1f}%)，强制垃圾回收", "SmartGC")
                return True
            
            # 基于时间的回收
            time_since_last = current_time - self._last_collection
            min_interval = 5.0  # 最小间隔5秒
            
            if time_since_last < min_interval:
                return False
            
            # 自适应阈值
            if memory_percent >= self._adaptive_threshold:
                return True
            
            # 基于内存增长趋势
            trend = self._memory_stats.get_memory_trend()
            if trend.get('trend') == 'increasing' and memory_percent > 70:
                return True
            
            return False
            
        except Exception as e:
            self._logger.error(f"垃圾回收条件判断失败: {e}", "SmartGC")
            return False
    
    def _perform_collection(self, before_snapshot: Dict, current_time: float) -> bool:
        """执行垃圾回收"""
        try:
            # 记录回收前状态
            before_alloc = before_snapshot['alloc']
            
            # 执行垃圾回收
            gc.collect()
            self._collection_count += 1
            self._last_collection = current_time
            
            # 测量回收后状态
            after_snapshot = self._memory_stats.measure_memory()
            after_alloc = after_snapshot.get('alloc', before_alloc)
            
            # 计算回收效果
            freed = before_alloc - after_alloc
            
            # 记录回收历史
            collection_record = {
                'timestamp': current_time,
                'before_alloc': before_alloc,
                'after_alloc': after_alloc,
                'freed': freed,
                'before_percent': before_snapshot['percent'],
                'after_percent': after_snapshot.get('percent', before_snapshot['percent']),
                'forced': freed == 0  # 如果没有释放内存，可能是强制回收
            }
            
            self._collection_history.append(collection_record)
            
            # 保持历史记录大小
            if len(self._collection_history) > 50:
                self._collection_history.pop(0)
            
            # 调整自适应阈值
            self._adjust_adaptive_threshold(collection_record)
            
            # 记录日志
            if freed > 0:
                self._logger.debug(
                    f"垃圾回收 #{self._collection_count} 完成，释放: {freed}字节",
                    "SmartGC"
                )
            else:
                self._logger.debug(
                    f"垃圾回收 #{self._collection_count} 完成，无内存释放",
                    "SmartGC"
                )
            
            return True
            
        except Exception as e:
            self._logger.error(f"垃圾回收执行失败: {e}", "SmartGC")
            return False
    
    def _adjust_adaptive_threshold(self, collection_record: Dict):
        """调整自适应阈值"""
        try:
            # 根据回收效果调整阈值
            if collection_record['freed'] > 1024:  # 释放超过1KB
                # 效果好，可以降低阈值
                self._adaptive_threshold = max(70, self._adaptive_threshold - 1)
            elif collection_record['freed'] == 0:
                # 效果差，提高阈值
                self._adaptive_threshold = min(90, self._adaptive_threshold + 1)
            
        except Exception as e:
            self._logger.error(f"自适应阈值调整失败: {e}", "SmartGC")
    
    def get_collection_stats(self) -> Dict:
        """获取垃圾回收统计"""
        try:
            if not self._collection_history:
                return {}
            
            total_freed = sum(record['freed'] for record in self._collection_history)
            avg_freed = total_freed / len(self._collection_history)
            
            return {
                'total_collections': self._collection_count,
                'total_freed': total_freed,
                'avg_freed': avg_freed,
                'adaptive_threshold': self._adaptive_threshold,
                'last_collection': self._last_collection,
                'recent_collections': len(self._collection_history)
            }
            
        except Exception as e:
            self._logger.error(f"获取回收统计失败: {e}", "SmartGC")
            return {}
    
    def get_memory_stats(self) -> MemoryStats:
        """获取内存统计管理器"""
        return self._memory_stats

# =============================================================================
# 性能监控器
# =============================================================================

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._metrics = {}
        self._start_times = {}
        self._performance_history = []
        self._history_size = 100
        
    def start_timing(self, operation: str):
        """开始计时"""
        try:
            self._start_times[operation] = time.time()
        except Exception as e:
            self._logger.error(f"开始计时失败: {e}", "PerformanceMonitor")
    
    def end_timing(self, operation: str) -> Optional[float]:
        """结束计时并返回耗时"""
        try:
            if operation not in self._start_times:
                return None
            
            start_time = self._start_times.pop(operation)
            duration = time.time() - start_time
            
            # 记录性能指标
            self._record_metric(operation, duration)
            
            return duration
            
        except Exception as e:
            self._logger.error(f"结束计时失败: {e}", "PerformanceMonitor")
            return None
    
    def _record_metric(self, operation: str, duration: float):
        """记录性能指标"""
        try:
            # 更新指标统计
            if operation not in self._metrics:
                self._metrics[operation] = {
                    'count': 0,
                    'total_time': 0,
                    'min_time': float('inf'),
                    'max_time': 0,
                    'avg_time': 0
                }
            
            metric = self._metrics[operation]
            metric['count'] += 1
            metric['total_time'] += duration
            metric['min_time'] = min(metric['min_time'], duration)
            metric['max_time'] = max(metric['max_time'], duration)
            metric['avg_time'] = metric['total_time'] / metric['count']
            
            # 添加到历史记录
            record = {
                'timestamp': time.time(),
                'operation': operation,
                'duration': duration
            }
            
            self._performance_history.append(record)
            
            # 保持历史记录大小
            if len(self._performance_history) > self._history_size:
                self._performance_history.pop(0)
            
            # 检查性能异常
            self._check_performance_anomaly(operation, duration)
            
        except Exception as e:
            self._logger.error(f"记录性能指标失败: {e}", "PerformanceMonitor")
    
    def _check_performance_anomaly(self, operation: str, duration: float):
        """检查性能异常"""
        try:
            if operation not in self._metrics:
                return
            
            metric = self._metrics[operation]
            
            # 如果执行时间超过平均时间的3倍，记录警告
            if metric['count'] > 5 and duration > metric['avg_time'] * 3:
                self._logger.warning(
                    f"性能异常: {operation} 耗时 {duration:.3f}s (平均: {metric['avg_time']:.3f}s)",
                    "PerformanceMonitor"
                )
            
        except Exception as e:
            self._logger.error(f"性能异常检查失败: {e}", "PerformanceMonitor")
    
    def get_metrics(self) -> Dict:
        """获取性能指标"""
        return self._metrics.copy()
    
    def get_operation_stats(self, operation: str) -> Optional[Dict]:
        """获取特定操作的统计"""
        return self._metrics.get(operation)
    
    def get_recent_performance(self, count: int = 20) -> List[Dict]:
        """获取最近的性能记录"""
        return self._performance_history[-count:]
    
    def get_performance_summary(self) -> Dict:
        """获取性能摘要"""
        try:
            if not self._metrics:
                return {}
            
            total_operations = sum(metric['count'] for metric in self._metrics.values())
            total_time = sum(metric['total_time'] for metric in self._metrics.values())
            
            # 找出最慢的操作
            slowest_operation = max(
                self._metrics.items(),
                key=lambda x: x[1]['avg_time'],
                default=(None, None)
            )
            
            # 找出最频繁的操作
            most_frequent_operation = max(
                self._metrics.items(),
                key=lambda x: x[1]['count'],
                default=(None, None)
            )
            
            return {
                'total_operations': total_operations,
                'total_time': total_time,
                'average_time_per_operation': total_time / total_operations if total_operations > 0 else 0,
                'slowest_operation': slowest_operation[0],
                'slowest_avg_time': slowest_operation[1]['avg_time'] if slowest_operation[1] else 0,
                'most_frequent_operation': most_frequent_operation[0],
                'most_frequent_count': most_frequent_operation[1]['count'] if most_frequent_operation[1] else 0,
                'monitored_operations': len(self._metrics)
            }
            
        except Exception as e:
            self._logger.error(f"性能摘要生成失败: {e}", "PerformanceMonitor")
            return {}

# =============================================================================
# 内存优化器
# =============================================================================

class MemoryOptimizer:
    """内存优化器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._gc = SmartGarbageCollector()
        self._performance_monitor = PerformanceMonitor()
        self._optimization_stats = {
            'optimizations_performed': 0,
            'memory_saved': 0,
            'last_optimization': 0
        }
        
    def optimize_memory(self, force: bool = False) -> bool:
        """优化内存使用"""
        try:
            self._performance_monitor.start_timing('memory_optimization')
            
            # 执行垃圾回收
            collected = self._gc.collect_if_needed(force)
            
            if collected:
                self._optimization_stats['optimizations_performed'] += 1
                self._optimization_stats['last_optimization'] = time.time()
            
            # 检查是否需要深度优化
            memory_stats = self._gc.get_memory_stats()
            current_snapshot = memory_stats.measure_memory()
            
            if current_snapshot and current_snapshot['percent'] > 85:
                self._deep_optimization()
            
            self._performance_monitor.end_timing('memory_optimization')
            return collected
            
        except Exception as e:
            self._logger.error(f"内存优化失败: {e}", "MemoryOptimizer")
            return False
    
    def _deep_optimization(self):
        """深度优化"""
        try:
            self._logger.info("执行深度内存优化", "MemoryOptimizer")
            
            # 获取优化前内存
            before_stats = self._gc.get_memory_stats()
            before_snapshot = before_stats.measure_memory()
            before_memory = before_snapshot.get('alloc', 0)
            
            # 清理性能历史
            self._performance_monitor._performance_history = self._performance_monitor._performance_history[-25:]
            
            # 清理垃圾回收历史
            self._gc._collection_history = self._gc._collection_history[-25:]
            
            # 清理内存历史
            before_stats._memory_history = before_stats._memory_history[-25:]
            
            # 多次垃圾回收
            for i in range(3):
                gc.collect()
                time.sleep_ms(100)
            
            # 获取优化后内存
            after_snapshot = before_stats.measure_memory()
            after_memory = after_snapshot.get('alloc', before_memory)
            
            saved = before_memory - after_memory
            if saved > 0:
                self._optimization_stats['memory_saved'] += saved
                self._logger.info(f"深度优化完成，节省: {saved}字节", "MemoryOptimizer")
            
        except Exception as e:
            self._logger.error(f"深度优化失败: {e}", "MemoryOptimizer")
    
    def get_optimization_stats(self) -> Dict:
        """获取优化统计"""
        return self._optimization_stats.copy()
    
    def get_memory_report(self) -> Dict:
        """获取内存报告"""
        try:
            memory_stats = self._gc.get_memory_stats()
            current_snapshot = memory_stats.measure_memory()
            
            if not current_snapshot:
                return {}
            
            report = {
                'current_memory': current_snapshot,
                'memory_trend': memory_stats.get_memory_trend(),
                'object_stats': memory_stats.get_object_stats(),
                'gc_stats': self._gc.get_collection_stats(),
                'optimization_stats': self.get_optimization_stats(),
                'performance_summary': self._performance_monitor.get_performance_summary()
            }
            
            # 添加基线比较
            baseline_comparison = memory_stats.get_baseline_comparison()
            if baseline_comparison:
                report['baseline_comparison'] = baseline_comparison
            
            return report
            
        except Exception as e:
            self._logger.error(f"内存报告生成失败: {e}", "MemoryOptimizer")
            return {}
    
    def set_memory_baseline(self):
        """设置内存基线"""
        try:
            self._gc.get_memory_stats().set_baseline()
            self._logger.info("内存基线已设置", "MemoryOptimizer")
        except Exception as e:
            self._logger.error(f"设置内存基线失败: {e}", "MemoryOptimizer")

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局内存优化器
_memory_optimizer = MemoryOptimizer()

def get_memory_optimizer():
    """获取全局内存优化器"""
    return _memory_optimizer

def optimize_memory(force: bool = False) -> bool:
    """优化内存使用"""
    return _memory_optimizer.optimize_memory(force)

def get_memory_report() -> Dict:
    """获取内存报告"""
    return _memory_optimizer.get_memory_report()

def set_memory_baseline():
    """设置内存基线"""
    _memory_optimizer.set_memory_baseline()

# =============================================================================
# 性能监控装饰器
# =============================================================================

def monitor_performance(operation_name: str = None):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            _memory_optimizer._performance_monitor.start_timing(op_name)
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                _memory_optimizer._performance_monitor.end_timing(op_name)
        return wrapper
    return decorator

# =============================================================================
# 初始化
# =============================================================================

# 设置初始内存基线
set_memory_baseline()

# 执行垃圾回收
gc.collect()