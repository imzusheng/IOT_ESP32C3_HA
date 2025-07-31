# -*- coding: utf-8 -*-
"""
状态监控和增强日志模块

为ESP32C3设备提供全面的状态监控和日志管理：
- 实时状态监控
- 增强日志系统
- 性能指标收集
- 系统诊断
- 远程监控支持
"""

import time
import gc
import json
import sys
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque

# 导入依赖
try:
    import config
    import error_handler
    import memory_optimizer
    import enhanced_error_handler
except ImportError:
    # 简化配置
    class MockConfig:
        SystemConfig = type('SystemConfig', (), {
            'STATUS_MONITOR_INTERVAL': 30000,
            'LOG_BUFFER_SIZE': 100,
            'METRICS_HISTORY_SIZE': 200,
            'REMOTE_MONITORING_ENABLED': True,
            'DIAGNOSTIC_ENABLED': True
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
# 状态类型定义
# =============================================================================

class ComponentStatus(Enum):
    """组件状态"""
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    OFFLINE = "OFFLINE"

class SystemStatus(Enum):
    """系统状态"""
    BOOTING = "BOOTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    MAINTENANCE = "MAINTENANCE"
    EMERGENCY = "EMERGENCY"

# =============================================================================
# 状态数据类
# =============================================================================

@dataclass
class ComponentState:
    """组件状态"""
    name: str
    status: ComponentStatus
    last_update: float
    uptime: float
    error_count: int
    warning_count: int
    metrics: Dict[str, Any]
    message: str = ""
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)

@dataclass
class SystemMetrics:
    """系统指标"""
    timestamp: float
    uptime: float
    memory_usage: float
    memory_free: int
    cpu_usage: float  # 模拟值
    temperature: float
    network_status: str
    error_count: int
    warning_count: int
    component_count: int
    healthy_components: int
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)

# =============================================================================
# 组件监控器
# =============================================================================

class ComponentMonitor:
    """组件监控器"""
    
    def __init__(self, component_name: str):
        self.name = component_name
        self.state = ComponentState(
            name=component_name,
            status=ComponentStatus.UNKNOWN,
            last_update=time.time(),
            uptime=0,
            error_count=0,
            warning_count=0,
            metrics={}
        )
        self._start_time = time.time()
        self._health_check_callbacks = []
        self._logger = error_handler.get_logger()
    
    def add_health_check(self, callback: Callable[[], Dict]):
        """添加健康检查回调"""
        self._health_check_callbacks.append(callback)
    
    def update_status(self, status: ComponentStatus, message: str = "", metrics: Optional[Dict] = None):
        """更新组件状态"""
        self.state.status = status
        self.state.message = message
        self.state.last_update = time.time()
        self.state.uptime = time.time() - self._start_time
        
        if metrics:
            self.state.metrics.update(metrics)
        
        # 更新错误和警告计数
        if status == ComponentStatus.ERROR:
            self.state.error_count += 1
        elif status == ComponentStatus.WARNING:
            self.state.warning_count += 1
    
    def check_health(self) -> Dict:
        """执行健康检查"""
        try:
            results = {}
            
            for callback in self._health_check_callbacks:
                try:
                    result = callback()
                    if result:
                        results.update(result)
                except Exception as e:
                    self._logger.error(f"健康检查失败: {e}", f"ComponentMonitor[{self.name}]")
            
            # 根据检查结果更新状态
            if results:
                overall_health = results.get('overall_health', True)
                status = ComponentStatus.HEALTHY if overall_health else ComponentStatus.WARNING
                
                if results.get('has_errors', False):
                    status = ComponentStatus.ERROR
                elif results.get('has_warnings', False):
                    status = ComponentStatus.WARNING
                
                self.update_status(status, results.get('message', ''), results)
            
            return results
            
        except Exception as e:
            self._logger.error(f"健康检查执行失败: {e}", f"ComponentMonitor[{self.name}]")
            self.update_status(ComponentStatus.ERROR, f"健康检查失败: {e}")
            return {}
    
    def get_state(self) -> ComponentState:
        """获取组件状态"""
        # 更新运行时间
        self.state.uptime = time.time() - self._start_time
        return self.state
    
    def reset_stats(self):
        """重置统计"""
        self.state.error_count = 0
        self.state.warning_count = 0
        self._start_time = time.time()

# =============================================================================
# 系统状态监控器
# =============================================================================

class SystemStatusMonitor:
    """系统状态监控器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._components = {}
        self._metrics_history = deque(maxlen=config.SystemConfig.METRICS_HISTORY_SIZE)
        self._last_metrics_update = 0
        self._system_status = SystemStatus.BOOTING
        self._status_change_callbacks = []
        
        # 初始化系统组件
        self._init_system_components()
    
    def _init_system_components(self):
        """初始化系统组件"""
        # 创建主要组件监控器
        components = [
            'system', 'memory', 'network', 'daemon', 'mqtt', 'sensors'
        ]
        
        for component_name in components:
            self.register_component(component_name)
    
    def register_component(self, component_name: str) -> ComponentMonitor:
        """注册组件"""
        if component_name not in self._components:
            monitor = ComponentMonitor(component_name)
            self._components[component_name] = monitor
            
            # 为特定组件添加健康检查
            self._setup_component_health_checks(monitor)
        
        return self._components[component_name]
    
    def _setup_component_health_checks(self, monitor: ComponentMonitor):
        """设置组件健康检查"""
        component_name = monitor.name
        
        if component_name == 'memory':
            monitor.add_health_check(self._check_memory_health)
        elif component_name == 'network':
            monitor.add_health_check(self._check_network_health)
        elif component_name == 'system':
            monitor.add_health_check(self._check_system_health)
        elif component_name == 'daemon':
            monitor.add_health_check(self._check_daemon_health)
        elif component_name == 'mqtt':
            monitor.add_health_check(self._check_mqtt_health)
        elif component_name == 'sensors':
            monitor.add_health_check(self._check_sensors_health)
    
    def _check_memory_health(self) -> Dict:
        """检查内存健康"""
        try:
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            
            if total == 0:
                return {'overall_health': False, 'message': '无法获取内存信息'}
            
            percent = (alloc / total) * 100
            
            health = percent < 85
            message = f'内存使用率: {percent:.1f}%' if percent > 70 else None
            
            return {
                'overall_health': health,
                'has_warnings': percent > 70,
                'has_errors': percent > 90,
                'message': message,
                'memory_percent': percent,
                'memory_free': free
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'内存检查失败: {e}'}
    
    def _check_network_health(self) -> Dict:
        """检查网络健康"""
        try:
            # 简化版本：假设网络正常
            # 实际应该检查WiFi和MQTT连接状态
            return {
                'overall_health': True,
                'message': None,
                'network_status': 'connected'
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'网络检查失败: {e}'}
    
    def _check_system_health(self) -> Dict:
        """检查系统健康"""
        try:
            # 简化版本：检查整体系统状态
            error_stats = error_handler.get_error_stats()
            total_errors = sum(stats.get('count', 0) for stats in error_stats.values())
            
            health = total_errors < 50
            message = f'系统错误数: {total_errors}' if total_errors > 20 else None
            
            return {
                'overall_health': health,
                'has_warnings': total_errors > 20,
                'has_errors': total_errors > 100,
                'message': message,
                'total_errors': total_errors
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'系统检查失败: {e}'}
    
    def _check_daemon_health(self) -> Dict:
        """检查守护进程健康"""
        try:
            # 简化版本：假设守护进程正常
            return {
                'overall_health': True,
                'message': None,
                'daemon_status': 'running'
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'守护进程检查失败: {e}'}
    
    def _check_mqtt_health(self) -> Dict:
        """检查MQTT健康"""
        try:
            # 简化版本：假设MQTT正常
            return {
                'overall_health': True,
                'message': None,
                'mqtt_status': 'connected'
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'MQTT检查失败: {e}'}
    
    def _check_sensors_health(self) -> Dict:
        """检查传感器健康"""
        try:
            # 简化版本：模拟温度传感器
            temp = 45.0
            health = temp < 70
            message = f'温度: {temp:.1f}°C' if temp > 50 else None
            
            return {
                'overall_health': health,
                'has_warnings': temp > 50,
                'has_errors': temp > 80,
                'message': message,
                'temperature': temp
            }
            
        except Exception as e:
            return {'overall_health': False, 'message': f'传感器检查失败: {e}'}
    
    def update_system_metrics(self) -> SystemMetrics:
        """更新系统指标"""
        try:
            current_time = time.time()
            
            # 限制更新频率
            if current_time - self._last_metrics_update < 30:  # 30秒
                return self._metrics_history[-1] if self._metrics_history else None
            
            # 收集组件状态
            total_components = len(self._components)
            healthy_components = 0
            total_errors = 0
            total_warnings = 0
            
            for component in self._components.values():
                state = component.get_state()
                if state.status == ComponentStatus.HEALTHY:
                    healthy_components += 1
                total_errors += state.error_count
                total_warnings += state.warning_count
            
            # 获取内存信息
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            memory_percent = (alloc / total) * 100 if total > 0 else 0
            
            # 创建系统指标
            metrics = SystemMetrics(
                timestamp=current_time,
                uptime=current_time,  # 系统启动时间
                memory_usage=memory_percent,
                memory_free=free,
                cpu_usage=0.0,  # ESP32C3没有CPU使用率API
                temperature=45.0,  # 模拟温度
                network_status='connected',  # 模拟网络状态
                error_count=total_errors,
                warning_count=total_warnings,
                component_count=total_components,
                healthy_components=healthy_components
            )
            
            # 添加到历史记录
            self._metrics_history.append(metrics)
            self._last_metrics_update = current_time
            
            # 更新系统状态
            self._update_system_status(metrics)
            
            return metrics
            
        except Exception as e:
            self._logger.error(f"系统指标更新失败: {e}", "SystemStatusMonitor")
            return None
    
    def _update_system_status(self, metrics: SystemMetrics):
        """更新系统状态"""
        try:
            old_status = self._system_status
            new_status = self._determine_system_status(metrics)
            
            if old_status != new_status:
                self._system_status = new_status
                self._logger.info(f"系统状态变更: {old_status.value} -> {new_status.value}", "SystemStatusMonitor")
                
                # 通知状态变更回调
                for callback in self._status_change_callbacks:
                    try:
                        callback(old_status, new_status, metrics)
                    except Exception as e:
                        self._logger.error(f"状态变更回调失败: {e}", "SystemStatusMonitor")
            
        except Exception as e:
            self._logger.error(f"系统状态更新失败: {e}", "SystemStatusMonitor")
    
    def _determine_system_status(self, metrics: SystemMetrics) -> SystemStatus:
        """确定系统状态"""
        try:
            # 健康组件比例
            health_ratio = metrics.healthy_components / metrics.component_count if metrics.component_count > 0 else 0
            
            # 错误和警告数量
            error_count = metrics.error_count
            warning_count = metrics.warning_count
            
            # 内存使用率
            memory_usage = metrics.memory_usage
            
            # 状态判断逻辑
            if health_ratio >= 0.9 and error_count < 10 and memory_usage < 80:
                return SystemStatus.HEALTHY
            elif health_ratio >= 0.7 and error_count < 50 and memory_usage < 90:
                return SystemStatus.DEGRADED
            elif health_ratio >= 0.5 and error_count < 100 and memory_usage < 95:
                return SystemStatus.UNHEALTHY
            else:
                return SystemStatus.EMERGENCY
            
        except Exception as e:
            self._logger.error(f"系统状态判断失败: {e}", "SystemStatusMonitor")
            return SystemStatus.UNHEALTHY
    
    def add_status_change_callback(self, callback: Callable[[SystemStatus, SystemStatus, SystemMetrics], None]):
        """添加状态变更回调"""
        self._status_change_callbacks.append(callback)
    
    def get_system_status(self) -> SystemStatus:
        """获取系统状态"""
        return self._system_status
    
    def get_component_status(self, component_name: str) -> Optional[ComponentState]:
        """获取组件状态"""
        component = self._components.get(component_name)
        return component.get_state() if component else None
    
    def get_all_components_status(self) -> Dict[str, ComponentState]:
        """获取所有组件状态"""
        return {name: component.get_state() for name, component in self._components.items()}
    
    def get_latest_metrics(self) -> Optional[SystemMetrics]:
        """获取最新系统指标"""
        return self._metrics_history[-1] if self._metrics_history else None
    
    def get_metrics_history(self, count: int = 50) -> List[SystemMetrics]:
        """获取指标历史"""
        return list(self._metrics_history)[-count:]
    
    def perform_health_check(self) -> Dict:
        """执行健康检查"""
        try:
            self._logger.info("开始系统健康检查", "SystemStatusMonitor")
            
            results = {}
            
            # 检查所有组件
            for component_name, component in self._components.items():
                try:
                    component_result = component.check_health()
                    results[component_name] = component_result
                except Exception as e:
                    self._logger.error(f"组件 {component_name} 健康检查失败: {e}", "SystemStatusMonitor")
                    results[component_name] = {'overall_health': False, 'message': str(e)}
            
            # 更新系统指标
            metrics = self.update_system_metrics()
            
            # 生成健康报告
            health_report = {
                'timestamp': time.time(),
                'system_status': self._system_status.value,
                'components': results,
                'system_metrics': metrics.to_dict() if metrics else None,
                'overall_health': self._system_status in [SystemStatus.HEALTHY, SystemStatus.DEGRADED]
            }
            
            self._logger.info(f"健康检查完成，系统状态: {self._system_status.value}", "SystemStatusMonitor")
            
            return health_report
            
        except Exception as e:
            self._logger.error(f"健康检查失败: {e}", "SystemStatusMonitor")
            return {'overall_health': False, 'error': str(e)}

# =============================================================================
# 增强日志管理器
# =============================================================================

class EnhancedLogManager:
    """增强日志管理器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._log_entries = deque(maxlen=config.SystemConfig.LOG_BUFFER_SIZE)
        self._log_filters = {}
        self._log_subscribers = []
        self._stats = {
            'total_logs': 0,
            'debug_logs': 0,
            'info_logs': 0,
            'warning_logs': 0,
            'error_logs': 0,
            'critical_logs': 0
        }
    
    def log(self, level: str, message: str, module: str = "", **kwargs):
        """记录日志"""
        try:
            # 创建日志条目
            log_entry = {
                'timestamp': time.time(),
                'level': level,
                'message': message,
                'module': module,
                **kwargs
            }
            
            # 添加到缓冲区
            self._log_entries.append(log_entry)
            
            # 更新统计
            self._stats['total_logs'] += 1
            level_key = f"{level.lower()}_logs"
            if level_key in self._stats:
                self._stats[level_key] += 1
            
            # 通知订阅者
            self._notify_subscribers(log_entry)
            
            # 调用原始日志记录器
            log_method = getattr(self._logger, level.lower(), self._logger.info)
            log_method(message, module)
            
        except Exception as e:
            print(f"日志记录失败: {e}")
    
    def _notify_subscribers(self, log_entry: Dict):
        """通知日志订阅者"""
        for subscriber in self._log_subscribers:
            try:
                subscriber(log_entry)
            except Exception as e:
                self._logger.error(f"日志订阅者通知失败: {e}", "EnhancedLogManager")
    
    def add_log_filter(self, name: str, filter_func: Callable[[Dict], bool]):
        """添加日志过滤器"""
        self._log_filters[name] = filter_func
    
    def subscribe_to_logs(self, callback: Callable[[Dict], None]):
        """订阅日志"""
        self._log_subscribers.append(callback)
    
    def get_logs(self, level: Optional[str] = None, module: Optional[str] = None, 
                 count: int = 50, filter_name: Optional[str] = None) -> List[Dict]:
        """获取日志"""
        try:
            logs = list(self._log_entries)
            
            # 应用过滤器
            if filter_name and filter_name in self._log_filters:
                logs = [log for log in logs if self._log_filters[filter_name](log)]
            
            # 按级别过滤
            if level:
                logs = [log for log in logs if log.get('level') == level]
            
            # 按模块过滤
            if module:
                logs = [log for log in logs if log.get('module') == module]
            
            # 返回指定数量的日志
            return logs[-count:]
            
        except Exception as e:
            self._logger.error(f"获取日志失败: {e}", "EnhancedLogManager")
            return []
    
    def get_log_stats(self) -> Dict:
        """获取日志统计"""
        return self._stats.copy()
    
    def clear_logs(self):
        """清空日志"""
        self._log_entries.clear()
        self._stats = {
            'total_logs': 0,
            'debug_logs': 0,
            'info_logs': 0,
            'warning_logs': 0,
            'error_logs': 0,
            'critical_logs': 0
        }
    
    def export_logs(self, format_type: str = 'json') -> str:
        """导出日志"""
        try:
            logs = list(self._log_entries)
            
            if format_type == 'json':
                return json.dumps(logs, indent=2, default=str)
            elif format_type == 'csv':
                # 简化CSV格式
                lines = ['timestamp,level,module,message']
                for log in logs:
                    lines.append(f"{log['timestamp']},{log['level']},{log.get('module','')},{log['message']}")
                return '\\n'.join(lines)
            else:
                return str(logs)
                
        except Exception as e:
            self._logger.error(f"导出日志失败: {e}", "EnhancedLogManager")
            return ""

# =============================================================================
# 系统诊断器
# =============================================================================

class SystemDiagnostics:
    """系统诊断器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._status_monitor = None
        self._log_manager = None
        self._diagnostic_results = {}
    
    def set_status_monitor(self, monitor: SystemStatusMonitor):
        """设置状态监控器"""
        self._status_monitor = monitor
    
    def set_log_manager(self, manager: EnhancedLogManager):
        """设置日志管理器"""
        self._log_manager = manager
    
    def run_full_diagnostic(self) -> Dict:
        """运行完整诊断"""
        try:
            self._logger.info("开始系统诊断", "SystemDiagnostics")
            
            diagnostic_results = {
                'timestamp': time.time(),
                'system_info': self._get_system_info(),
                'memory_analysis': self._analyze_memory(),
                'error_analysis': self._analyze_errors(),
                'performance_analysis': self._analyze_performance(),
                'component_health': self._analyze_component_health(),
                'recommendations': self._generate_recommendations()
            }
            
            self._diagnostic_results = diagnostic_results
            
            self._logger.info("系统诊断完成", "SystemDiagnostics")
            
            return diagnostic_results
            
        except Exception as e:
            self._logger.error(f"系统诊断失败: {e}", "SystemDiagnostics")
            return {'error': str(e)}
    
    def _get_system_info(self) -> Dict:
        """获取系统信息"""
        try:
            return {
                'platform': 'ESP32C3',
                'uptime': time.time(),
                'python_version': sys.version,
                'memory_total': gc.mem_alloc() + gc.mem_free(),
                'memory_free': gc.mem_free(),
                'gc_enabled': True
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _analyze_memory(self) -> Dict:
        """分析内存使用"""
        try:
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            
            if total == 0:
                return {'error': '无法获取内存信息'}
            
            percent = (alloc / total) * 100
            
            analysis = {
                'memory_allocated': alloc,
                'memory_free': free,
                'memory_total': total,
                'memory_percent': percent,
                'memory_status': 'normal'
            }
            
            # 内存状态评估
            if percent > 90:
                analysis['memory_status'] = 'critical'
                analysis['recommendation'] = '内存使用过高，建议清理或重启'
            elif percent > 80:
                analysis['memory_status'] = 'warning'
                analysis['recommendation'] = '内存使用较高，建议关注'
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _analyze_errors(self) -> Dict:
        """分析错误"""
        try:
            error_stats = error_handler.get_error_stats()
            recovery_stats = enhanced_error_handler.get_recovery_stats()
            
            analysis = {
                'total_errors': sum(stats.get('count', 0) for stats in error_stats.values()),
                'error_types': list(error_stats.keys()),
                'recovery_stats': recovery_stats,
                'error_status': 'normal'
            }
            
            # 错误状态评估
            if analysis['total_errors'] > 100:
                analysis['error_status'] = 'critical'
                analysis['recommendation'] = '错误过多，建议检查系统'
            elif analysis['total_errors'] > 50:
                analysis['error_status'] = 'warning'
                analysis['recommendation'] = '错误较多，建议关注'
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _analyze_performance(self) -> Dict:
        """分析性能"""
        try:
            # 获取内存优化器性能数据
            perf_stats = memory_optimizer.get_memory_optimizer()._performance_monitor.get_performance_summary()
            
            analysis = {
                'performance_stats': perf_stats,
                'performance_status': 'normal'
            }
            
            # 性能状态评估
            if perf_stats.get('total_operations', 0) > 1000:
                avg_time = perf_stats.get('average_time_per_operation', 0)
                if avg_time > 1.0:  # 平均操作时间超过1秒
                    analysis['performance_status'] = 'warning'
                    analysis['recommendation'] = '性能较慢，建议优化'
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _analyze_component_health(self) -> Dict:
        """分析组件健康"""
        try:
            if not self._status_monitor:
                return {'error': '状态监控器未设置'}
            
            components_status = self._status_monitor.get_all_components_status()
            
            analysis = {
                'total_components': len(components_status),
                'healthy_components': sum(1 for s in components_status.values() if s.status == ComponentStatus.HEALTHY),
                'warning_components': sum(1 for s in components_status.values() if s.status == ComponentStatus.WARNING),
                'error_components': sum(1 for s in components_status.values() if s.status == ComponentStatus.ERROR),
                'component_status': 'normal'
            }
            
            # 组件状态评估
            health_ratio = analysis['healthy_components'] / analysis['total_components'] if analysis['total_components'] > 0 else 0
            
            if health_ratio < 0.5:
                analysis['component_status'] = 'critical'
                analysis['recommendation'] = '组件健康度过低，建议检查'
            elif health_ratio < 0.8:
                analysis['component_status'] = 'warning'
                analysis['recommendation'] = '部分组件异常，建议关注'
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _generate_recommendations(self) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于诊断结果生成建议
        if 'memory_analysis' in self._diagnostic_results:
            memory_analysis = self._diagnostic_results['memory_analysis']
            if memory_analysis.get('recommendation'):
                recommendations.append(memory_analysis['recommendation'])
        
        if 'error_analysis' in self._diagnostic_results:
            error_analysis = self._diagnostic_results['error_analysis']
            if error_analysis.get('recommendation'):
                recommendations.append(error_analysis['recommendation'])
        
        if 'performance_analysis' in self._diagnostic_results:
            performance_analysis = self._diagnostic_results['performance_analysis']
            if performance_analysis.get('recommendation'):
                recommendations.append(performance_analysis['recommendation'])
        
        if 'component_health' in self._diagnostic_results:
            component_health = self._diagnostic_results['component_health']
            if component_health.get('recommendation'):
                recommendations.append(component_health['recommendation'])
        
        # 通用建议
        if not recommendations:
            recommendations.append('系统运行正常，继续保持监控')
        
        return recommendations
    
    def get_diagnostic_results(self) -> Dict:
        """获取诊断结果"""
        return self._diagnostic_results.copy()

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局实例
_system_status_monitor = SystemStatusMonitor()
_enhanced_log_manager = EnhancedLogManager()
_system_diagnostics = SystemDiagnostics()

# 设置诊断器的依赖
_system_diagnostics.set_status_monitor(_system_status_monitor)
_system_diagnostics.set_log_manager(_enhanced_log_manager)

def get_system_status_monitor():
    """获取系统状态监控器"""
    return _system_status_monitor

def get_enhanced_log_manager():
    """获取增强日志管理器"""
    return _enhanced_log_manager

def get_system_diagnostics():
    """获取系统诊断器"""
    return _system_diagnostics

def log_enhanced(level: str, message: str, module: str = "", **kwargs):
    """增强日志记录"""
    _enhanced_log_manager.log(level, message, module, **kwargs)

def get_system_status() -> SystemStatus:
    """获取系统状态"""
    return _system_status_monitor.get_system_status()

def run_system_diagnostic() -> Dict:
    """运行系统诊断"""
    return _system_diagnostics.run_full_diagnostic()

# =============================================================================
# 便捷函数
# =============================================================================

def debug_enhanced(message: str, module: str = "", **kwargs):
    """增强调试日志"""
    log_enhanced('DEBUG', message, module, **kwargs)

def info_enhanced(message: str, module: str = "", **kwargs):
    """增强信息日志"""
    log_enhanced('INFO', message, module, **kwargs)

def warning_enhanced(message: str, module: str = "", **kwargs):
    """增强警告日志"""
    log_enhanced('WARNING', message, module, **kwargs)

def error_enhanced(message: str, module: str = "", **kwargs):
    """增强错误日志"""
    log_enhanced('ERROR', message, module, **kwargs)

def critical_enhanced(message: str, module: str = "", **kwargs):
    """增强严重错误日志"""
    log_enhanced('CRITICAL', message, module, **kwargs)

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()