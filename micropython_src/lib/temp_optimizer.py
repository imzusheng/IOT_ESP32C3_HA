# temp_optimizer.py
"""
温度优化策略模块

从main.py中分离出来的温度优化逻辑，提供：
- 温度分级管理
- 动态配置优化
- 温度阈值检查
- 优化建议生成
"""

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
        'scheduler_interval_ms': 200,
        'pwm_freq': 60,
        'max_brightness': 20000,
        'led_interval_ms': 50,
        'wifi_check_interval_s': 30,
    },
    'warning': {
        'main_interval_ms': 8000,
        'monitor_interval_ms': 45000,
        'scheduler_interval_ms': 400,
        'pwm_freq': 40,
        'max_brightness': 15000,
        'led_interval_ms': 80,
        'wifi_check_interval_s': 45,
    },
    'critical': {
        'main_interval_ms': 10000,
        'monitor_interval_ms': 60000,
        'scheduler_interval_ms': 800,
        'pwm_freq': 30,
        'max_brightness': 8000,
        'led_interval_ms': 100,
        'wifi_check_interval_s': 60,
    },
    'emergency': {
        'main_interval_ms': 15000,
        'monitor_interval_ms': 120000,
        'scheduler_interval_ms': 1500,
        'pwm_freq': 20,
        'max_brightness': 3000,
        'led_interval_ms': 200,
        'wifi_check_interval_s': 300,
    }
}

def get_temperature_level(current_temp):
    """根据当前温度确定温度级别"""
    if current_temp >= TEMP_THRESHOLDS['emergency']:
        return 'emergency'
    elif current_temp >= TEMP_THRESHOLDS['critical']:
        return 'critical'
    elif current_temp >= TEMP_THRESHOLDS['warning']:
        return 'warning'
    else:
        return 'normal'

def get_optimized_config_for_temp(current_temp):
    """根据当前温度获取优化后的配置"""
    temp_level = get_temperature_level(current_temp)
    return TEMP_LEVEL_CONFIGS[temp_level].copy()

def check_and_optimize(current_temp):
    """检查温度并返回优化信息"""
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
            "调度器间隔调整到400ms"
        ])
    elif temp_level == 'critical':
        optimization_info['recommendations'].extend([
            "降低LED亮度到40%",
            "延长监控间隔到60秒",
            "调度器间隔调整到800ms"
        ])
    elif temp_level == 'emergency':
        optimization_info['recommendations'].extend([
            "紧急降低LED亮度到15%",
            "延长监控间隔到120秒",
            "调度器间隔调整到1.5秒"
        ])
    
    return optimization_info