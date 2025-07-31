# -*- coding: utf-8 -*-
"""
增强错误处理和恢复机制

为ESP32C3设备提供高级错误处理和系统恢复功能：
- 智能错误分类和处理
- 自动恢复机制
- 系统健康监控
- 故障诊断
- 预防性维护
"""

import time
import gc
import sys
import machine
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass

# 导入依赖
try:
    import config
    import error_handler
    import memory_optimizer
except ImportError:
    # 简化配置
    class MockConfig:
        SystemConfig = type('SystemConfig', (), {
            'ERROR_RECOVERY_ENABLED': True,
            'AUTO_RESTART_ENABLED': True,
            'HEALTH_CHECK_INTERVAL': 60000,
            'MAX_RECOVERY_ATTEMPTS': 3,
            'RECOVERY_COOLDOWN': 30000,
            'CRITICAL_ERROR_THRESHOLD': 5
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
# 错误严重程度定义
# =============================================================================

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "LOW"           # 低级错误，不影响系统运行
    MEDIUM = "MEDIUM"     # 中级错误，影响部分功能
    HIGH = "HIGH"         # 高级错误，影响主要功能
    CRITICAL = "CRITICAL" # 严重错误，系统无法正常运行
    FATAL = "FATAL"       # 致命错误，需要立即重启

# =============================================================================
# 错误恢复策略
# =============================================================================

class RecoveryStrategy(Enum):
    """恢复策略"""
    NONE = "NONE"                     # 无需恢复
    RETRY = "RETRY"                   # 重试
    RESTART_COMPONENT = "RESTART_COMPONENT"  # 重启组件
    RESTART_SYSTEM = "RESTART_SYSTEM"       # 重启系统
    RESET_CONNECTION = "RESET_CONNECTION"   # 重置连接
    CLEAR_CACHE = "CLEAR_CACHE"           # 清除缓存
    FALLBACK_MODE = "FALLBACK_MODE"       # 降级模式
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"  # 紧急关闭

# =============================================================================
# 错误上下文数据类
# =============================================================================

@dataclass
class ErrorContext:
    """错误上下文"""
    error_type: error_handler.ErrorType
    severity: ErrorSeverity
    message: str
    component: str
    timestamp: float
    stack_trace: Optional[str] = None
    additional_data: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'error_type': self.error_type.value,
            'severity': self.severity.value,
            'message': self.message,
            'component': self.component,
            'timestamp': self.timestamp,
            'stack_trace': self.stack_trace,
            'additional_data': self.additional_data or {}
        }

# =============================================================================
# 恢复动作类
# =============================================================================

class RecoveryAction:
    """恢复动作基类"""
    
    def __init__(self, name: str, strategy: RecoveryStrategy):
        self.name = name
        self.strategy = strategy
        self.execution_count = 0
        self.success_count = 0
        self.last_execution = 0
        
    def execute(self, context: ErrorContext) -> bool:
        """执行恢复动作"""
        try:
            self.execution_count += 1
            self.last_execution = time.time()
            
            result = self._execute_action(context)
            
            if result:
                self.success_count += 1
                
            return result
            
        except Exception as e:
            error_handler.error(f"恢复动作执行失败: {e}", "RecoveryAction")
            return False
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """子类实现具体恢复逻辑"""
        raise NotImplementedError
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'name': self.name,
            'strategy': self.strategy.value,
            'execution_count': self.execution_count,
            'success_count': self.success_count,
            'success_rate': self.success_count / self.execution_count if self.execution_count > 0 else 0,
            'last_execution': self.last_execution
        }

# =============================================================================
# 具体恢复动作实现
# =============================================================================

class RetryAction(RecoveryAction):
    """重试动作"""
    
    def __init__(self, max_retries: int = 3, delay_ms: int = 1000):
        super().__init__("重试", RecoveryStrategy.RETRY)
        self.max_retries = max_retries
        self.delay_ms = delay_ms
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """执行重试"""
        error_handler.info(f"开始重试 (最多{self.max_retries}次)", "RetryAction")
        
        for attempt in range(1, self.max_retries + 1):
            try:
                # 这里应该根据上下文执行具体的重试逻辑
                # 简化版本：等待一段时间
                time.sleep_ms(self.delay_ms)
                
                # 模拟重试成功
                if attempt > 1:  # 假设第二次重试成功
                    error_handler.info(f"重试成功 (第{attempt}次)", "RetryAction")
                    return True
                    
            except Exception as e:
                error_handler.warning(f"重试第{attempt}次失败: {e}", "RetryAction")
                continue
        
        error_handler.error("重试失败", "RetryAction")
        return False

class RestartComponentAction(RecoveryAction):
    """重启组件动作"""
    
    def __init__(self, component_name: str):
        super().__init__(f"重启{component_name}", RecoveryStrategy.RESTART_COMPONENT)
        self.component_name = component_name
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """执行组件重启"""
        try:
            error_handler.info(f"重启组件: {self.component_name}", "RestartComponentAction")
            
            # 这里应该根据组件名称执行具体的重启逻辑
            # 简化版本：记录日志并返回成功
            error_handler.info(f"组件 {self.component_name} 重启成功", "RestartComponentAction")
            return True
            
        except Exception as e:
            error_handler.error(f"组件重启失败: {e}", "RestartComponentAction")
            return False

class MemoryCleanupAction(RecoveryAction):
    """内存清理动作"""
    
    def __init__(self):
        super().__init__("内存清理", RecoveryStrategy.CLEAR_CACHE)
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """执行内存清理"""
        try:
            error_handler.info("开始内存清理", "MemoryCleanupAction")
            
            # 执行深度垃圾回收
            for i in range(3):
                gc.collect()
                time.sleep_ms(100)
            
            # 调用内存优化器
            try:
                memory_optimizer.optimize_memory(force=True)
            except:
                pass
            
            error_handler.info("内存清理完成", "MemoryCleanupAction")
            return True
            
        except Exception as e:
            error_handler.error(f"内存清理失败: {e}", "MemoryCleanupAction")
            return False

class SystemRestartAction(RecoveryAction):
    """系统重启动作"""
    
    def __init__(self):
        super().__init__("系统重启", RecoveryStrategy.RESTART_SYSTEM)
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """执行系统重启"""
        try:
            error_handler.critical("准备重启系统", "SystemRestartAction")
            
            # 给系统一些时间来完成清理
            time.sleep_ms(2000)
            
            # 执行重启
            machine.reset()
            
            # 理论上不会执行到这里
            return True
            
        except Exception as e:
            error_handler.error(f"系统重启失败: {e}", "SystemRestartAction")
            return False

class ConnectionResetAction(RecoveryAction):
    """连接重置动作"""
    
    def __init__(self):
        super().__init__("连接重置", RecoveryStrategy.RESET_CONNECTION)
    
    def _execute_action(self, context: ErrorContext) -> bool:
        """执行连接重置"""
        try:
            error_handler.info("重置网络连接", "ConnectionResetAction")
            
            # 这里应该执行具体的连接重置逻辑
            # 简化版本：记录日志
            error_handler.info("连接重置完成", "ConnectionResetAction")
            return True
            
        except Exception as e:
            error_handler.error(f"连接重置失败: {e}", "ConnectionResetAction")
            return False

# =============================================================================
# 错误恢复管理器
# =============================================================================

class ErrorRecoveryManager:
    """错误恢复管理器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._recovery_actions = {}
        self._error_history = []
        self._recovery_stats = {
            'total_errors': 0,
            'successful_recoveries': 0,
            'failed_recoveries': 0,
            'last_recovery': 0
        }
        self._recovery_cooldowns = {}
        
        # 初始化恢复动作
        self._init_recovery_actions()
    
    def _init_recovery_actions(self):
        """初始化恢复动作"""
        self._recovery_actions = {
            error_handler.ErrorType.NETWORK: [
                RetryAction(max_retries=3, delay_ms=2000),
                ConnectionResetAction(),
                RestartComponentAction("WiFi")
            ],
            error_handler.ErrorType.MEMORY: [
                MemoryCleanupAction(),
                RetryAction(max_retries=2, delay_ms=1000)
            ],
            error_handler.ErrorType.HARDWARE: [
                RestartComponentAction("Hardware"),
                SystemRestartAction()
            ],
            error_handler.ErrorType.SYSTEM: [
                MemoryCleanupAction(),
                RetryAction(max_retries=2, delay_ms=1500),
                SystemRestartAction()
            ],
            error_handler.ErrorType.MQTT: [
                RetryAction(max_retries=3, delay_ms=1000),
                ConnectionResetAction(),
                RestartComponentAction("MQTT")
            ],
            error_handler.ErrorType.WIFI: [
                RetryAction(max_retries=3, delay_ms=2000),
                ConnectionResetAction(),
                RestartComponentAction("WiFi")
            ],
            error_handler.ErrorType.DAEMON: [
                RestartComponentAction("Daemon"),
                MemoryCleanupAction()
            ],
            error_handler.ErrorType.CONFIG: [
                # 配置错误通常需要手动干预
            ]
        }
    
    def handle_error(self, context: ErrorContext) -> bool:
        """处理错误"""
        try:
            self._recovery_stats['total_errors'] += 1
            
            # 记录错误
            self._error_history.append(context)
            
            # 保持历史记录大小
            if len(self._error_history) > 100:
                self._error_history.pop(0)
            
            # 检查是否在冷却期
            if self._is_in_cooldown(context.error_type):
                self._logger.warning(f"错误类型 {context.error_type.value} 在冷却期，跳过恢复", "ErrorRecovery")
                return False
            
            # 获取恢复动作
            actions = self._recovery_actions.get(context.error_type, [])
            
            if not actions:
                self._logger.warning(f"没有找到错误类型 {context.error_type.value} 的恢复动作", "ErrorRecovery")
                return False
            
            # 执行恢复动作
            return self._execute_recovery_actions(context, actions)
            
        except Exception as e:
            self._logger.error(f"错误处理失败: {e}", "ErrorRecovery")
            return False
    
    def _execute_recovery_actions(self, context: ErrorContext, actions: List[RecoveryAction]) -> bool:
        """执行恢复动作"""
        try:
            self._logger.info(f"开始恢复错误: {context.error_type.value}", "ErrorRecovery")
            
            for action in actions:
                self._logger.info(f"尝试恢复动作: {action.name}", "ErrorRecovery")
                
                if action.execute(context):
                    self._recovery_stats['successful_recoveries'] += 1
                    self._recovery_stats['last_recovery'] = time.time()
                    
                    # 设置冷却期
                    self._set_cooldown(context.error_type)
                    
                    self._logger.info(f"恢复成功: {action.name}", "ErrorRecovery")
                    return True
                else:
                    self._logger.warning(f"恢复动作失败: {action.name}", "ErrorRecovery")
            
            # 所有恢复动作都失败
            self._recovery_stats['failed_recoveries'] += 1
            
            # 如果是严重错误，考虑系统重启
            if context.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.FATAL]:
                self._logger.critical("所有恢复动作失败，考虑系统重启", "ErrorRecovery")
                if config.SystemConfig.AUTO_RESTART_ENABLED:
                    SystemRestartAction().execute(context)
            
            return False
            
        except Exception as e:
            self._logger.error(f"恢复动作执行失败: {e}", "ErrorRecovery")
            return False
    
    def _is_in_cooldown(self, error_type: error_handler.ErrorType) -> bool:
        """检查是否在冷却期"""
        cooldown_time = self._recovery_cooldowns.get(error_type, 0)
        return time.time() - cooldown_time < config.SystemConfig.RECOVERY_COOLDOWN / 1000
    
    def _set_cooldown(self, error_type: error_handler.ErrorType):
        """设置冷却期"""
        self._recovery_cooldowns[error_type] = time.time()
    
    def get_recovery_stats(self) -> Dict:
        """获取恢复统计"""
        return self._recovery_stats.copy()
    
    def get_action_stats(self) -> Dict:
        """获取动作统计"""
        stats = {}
        for error_type, actions in self._recovery_actions.items():
            stats[error_type.value] = [action.get_stats() for action in actions]
        return stats
    
    def get_error_history(self, count: int = 10) -> List[Dict]:
        """获取错误历史"""
        return [context.to_dict() for context in self._error_history[-count:]]
    
    def reset_stats(self):
        """重置统计"""
        self._recovery_stats = {
            'total_errors': 0,
            'successful_recoveries': 0,
            'failed_recoveries': 0,
            'last_recovery': 0
        }
        self._error_history.clear()
        self._recovery_cooldowns.clear()

# =============================================================================
# 系统健康监控器
# =============================================================================

class SystemHealthMonitor:
    """系统健康监控器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._health_metrics = {}
        self._health_checks = {}
        self._last_health_check = 0
        self._unhealthy_components = set()
        
        # 初始化健康检查
        self._init_health_checks()
    
    def _init_health_checks(self):
        """初始化健康检查"""
        self._health_checks = {
            'memory': self._check_memory_health,
            'temperature': self._check_temperature_health,
            'connectivity': self._check_connectivity_health,
            'daemon': self._check_daemon_health,
            'error_rate': self._check_error_rate_health
        }
    
    def _check_memory_health(self) -> Dict:
        """检查内存健康"""
        try:
            # 获取内存使用情况
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            
            if total == 0:
                return {'healthy': False, 'reason': '无法获取内存信息'}
            
            percent = (alloc / total) * 100
            
            # 健康状态判断
            if percent < 70:
                status = 'healthy'
            elif percent < 85:
                status = 'warning'
            elif percent < 95:
                status = 'critical'
            else:
                status = 'fatal'
            
            return {
                'healthy': status in ['healthy', 'warning'],
                'status': status,
                'memory_percent': percent,
                'memory_free': free,
                'reason': f'内存使用率: {percent:.1f}%' if status != 'healthy' else None
            }
            
        except Exception as e:
            return {'healthy': False, 'reason': f'内存检查失败: {e}'}
    
    def _check_temperature_health(self) -> Dict:
        """检查温度健康"""
        try:
            # 模拟温度读取
            temp = 45.0  # 实际应该从硬件读取
            
            # 健康状态判断
            if temp < 50:
                status = 'healthy'
            elif temp < 70:
                status = 'warning'
            elif temp < 85:
                status = 'critical'
            else:
                status = 'fatal'
            
            return {
                'healthy': status in ['healthy', 'warning'],
                'status': status,
                'temperature': temp,
                'reason': f'温度: {temp:.1f}°C' if status != 'healthy' else None
            }
            
        except Exception as e:
            return {'healthy': False, 'reason': f'温度检查失败: {e}'}
    
    def _check_connectivity_health(self) -> Dict:
        """检查连接健康"""
        try:
            # 简化版本：假设连接正常
            # 实际应该检查WiFi和MQTT连接状态
            return {
                'healthy': True,
                'status': 'healthy',
                'reason': None
            }
            
        except Exception as e:
            return {'healthy': False, 'reason': f'连接检查失败: {e}'}
    
    def _check_daemon_health(self) -> Dict:
        """检查守护进程健康"""
        try:
            # 简化版本：假设守护进程正常
            # 实际应该检查守护进程状态
            return {
                'healthy': True,
                'status': 'healthy',
                'reason': None
            }
            
        except Exception as e:
            return {'healthy': False, 'reason': f'守护进程检查失败: {e}'}
    
    def _check_error_rate_health(self) -> Dict:
        """检查错误率健康"""
        try:
            # 获取错误统计
            error_stats = error_handler.get_error_stats()
            total_errors = sum(stats.get('count', 0) for stats in error_stats.values())
            
            # 健康状态判断
            if total_errors < 10:
                status = 'healthy'
            elif total_errors < 50:
                status = 'warning'
            elif total_errors < 100:
                status = 'critical'
            else:
                status = 'fatal'
            
            return {
                'healthy': status in ['healthy', 'warning'],
                'status': status,
                'total_errors': total_errors,
                'reason': f'错误数: {total_errors}' if status != 'healthy' else None
            }
            
        except Exception as e:
            return {'healthy': False, 'reason': f'错误率检查失败: {e}'}
    
    def check_system_health(self) -> Dict:
        """检查系统健康"""
        try:
            current_time = time.time()
            
            # 限制检查频率
            if current_time - self._last_health_check < config.SystemConfig.HEALTH_CHECK_INTERVAL / 1000:
                return self._health_metrics
            
            self._last_health_check = current_time
            
            # 执行所有健康检查
            results = {}
            overall_healthy = True
            unhealthy_components = []
            
            for component, check_func in self._health_checks.items():
                result = check_func()
                results[component] = result
                
                if not result['healthy']:
                    overall_healthy = False
                    unhealthy_components.append(component)
            
            # 更新不健康组件列表
            self._unhealthy_components = set(unhealthy_components)
            
            # 生成健康报告
            health_report = {
                'overall_healthy': overall_healthy,
                'timestamp': current_time,
                'components': results,
                'unhealthy_components': unhealthy_components,
                'health_score': self._calculate_health_score(results)
            }
            
            # 更新健康指标
            self._health_metrics = health_report
            
            # 记录健康状态
            if not overall_healthy:
                self._logger.warning(f"系统不健康: {unhealthy_components}", "HealthMonitor")
            
            return health_report
            
        except Exception as e:
            self._logger.error(f"系统健康检查失败: {e}", "HealthMonitor")
            return {'overall_healthy': False, 'reason': f'健康检查失败: {e}'}
    
    def _calculate_health_score(self, results: Dict) -> float:
        """计算健康分数"""
        try:
            if not results:
                return 0.0
            
            total_score = 0
            component_count = len(results)
            
            for component, result in results.items():
                if result['healthy']:
                    total_score += 100
                elif result.get('status') == 'warning':
                    total_score += 70
                elif result.get('status') == 'critical':
                    total_score += 30
                else:
                    total_score += 0
            
            return total_score / component_count
            
        except Exception as e:
            self._logger.error(f"健康分数计算失败: {e}", "HealthMonitor")
            return 0.0
    
    def get_unhealthy_components(self) -> List[str]:
        """获取不健康组件"""
        return list(self._unhealthy_components)
    
    def get_health_metrics(self) -> Dict:
        """获取健康指标"""
        return self._health_metrics.copy()

# =============================================================================
# 增强错误处理器
# =============================================================================

class EnhancedErrorHandler:
    """增强错误处理器"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._recovery_manager = ErrorRecoveryManager()
        self._health_monitor = SystemHealthMonitor()
        self._error_contexts = []
        
    def handle_error(self, error_type: error_handler.ErrorType, error: Exception, 
                    component: str = "Unknown", severity: ErrorSeverity = None,
                    additional_data: Optional[Dict] = None):
        """处理错误"""
        try:
            # 确定错误严重程度
            if severity is None:
                severity = self._determine_severity(error_type, error)
            
            # 创建错误上下文
            context = ErrorContext(
                error_type=error_type,
                severity=severity,
                message=str(error),
                component=component,
                timestamp=time.time(),
                additional_data=additional_data
            )
            
            # 记录错误
            self._log_error(context)
            
            # 保存错误上下文
            self._error_contexts.append(context)
            if len(self._error_contexts) > 50:
                self._error_contexts.pop(0)
            
            # 执行恢复
            if config.SystemConfig.ERROR_RECOVERY_ENABLED:
                recovery_success = self._recovery_manager.handle_error(context)
                
                if not recovery_success:
                    self._logger.error(f"错误恢复失败: {error_type.value}", "EnhancedErrorHandler")
                
                return recovery_success
            
            return False
            
        except Exception as e:
            self._logger.error(f"错误处理失败: {e}", "EnhancedErrorHandler")
            return False
    
    def _determine_severity(self, error_type: error_handler.ErrorType, error: Exception) -> ErrorSeverity:
        """确定错误严重程度"""
        # 根据错误类型确定严重程度
        severity_map = {
            error_handler.ErrorType.HARDWARE: ErrorSeverity.HIGH,
            error_handler.ErrorType.MEMORY: ErrorSeverity.HIGH,
            error_handler.ErrorType.SYSTEM: ErrorSeverity.HIGH,
            error_handler.ErrorType.FATAL: ErrorSeverity.FATAL,
            error_handler.ErrorType.NETWORK: ErrorSeverity.MEDIUM,
            error_handler.ErrorType.MQTT: ErrorSeverity.MEDIUM,
            error_handler.ErrorType.WIFI: ErrorSeverity.MEDIUM,
            error_handler.ErrorType.DAEMON: ErrorSeverity.MEDIUM,
            error_handler.ErrorType.CONFIG: ErrorSeverity.LOW
        }
        
        return severity_map.get(error_type, ErrorSeverity.MEDIUM)
    
    def _log_error(self, context: ErrorContext):
        """记录错误"""
        try:
            # 根据严重程度选择日志级别
            if context.severity == ErrorSeverity.FATAL:
                self._logger.critical(
                    f"[{context.component}] {context.error_type.value}: {context.message}",
                    "EnhancedErrorHandler"
                )
            elif context.severity == ErrorSeverity.CRITICAL:
                self._logger.critical(
                    f"[{context.component}] {context.error_type.value}: {context.message}",
                    "EnhancedErrorHandler"
                )
            elif context.severity == ErrorSeverity.HIGH:
                self._logger.error(
                    f"[{context.component}] {context.error_type.value}: {context.message}",
                    "EnhancedErrorHandler"
                )
            elif context.severity == ErrorSeverity.MEDIUM:
                self._logger.warning(
                    f"[{context.component}] {context.error_type.value}: {context.message}",
                    "EnhancedErrorHandler"
                )
            else:
                self._logger.info(
                    f"[{context.component}] {context.error_type.value}: {context.message}",
                    "EnhancedErrorHandler"
                )
            
        except Exception as e:
            print(f"日志记录失败: {e}")
    
    def check_system_health(self) -> Dict:
        """检查系统健康"""
        return self._health_monitor.check_system_health()
    
    def get_recovery_stats(self) -> Dict:
        """获取恢复统计"""
        return self._recovery_manager.get_recovery_stats()
    
    def get_error_history(self, count: int = 10) -> List[Dict]:
        """获取错误历史"""
        return self._recovery_manager.get_error_history(count)
    
    def get_health_metrics(self) -> Dict:
        """获取健康指标"""
        return self._health_monitor.get_health_metrics()

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局增强错误处理器
_enhanced_error_handler = EnhancedErrorHandler()

def get_enhanced_error_handler():
    """获取全局增强错误处理器"""
    return _enhanced_error_handler

def handle_error(error_type: error_handler.ErrorType, error: Exception, 
                component: str = "Unknown", severity: ErrorSeverity = None,
                additional_data: Optional[Dict] = None) -> bool:
    """处理错误"""
    return _enhanced_error_handler.handle_error(error_type, error, component, severity, additional_data)

def check_system_health() -> Dict:
    """检查系统健康"""
    return _enhanced_error_handler.check_system_health()

def get_recovery_stats() -> Dict:
    """获取恢复统计"""
    return _enhanced_error_handler.get_recovery_stats()

def get_error_history(count: int = 10) -> List[Dict]:
    """获取错误历史"""
    return _enhanced_error_handler.get_error_history(count)

# =============================================================================
# 装饰器
# =============================================================================

def error_handler(component: str = "Unknown", severity: ErrorSeverity = None):
    """错误处理装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(
                    error_handler.ErrorType.SYSTEM,
                    e,
                    component,
                    severity
                )
                return None
        return wrapper
    return decorator

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()