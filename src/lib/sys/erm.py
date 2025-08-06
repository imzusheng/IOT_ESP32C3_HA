# -*- coding: utf-8 -*-
"""
错误恢复管理模块 Error Recovery Module

为ESP32C3设备提供集中化的错误处理和恢复策略管理：
- 错误恢复策略统一管理
- 自动恢复机制
- 恢复成功率统计
- 智能恢复调度

恢复策略说明：
- 网络错误：重连 + 内存清理
- 内存错误：深度清理 + 重启服务
- 硬件错误：重启系统
- 系统错误：分步恢复
- 配置错误：使用默认配置
"""

import time
import gc
import machine
from lib.sys import logger as logger
import sys_daemon
from lib.sys import fsm as fsm
from lib.sys import memo as object_pool
import utils

# =============================================================================
# 恢复策略配置
# =============================================================================

class RecoveryConfig:
    """恢复配置常量"""
    # 重试配置
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_BASE = 1000  # 基础延迟1秒
    
    # 超时配置
    NETWORK_TIMEOUT = 30000  # 网络重连超时30秒
    MEMORY_CLEANUP_TIMEOUT = 10000  # 内存清理超时10秒
    SERVICE_RESTART_TIMEOUT = 15000  # 服务重启超时15秒
    
    # 冷却时间
    RECOVERY_COOLDOWN = 30000  # 恢复操作冷却时间30秒
    ERROR_RESET_COOLDOWN = 60000  # 错误计数重置冷却时间60秒

# =============================================================================
# 恢复动作类
# =============================================================================

class EnhancedRecoveryAction:
    """增强恢复动作基类"""
    
    def __init__(self, name: str, strategy: str, priority: int = 1):
        self.name = name
        self.strategy = strategy
        self.priority = priority
        self.execution_count = 0
        self.success_count = 0
        self.last_execution = 0
        self.last_success = 0
        self.cooldown_until = 0
        
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        current_time = time.ticks_ms()
        return time.ticks_diff(current_time, self.cooldown_until) > 0
    
    def execute(self, error_type: str, error_data: dict = None) -> bool:
        """执行恢复动作"""
        if not self.can_execute():
            return False
            
        try:
            self.execution_count += 1
            self.last_execution = time.time()
            
            result = self._execute_action(error_type, error_data or {})
            
            if result:
                self.success_count += 1
                self.last_success = time.time()
                self._set_cooldown()
            
            return result
            
        except Exception as e:
            print(f"[Recovery] {self.name} 执行异常: {e}")
            return False
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """子类实现具体恢复逻辑"""
        raise NotImplementedError
    
    def _set_cooldown(self):
        """设置冷却时间"""
        self.cooldown_until = time.ticks_ms() + RecoveryConfig.RECOVERY_COOLDOWN
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.execution_count == 0:
            return 0.0
        return self.success_count / self.execution_count
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'name': self.name,
            'strategy': self.strategy,
            'priority': self.priority,
            'execution_count': self.execution_count,
            'success_count': self.success_count,
            'success_rate': self.get_success_rate(),
            'last_execution': self.last_execution,
            'last_success': self.last_success,
            'can_execute': self.can_execute()
        }

class NetworkRecoveryAction(EnhancedRecoveryAction):
    """网络恢复动作"""
    
    def __init__(self):
        super().__init__("网络恢复", "NETWORK_RECOVERY", priority=1)
        self.max_retries = RecoveryConfig.MAX_RETRY_ATTEMPTS
        self.retry_delay = RecoveryConfig.RETRY_DELAY_BASE
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """执行网络恢复"""
        print("[Recovery] 开始网络恢复...")
        
        # 导入网络模块
        try:
            import net_wifi
            import net_mqtt
        except ImportError:
            print("[Recovery] 网络模块导入失败")
            return False
        
        # 执行网络重连
        for attempt in range(self.max_retries):
            try:
                print(f"[Recovery] 网络重连尝试 {attempt + 1}/{self.max_retries}")
                
                # 重连WiFi
                wifi_connected = net_wifi.connect_wifi()
                if not wifi_connected:
                    time.sleep_ms(self.retry_delay)
                    continue
                
                # 重连MQTT（如果有MQTT客户端）
                mqtt_client = error_data.get('mqtt_client')
                if mqtt_client and hasattr(mqtt_client, 'connect'):
                    if not mqtt_client.connect():
                        time.sleep_ms(self.retry_delay)
                        continue
                
                print("[Recovery] 网络恢复成功")
                return True
                
            except Exception as e:
                print(f"[Recovery] 网络重连异常: {e}")
                time.sleep_ms(self.retry_delay)
        
        print("[Recovery] 网络恢复失败")
        return False

class MemoryRecoveryAction(EnhancedRecoveryAction):
    """内存恢复动作"""
    
    def __init__(self):
        super().__init__("内存恢复", "MEMORY_RECOVERY", priority=2)
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """执行内存恢复"""
        print("[Recovery] 开始内存恢复...")
        
        try:
            # 使用对象池的内存优化器
            memory_info = utils.check_memory()
            if memory_info:
                print(f"[Recovery] 当前内存使用: {memory_info['percent']:.1f}%")
            
            # 执行深度垃圾回收
            for _ in range(3):
                gc.collect()
                time.sleep_ms(100)
            
            # 清理对象池
            object_pool.clear_all_pools()
            
            # 重新初始化核心对象池
            from lib.sys import memo as op_module
            op_module._dict_pool = op_module.DictPool(pool_size=3)
            op_module._string_cache = op_module.StringCache(max_size=30)
            op_module._buffer_manager = op_module.BufferManager()
            
            # 清理错误历史
            try:
                logger.reset_error_stats()
            except:
                pass
            
            # 验证恢复效果
            final_memory = utils.check_memory()
            if final_memory:
                print(f"[Recovery] 内存恢复完成，使用率: {final_memory['percent']:.1f}%")
                return final_memory['percent'] < 85  # 内存使用率低于85%认为恢复成功
            
            return True
            
        except Exception as e:
            print(f"[Recovery] 内存恢复异常: {e}")
            return False

class ServiceRecoveryAction(EnhancedRecoveryAction):
    """服务恢复动作"""
    
    def __init__(self):
        super().__init__("服务恢复", "SERVICE_RECOVERY", priority=3)
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """执行服务恢复"""
        print("[Recovery] 开始服务恢复...")
        
        try:
            # 重启守护进程
            sys_daemon.stop_daemon()
            time.sleep_ms(1000)
            
            daemon_started = sys_daemon.start_daemon()
            if not daemon_started:
                print("[Recovery] 守护进程重启失败")
                return False
            
            # 重置MQTT客户端连接
            mqtt_client = error_data.get('mqtt_client')
            if mqtt_client and hasattr(mqtt_client, 'connect'):
                mqtt_client.connect()
            
            print("[Recovery] 服务恢复成功")
            return True
            
        except Exception as e:
            print(f"[Recovery] 服务恢复异常: {e}")
            return False

class SystemRecoveryAction(EnhancedRecoveryAction):
    """系统恢复动作"""
    
    def __init__(self):
        super().__init__("系统恢复", "SYSTEM_RECOVERY", priority=4)
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """执行系统恢复"""
        print("[Recovery] 开始系统恢复...")
        
        try:
            # 尝试状态机恢复
            sm = fsm.get_state_machine()
            
            # 根据错误类型选择恢复策略
            if error_type in ["MEMORY_ERROR", "CRITICAL_ERROR"]:
                # 强制进入安全模式
                sys_daemon.force_safe_mode(f"系统恢复: {error_type}")
                fsm.handle_event(fsm.StateEvent.MEMORY_CRITICAL)
                return True
            else:
                # 尝试正常恢复
                fsm.handle_event(fsm.StateEvent.RECOVERY_SUCCESS)
                return True
                
        except Exception as e:
            print(f"[Recovery] 系统恢复异常: {e}")
            return False

class HardwareRecoveryAction(EnhancedRecoveryAction):
    """硬件恢复动作"""
    
    def __init__(self):
        super().__init__("硬件恢复", "HARDWARE_RECOVERY", priority=5)
    
    def _execute_action(self, error_type: str, error_data: dict) -> bool:
        """执行硬件恢复"""
        print("[Recovery] 开始硬件恢复...")
        
        try:
            # 硬件错误通常需要重启系统
            print("[Recovery] 硬件错误，准备重启系统...")
            
            # 记录重启原因
            if error_data.get('mqtt_client'):
                try:
                    error_data['mqtt_client'].log("CRITICAL", f"硬件恢复: 系统重启 - {error_type}")
                except:
                    pass
            
            # 延迟重启
            time.sleep_ms(2000)
            
            # 系统重启
            machine.reset()
            
            return True  # 理论上不会执行到这里
            
        except Exception as e:
            print(f"[Recovery] 硬件恢复异常: {e}")
            return False

# =============================================================================
# 恢复管理器类
# =============================================================================

class RecoveryManager:
    """恢复管理器"""
    
    def __init__(self):
        """初始化恢复管理器"""
        self.recovery_actions = {}
        self.recovery_history = []
        self.max_history = 20
        self.error_recovery_counts = {}
        self.last_recovery_time = {}
        
        # 注册恢复动作
        self._register_recovery_actions()
        
        print("[RecoveryManager] 恢复管理器初始化完成")
    
    def _register_recovery_actions(self):
        """注册恢复动作"""
        self.recovery_actions = {
            'NETWORK_ERROR': [
                NetworkRecoveryAction(),
                MemoryRecoveryAction(),
                ServiceRecoveryAction()
            ],
            'MEMORY_ERROR': [
                MemoryRecoveryAction(),
                ServiceRecoveryAction(),
                SystemRecoveryAction()
            ],
            'HARDWARE_ERROR': [
                HardwareRecoveryAction()
            ],
            'SYSTEM_ERROR': [
                MemoryRecoveryAction(),
                ServiceRecoveryAction(),
                SystemRecoveryAction()
            ],
            'MQTT_ERROR': [
                NetworkRecoveryAction(),
                MemoryRecoveryAction()
            ],
            'WIFI_ERROR': [
                NetworkRecoveryAction(),
                MemoryRecoveryAction()
            ],
            'DAEMON_ERROR': [
                ServiceRecoveryAction(),
                MemoryRecoveryAction()
            ],
            'CONFIG_ERROR': [
                SystemRecoveryAction()
            ],
            'FATAL_ERROR': [
                SystemRecoveryAction(),
                HardwareRecoveryAction()
            ]
        }
    
    def handle_error(self, error_type: str, error: Exception, context: str = "", 
                    severity: str = "MEDIUM", error_data: dict = None) -> bool:
        """处理错误并执行恢复"""
        try:
            # 记录错误
            logger.handle_error(error_type, error, context, severity)
            
            # 准备恢复数据
            recovery_data = error_data or {}
            recovery_data.update({
                'error_type': error_type,
                'error_message': str(error),
                'context': context,
                'severity': severity,
                'timestamp': time.time()
            })
            
            # 执行恢复
            recovery_success = self._execute_recovery(error_type, recovery_data)
            
            # 记录恢复历史
            self._record_recovery_attempt(error_type, recovery_success, recovery_data)
            
            return recovery_success
            
        except Exception as e:
            print(f"[RecoveryManager] 错误处理异常: {e}")
            return False
    
    def _execute_recovery(self, error_type: str, error_data: dict) -> bool:
        """执行恢复动作"""
        # 获取该错误类型的恢复动作
        actions = self.recovery_actions.get(error_type, [])
        
        if not actions:
            print(f"[RecoveryManager] 没有找到 {error_type} 的恢复动作")
            return False
        
        # 按优先级排序
        actions.sort(key=lambda x: x.priority)
        
        # 尝试执行恢复动作
        for action in actions:
            try:
                print(f"[RecoveryManager] 尝试恢复动作: {action.name}")
                
                if action.execute(error_type, error_data):
                    print(f"[RecoveryManager] 恢复动作成功: {action.name}")
                    return True
                else:
                    print(f"[RecoveryManager] 恢复动作失败: {action.name}")
                    
            except Exception as e:
                print(f"[RecoveryManager] 恢复动作异常: {action.name} - {e}")
        
        print(f"[RecoveryManager] 所有恢复动作失败: {error_type}")
        return False
    
    def _record_recovery_attempt(self, error_type: str, success: bool, error_data: dict):
        """记录恢复尝试"""
        # 更新错误恢复计数
        if error_type not in self.error_recovery_counts:
            self.error_recovery_counts[error_type] = {'total': 0, 'success': 0}
        
        self.error_recovery_counts[error_type]['total'] += 1
        if success:
            self.error_recovery_counts[error_type]['success'] += 1
        
        # 记录恢复历史
        recovery_record = {
            'error_type': error_type,
            'success': success,
            'timestamp': time.time(),
            'error_data': error_data
        }
        
        self.recovery_history.append(recovery_record)
        
        # 保持历史记录大小
        if len(self.recovery_history) > self.max_history:
            self.recovery_history.pop(0)
        
        # 更新最后恢复时间
        self.last_recovery_time[error_type] = time.time()
    
    def get_recovery_stats(self) -> dict:
        """获取恢复统计信息"""
        stats = {
            'error_recovery_counts': self.error_recovery_counts.copy(),
            'action_stats': {},
            'recent_history': self.recovery_history[-5:] if self.recovery_history else []
        }
        
        # 收集所有动作的统计信息
        for error_type, actions in self.recovery_actions.items():
            for action in actions:
                if action.name not in stats['action_stats']:
                    stats['action_stats'][action.name] = action.get_stats()
        
        return stats
    
    def get_recovery_success_rate(self, error_type: str = None) -> float:
        """获取恢复成功率"""
        if error_type:
            counts = self.error_recovery_counts.get(error_type, {})
            total = counts.get('total', 0)
            success = counts.get('success', 0)
            return success / total if total > 0 else 0.0
        else:
            # 总体成功率
            total_attempts = sum(counts['total'] for counts in self.error_recovery_counts.values())
            total_success = sum(counts['success'] for counts in self.error_recovery_counts.values())
            return total_success / total_attempts if total_attempts > 0 else 0.0
    
    def can_attempt_recovery(self, error_type: str) -> bool:
        """检查是否可以尝试恢复"""
        # 检查冷却时间
        last_time = self.last_recovery_time.get(error_type, 0)
        current_time = time.time()
        
        if current_time - last_time < RecoveryConfig.RECOVERY_COOLDOWN / 1000:
            return False
        
        # 检查是否有可用的恢复动作
        actions = self.recovery_actions.get(error_type, [])
        return any(action.can_execute() for action in actions)
    
    def reset_recovery_stats(self):
        """重置恢复统计"""
        self.error_recovery_counts.clear()
        self.recovery_history.clear()
        self.last_recovery_time.clear()
        
        # 重置所有动作的统计
        for actions in self.recovery_actions.values():
            for action in actions:
                action.execution_count = 0
                action.success_count = 0
                action.last_execution = 0
                action.last_success = 0
                action.cooldown_until = 0
        
        print("[RecoveryManager] 恢复统计已重置")

# =============================================================================
# 全局恢复管理器实例
# =============================================================================

# 创建全局恢复管理器实例
_recovery_manager = RecoveryManager()

def get_recovery_manager():
    """获取全局恢复管理器实例"""
    return _recovery_manager

def handle_error_with_recovery(error_type: str, error: Exception, context: str = "", 
                              severity: str = "MEDIUM", error_data: dict = None) -> bool:
    """处理错误并执行恢复的便捷函数"""
    return _recovery_manager.handle_error(error_type, error, context, severity, error_data)

def get_recovery_stats():
    """获取恢复统计的便捷函数"""
    return _recovery_manager.get_recovery_stats()

def get_recovery_success_rate(error_type: str = None):
    """获取恢复成功率的便捷函数"""
    return _recovery_manager.get_recovery_success_rate(error_type)

def can_attempt_recovery(error_type: str):
    """检查是否可以尝试恢复的便捷函数"""
    return _recovery_manager.can_attempt_recovery(error_type)

def reset_recovery_stats():
    """重置恢复统计的便捷函数"""
    _recovery_manager.reset_recovery_stats()

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()

print("[RecoveryManager] 错误恢复管理模块加载完成")