# -*- coding: utf-8 -*-
"""
简化状态监控模块

为ESP32C3设备提供轻量级的状态监控功能：
- 系统状态监控
- 组件健康检查
- 内存监控
- 简化的日志系统

内存优化说明：
- 简化数据结构，减少内存占用
- 移除复杂的历史记录功能
- 限制监控频率
- 使用轻量级日志缓冲
"""

import time
import gc
from enum import Enum

# =============================================================================
# 状态类型定义
# =============================================================================

class SystemStatus(Enum):
    """系统状态"""
    BOOTING = "BOOTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    EMERGENCY = "EMERGENCY"

# =============================================================================
# 系统监控器类
# =============================================================================

class SystemMonitor:
    """系统监控器"""
    
    def __init__(self):
        self._status = SystemStatus.BOOTING
        self._last_update = time.time()
        self._log_buffer = deque(maxlen=20)  # 减小日志缓冲区
        self._start_time = time.time()
    
    def update_status(self) -> Dict[str, Any]:
        """更新系统状态"""
        try:
            current_time = time.time()
            
            # 限制更新频率（每30秒更新一次）
            if current_time - self._last_update < 30:
                return self.get_current_status()
            
            # 执行健康检查
            health = self._perform_health_check()
            
            # 更新系统状态
            self._status = self._determine_status(health)
            self._last_update = current_time
            
            # 记录状态日志
            self._log_status_change()
            
            return self.get_current_status()
            
        except Exception as e:
            self._log(f"状态更新失败: {e}", "ERROR")
            return self.get_current_status()
    
    def _perform_health_check(self) -> Dict[str, Any]:
        """执行系统健康检查"""
        health = {
            'memory_ok': True,
            'temperature_ok': True,
            'errors_ok': True,
            'details': {}
        }
        
        try:
            # 检查内存
            memory = self._get_memory_info()
            if memory:
                health['memory_ok'] = memory['percent'] < 85
                health['details']['memory'] = f"{memory['percent']:.1f}%"
                if not health['memory_ok']:
                    health['details']['memory_issue'] = "内存使用过高"
            
            # 检查温度（模拟）
            try:
                import esp32
                temp = esp32.mcu_temperature()
                health['temperature_ok'] = temp < 70  # ESP32C3最高85°C
                health['details']['temperature'] = f"{temp:.1f}°C"
                if not health['temperature_ok']:
                    health['details']['temperature_issue'] = "温度过高"
            except Exception:
                health['details']['temperature'] = "未知"
            
            # 检查错误计数
            try:
                import daemon
                daemon_status = daemon.get_daemon_status()
                error_count = daemon_status.get('error_count', 0)
                health['errors_ok'] = error_count < 10
                health['details']['errors'] = error_count
                if not health['errors_ok']:
                    health['details']['errors_issue'] = "错误过多"
            except Exception:
                health['details']['errors'] = "未知"
            
            return health
            
        except Exception as e:
            health['overall_error'] = str(e)
            return health
    
    def _get_memory_info(self) -> Optional[Dict[str, Any]]:
        """获取内存信息"""
        try:
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            
            if total == 0:
                return None
            
            return {
                'alloc': alloc,
                'free': free,
                'total': total,
                'percent': (alloc / total) * 100
            }
        except Exception:
            return None
    
    def _determine_status(self, health: Dict[str, Any]) -> SystemStatus:
        """根据健康检查结果确定系统状态"""
        try:
            # 计算健康指标数量
            healthy_count = sum([
                health['memory_ok'],
                health['temperature_ok'],
                health['errors_ok']
            ])
            
            # 根据健康指标数量确定状态
            if healthy_count == 3:
                return SystemStatus.HEALTHY
            elif healthy_count == 2:
                return SystemStatus.DEGRADED
            elif healthy_count == 1:
                return SystemStatus.UNHEALTHY
            else:
                return SystemStatus.EMERGENCY
                
        except Exception:
            return SystemStatus.UNHEALTHY
    
    def _log_status_change(self):
        """记录状态变更"""
        try:
            uptime = time.time() - self._start_time
            message = f"系统状态: {self._status.value}, 运行时间: {uptime:.0f}s"
            self._log(message, "INFO")
        except Exception:
            pass
    
    def _log(self, message: str, level: str = "INFO"):
        """记录日志"""
        try:
            log_entry = {
                'timestamp': time.time(),
                'level': level,
                'message': message
            }
            
            self._log_buffer.append(log_entry)
            
            # 控制台输出
            print(f"[{level}] {message}")
            
        except Exception:
            # 日志记录失败时不影响主功能
            pass
    
    def get_current_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        try:
            memory = self._get_memory_info()
            uptime = time.time() - self._start_time
            
            return {
                'status': self._status.value,
                'uptime': uptime,
                'memory': memory,
                'last_update': self._last_update,
                'is_healthy': self._status in [SystemStatus.HEALTHY, SystemStatus.DEGRADED]
            }
        except Exception:
            return {'status': self._status.value, 'error': '获取状态失败'}
    
    def get_recent_logs(self, count: int = 10) -> List[Dict]:
        """获取最近的日志"""
        return list(self._log_buffer)[-count:]
    
    def force_memory_cleanup(self) -> bool:
        """强制内存清理"""
        try:
            gc.collect()
            time.sleep_ms(100)
            gc.collect()
            self._log("执行内存清理", "INFO")
            return True
        except Exception:
            return False
    
    def get_health_summary(self) -> Dict[str, Any]:
        """获取健康状态摘要"""
        try:
            health = self._perform_health_check()
            status = self.get_current_status()
            
            return {
                'overall_status': status['status'],
                'is_healthy': status['is_healthy'],
                'health_details': health['details'],
                'uptime': status['uptime'],
                'memory_usage': status['memory']['percent'] if status['memory'] else None
            }
        except Exception as e:
            return {'error': str(e)}

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局系统监控器实例
_system_monitor = SystemMonitor()

def get_system_monitor():
    """获取系统监控器实例"""
    return _system_monitor

def update_system_status() -> Dict[str, Any]:
    """更新系统状态"""
    return _system_monitor.update_status()

def get_system_status() -> Dict[str, Any]:
    """获取系统状态"""
    return _system_monitor.get_current_status()

def get_health_summary() -> Dict[str, Any]:
    """获取健康状态摘要"""
    return _system_monitor.get_health_summary()

def get_recent_logs(count: int = 10) -> List[Dict]:
    """获取最近的日志"""
    return _system_monitor.get_recent_logs(count)

def force_memory_cleanup() -> bool:
    """强制内存清理"""
    return _system_monitor.force_memory_cleanup()

# =============================================================================
# 便捷日志函数
# =============================================================================

def log_info(message: str):
    """记录信息日志"""
    _system_monitor._log(message, "INFO")

def log_warning(message: str):
    """记录警告日志"""
    _system_monitor._log(message, "WARNING")

def log_error(message: str):
    """记录错误日志"""
    _system_monitor._log(message, "ERROR")

def log_critical(message: str):
    """记录严重错误日志"""
    _system_monitor._log(message, "CRITICAL")

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()