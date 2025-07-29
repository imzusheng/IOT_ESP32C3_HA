# temp_optimization.py
"""
温度优化配置模块

针对ESP32C3运行时温度过高（39°C）问题的专项优化配置。
这个模块提供了一系列温度优化策略和动态调整机制。

优化策略：
1. 动态频率调整 - 根据温度动态调整任务频率
2. 功耗管理 - 降低PWM频率和LED亮度
3. 任务调度优化 - 延长监控间隔，减少CPU负载
4. 热保护机制 - 更严格的温度阈值和保护措施
"""

import time
from config import DAEMON_CONFIG, SAFETY_CONFIG, PWM_FREQ, MAX_BRIGHTNESS

# =============================================================================
# 温度优化配置
# =============================================================================

# 优化后的守护进程配置（低功耗模式）
OPTIMIZED_DAEMON_CONFIG = {
    # 主循环间隔延长到8秒，减少CPU使用
    'main_interval_ms': 8000,
    
    # 看门狗间隔延长到8秒
    'watchdog_interval_ms': 8000,
    
    # 监控间隔延长到60秒，减少传感器读取频率
    'monitor_interval_ms': 60000,
    
    # 性能报告间隔延长到60秒
    'perf_report_interval_s': 60,
}

# 优化后的安全配置（更严格的温度保护）
OPTIMIZED_SAFETY_CONFIG = {
    # 降低温度阈值到40°C，更早触发保护
    'temperature_threshold': 40.0,
    
    # 看门狗超时时间保持不变
    'wdt_timeout_ms': 10000,
    
    # 安全模式闪烁间隔延长，减少功耗
    'blink_interval_ms': 500,
    
    # 冷却时间延长到10秒
    'safe_mode_cooldown_ms': 10000,
    
    # 其他配置保持不变
    'max_error_count': 10,
    'error_reset_interval_ms': 60000,
    'max_recovery_attempts': 5,
}

# 优化后的LED配置（低功耗模式）
OPTIMIZED_LED_CONFIG = {
    # 降低PWM频率到30Hz，减少电流消耗
    'pwm_freq': 30,
    
    # 降低最大亮度到50%，减少功耗
    'max_brightness': 10000,
    
    # 增大渐变步长，减少PWM更新频率
    'fade_step': 512,
}

# 温度分级配置
TEMP_THRESHOLDS = {
    'normal': 35.0,      # 正常温度阈值
    'warning': 40.0,     # 警告温度阈值
    'critical': 45.0,    # 危险温度阈值
    'emergency': 50.0,   # 紧急温度阈值
}

# 不同温度级别的配置调整
TEMP_LEVEL_CONFIGS = {
    'normal': {
        'main_interval_ms': 5000,
        'monitor_interval_ms': 30000,
        'pwm_freq': 60,
        'max_brightness': 20000,
        'led_interval_ms': 50,
        'wifi_check_interval_s': 30,
    },
    'warning': {
        'main_interval_ms': 8000,
        'monitor_interval_ms': 45000,
        'pwm_freq': 40,
        'max_brightness': 15000,
        'led_interval_ms': 80,
        'wifi_check_interval_s': 45,
    },
    'critical': {
        'main_interval_ms': 10000,
        'monitor_interval_ms': 60000,
        'pwm_freq': 30,
        'max_brightness': 8000,
        'led_interval_ms': 100,
        'wifi_check_interval_s': 60,
    },
    'emergency': {
        'main_interval_ms': 15000,
        'monitor_interval_ms': 120000,
        'pwm_freq': 20,
        'max_brightness': 3000,
        'led_interval_ms': 200,
        'wifi_check_interval_s': 300,
    }
}

# =============================================================================
# 温度优化函数
# =============================================================================

def get_temperature_level(current_temp):
    """
    根据当前温度确定温度级别
    
    Args:
        current_temp (float): 当前温度
        
    Returns:
        str: 温度级别 ('normal', 'warning', 'critical', 'emergency')
    """
    if current_temp >= TEMP_THRESHOLDS['emergency']:
        return 'emergency'
    elif current_temp >= TEMP_THRESHOLDS['critical']:
        return 'critical'
    elif current_temp >= TEMP_THRESHOLDS['warning']:
        return 'warning'
    else:
        return 'normal'

def get_optimized_config_for_temp(current_temp):
    """
    根据当前温度获取优化后的配置
    
    Args:
        current_temp (float): 当前温度
        
    Returns:
        dict: 优化后的配置字典
    """
    temp_level = get_temperature_level(current_temp)
    return TEMP_LEVEL_CONFIGS[temp_level].copy()

def apply_temperature_optimization(current_temp):
    """
    应用温度优化策略
    
    Args:
        current_temp (float): 当前温度
        
    Returns:
        dict: 包含优化建议的字典
    """
    temp_level = get_temperature_level(current_temp)
    optimized_config = get_optimized_config_for_temp(current_temp)
    
    optimization_info = {
        'current_temp': current_temp,
        'temp_level': temp_level,
        'optimized_config': optimized_config,
        'recommendations': []
    }
    
    # 根据温度级别添加建议
    if temp_level == 'warning':
        optimization_info['recommendations'].extend([
            "降低LED亮度到75%",
            "延长监控间隔到45秒",
            "降低PWM频率到40Hz",
            "延长LED更新间隔到80ms",
            "延长WiFi检查间隔到45秒"
        ])
    elif temp_level == 'critical':
        optimization_info['recommendations'].extend([
            "降低LED亮度到40%",
            "延长监控间隔到60秒",
            "降低PWM频率到30Hz",
            "延长主循环间隔到10秒",
            "延长LED更新间隔到100ms",
            "延长WiFi检查间隔到60秒"
        ])
    elif temp_level == 'emergency':
        optimization_info['recommendations'].extend([
            "降低LED亮度到15%",
            "延长监控间隔到120秒",
            "降低PWM频率到20Hz",
            "延长主循环间隔到15秒",
            "延长LED更新间隔到200ms",
            "延长WiFi检查间隔到300秒",
            "考虑进入深度睡眠模式"
        ])
    
    return optimization_info

def get_power_saving_config():
    """
    获取节能配置
    
    Returns:
        dict: 节能配置字典
    """
    return {
        'daemon_config': OPTIMIZED_DAEMON_CONFIG.copy(),
        'safety_config': OPTIMIZED_SAFETY_CONFIG.copy(),
        'led_config': OPTIMIZED_LED_CONFIG.copy(),
    }

def log_temperature_optimization(current_temp, optimization_info):
    """
    记录温度优化信息
    
    Args:
        current_temp (float): 当前温度
        optimization_info (dict): 优化信息
    """
    print(f"[TEMP_OPT] 当前温度: {current_temp}°C")
    print(f"[TEMP_OPT] 温度级别: {optimization_info['temp_level']}")
    
    if optimization_info['recommendations']:
        print("[TEMP_OPT] 优化建议:")
        for rec in optimization_info['recommendations']:
            print(f"[TEMP_OPT]   - {rec}")

# =============================================================================
# 温度监控和自动优化类
# =============================================================================

class TemperatureOptimizer:
    """
    温度优化器类
    
    自动监控温度并应用相应的优化策略
    """
    
    def __init__(self):
        self.last_temp_check = 0
        self.current_temp_level = 'normal'
        self.optimization_history = []
        
    def check_and_optimize(self, current_temp):
        """
        检查温度并应用优化
        
        Args:
            current_temp (float): 当前温度
            
        Returns:
            dict: 优化结果
        """
        current_time = time.time()
        
        # 记录温度检查时间
        self.last_temp_check = current_time
        
        # 获取优化信息
        optimization_info = apply_temperature_optimization(current_temp)
        
        # 检查温度级别是否发生变化
        new_temp_level = optimization_info['temp_level']
        if new_temp_level != self.current_temp_level:
            print(f"[TEMP_OPT] 温度级别变化: {self.current_temp_level} -> {new_temp_level}")
            self.current_temp_level = new_temp_level
            
            # 记录优化历史
            self.optimization_history.append({
                'timestamp': current_time,
                'temp': current_temp,
                'level': new_temp_level,
                'config': optimization_info['optimized_config']
            })
            
            # 保持历史记录不超过10条
            if len(self.optimization_history) > 10:
                self.optimization_history.pop(0)
        
        # 记录优化信息
        log_temperature_optimization(current_temp, optimization_info)
        
        return optimization_info
    
    def get_current_optimization_level(self):
        """
        获取当前优化级别
        
        Returns:
            str: 当前温度级别
        """
        return self.current_temp_level
    
    def get_optimization_history(self):
        """
        获取优化历史
        
        Returns:
            list: 优化历史列表
        """
        return self.optimization_history.copy()

# 全局温度优化器实例
temp_optimizer = TemperatureOptimizer()

# =============================================================================
# 模块测试
# =============================================================================

if __name__ == "__main__":
    # 测试温度优化功能
    test_temps = [35.0, 39.0, 42.0, 47.0, 52.0]
    
    print("[TEMP_OPT] 温度优化测试开始")
    
    for temp in test_temps:
        print(f"\n[TEMP_OPT] 测试温度: {temp}°C")
        optimization_info = temp_optimizer.check_and_optimize(temp)
        
        print(f"[TEMP_OPT] 优化配置:")
        for key, value in optimization_info['optimized_config'].items():
            print(f"[TEMP_OPT]   {key}: {value}")
    
    print("\n[TEMP_OPT] 温度优化测试完成")
    print(f"[TEMP_OPT] 优化历史记录数: {len(temp_optimizer.get_optimization_history())}")