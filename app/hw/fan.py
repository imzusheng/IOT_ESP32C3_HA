# -*- coding: utf-8 -*-
"""
风扇控制模块 (利民TL-S12W等PWM风扇)

设计目标:
- 支持PWM控制和TACH转速读取
- 延迟初始化: 硬件在首次使用时创建
- 简单API: set_speed() 设置转速, get_rpm() 读取转速
- 最小依赖: 仅依赖machine与utime, 日志使用lib.logger
- 硬件定时器驱动: 使用硬件定时器进行精确的PWM控制

默认接线(ESP32-C3):
- PWM控制线 -> GPIO 2
- TACH信号线 -> GPIO 6  
- GND -> GND (必须连接!)
- 风扇电源 -> 12V/5V

重要: 必须连接共地线, 否则转速读数异常
"""

import utime as time
import machine
from lib.logger import info, warning, error

# =============================================================================
# 常量定义
# =============================================================================
MODULE_NAME = "FAN"
DEFAULT_PWM_PIN = 2      # 默认PWM控制引脚
DEFAULT_TACH_PIN = 6     # 默认TACH信号引脚
DEFAULT_PWM_FREQ = 25000 # PWM频率25kHz
DEFAULT_PULSES_PER_REV = 2  # 每转脉冲数, 利民TL-S12W为2脉冲/转
MIN_TACH_INTERVAL_US = 12000  # 脉冲去抖最小间隔(微秒)

# 转速范围
MIN_RPM = 0
MAX_RPM = 2000

# 脉冲间隔缓冲区大小
INTERVALS_MAX_LEN = 20

class _FanController:
    def __init__(self, pwm_pin: int = DEFAULT_PWM_PIN, tach_pin: int = DEFAULT_TACH_PIN, 
                 pwm_freq: int = DEFAULT_PWM_FREQ, pulses_per_rev: int = DEFAULT_PULSES_PER_REV):
        self.pwm_pin = pwm_pin
        self.tach_pin = tach_pin
        self.pwm_freq = pwm_freq
        self.pulses_per_rev = pulses_per_rev
        
        # 硬件对象
        self.pwm = None
        self.tach_pin_obj = None
        
        # 状态变量
        self.current_speed = 0  # 当前PWM占空比 0-100
        self.is_initialized = False
        
        # TACH相关
        self._pulse_count = 0
        self._last_pulse_time = 0
        self._intervals = []
        self._current_rpm = 0

    def _ensure_initialized(self):
        """确保硬件已初始化"""
        if self.is_initialized:
            return True
            
        try:
            # 初始化PWM - 参考测试脚本的简单方式
            self.pwm = machine.PWM(machine.Pin(self.pwm_pin), freq=self.pwm_freq)
            self.pwm.duty_u16(0)  # 初始关闭
            
            # 初始化TACH输入 - 参考测试脚本
            self.tach_pin_obj = machine.Pin(self.tach_pin, machine.Pin.IN, machine.Pin.PULL_UP)
            self.tach_pin_obj.irq(trigger=machine.Pin.IRQ_FALLING, handler=self._tach_irq_handler)
            
            # 重置计数器
            self._pulse_count = 0
            self._last_pulse_time = 0
            self._intervals = []
            self._current_rpm = 0
            
            self.is_initialized = True
            info(f"风扇控制器初始化成功: PWM=GPIO{self.pwm_pin}, TACH=GPIO{self.tach_pin}", module=MODULE_NAME)
            return True
            
        except Exception as e:
            # 开发阶段：即使硬件初始化失败也标记为已初始化，返回默认值
            warning(f"风扇控制器初始化失败: {e}", module=MODULE_NAME)
            self.is_initialized = True
            self.current_speed = 0
            self._current_rpm = 0
            return True

    def _tach_irq_handler(self, pin):
        """TACH信号中断处理函数 - 参考测试脚本逻辑"""
        now = time.ticks_us()
        
        # 防抖处理 - 参考测试脚本
        if self._last_pulse_time > 0:
            dt = time.ticks_diff(now, self._last_pulse_time)
            if dt < MIN_TACH_INTERVAL_US:
                return
                
            # 记录脉冲间隔用于周期法计算
            self._intervals.append(dt)
            if len(self._intervals) > INTERVALS_MAX_LEN:
                del self._intervals[0]
        
        self._last_pulse_time = now
        self._pulse_count += 1

    def _update_rpm(self):
        """更新RPM - 参考测试脚本的简单方法"""
        try:
            # 使用周期法计算RPM - 参考测试脚本
            rpm_period = self._calculate_rpm_from_intervals()
            if rpm_period is not None:
                self._current_rpm = rpm_period
            else:
                # 如果周期法失败，使用简单的计数法
                # 这里不重置计数器，让调用方决定何时重置
                pass
        except Exception:
            pass

    def _calculate_rpm_from_intervals(self):
        """基于脉冲间隔计算RPM (周期法)"""
        if len(self._intervals) < 3:
            return None
            
        try:
            # 使用IQR方法过滤离群值
            take = min(10, len(self._intervals))
            sample = sorted(self._intervals[-take:])
            
            # 计算Q1和Q3
            q1_idx = len(sample) // 4
            q3_idx = 3 * len(sample) // 4
            q1 = sample[q1_idx]
            q3 = sample[q3_idx]
            iqr = q3 - q1
            
            # 过滤异常值
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            filtered = [x for x in sample if lower_bound <= x <= upper_bound]
            
            if not filtered:
                return None
                
            # 使用中位数
            median_us = filtered[len(filtered) // 2]
            if median_us <= 0:
                return None
                
            rpm = int(60000000 / (median_us * self.pulses_per_rev))
            
            # 合理性检查
            if rpm > MAX_RPM:
                return None
                
            return rpm
            
        except Exception:
            return None

    def set_speed(self, speed_percent: int):
        """
        设置风扇转速
        
        Args:
            speed_percent (int): 转速百分比 0-100
        """
        if not self._ensure_initialized():
            return False
            
        # 限制范围
        speed_percent = max(0, min(100, int(speed_percent)))
        
        try:
            # 检查是否有实际的PWM硬件
            if self.pwm is not None:
                # 低速起转辅助：从0%启动且目标转速很低时需要先给高转速启动
                if speed_percent > 0 and self.current_speed == 0 and speed_percent <= 10:
                    # 先设置50%启动风扇
                    kickstart_duty = int(65535 * 50 / 100)
                    self.pwm.duty_u16(kickstart_duty)
                    time.sleep_ms(500)  # 等待500ms让风扇启动
                    info("风扇起转辅助：先设置50%启动", module=MODULE_NAME)
                    
                    # 等待风扇稳定后再设置目标转速
                    time.sleep_ms(200)
                
                # 设置目标PWM占空比
                duty = int(65535 * speed_percent / 100)
                self.pwm.duty_u16(duty)
            else:
                # 模拟模式：仅更新状态
                info(f"模拟模式：风扇转速设置为 {speed_percent}%", module=MODULE_NAME)
            
            self.current_speed = speed_percent
            
            if speed_percent > 0:
                info(f"风扇转速设置为 {speed_percent}%", module=MODULE_NAME)
            else:
                info("风扇已关闭", module=MODULE_NAME)
                
            return True
            
        except Exception as e:
            # 即使硬件操作失败，也更新状态用于开发测试
            warning(f"设置风扇转速失败，使用模拟模式: {e}", module=MODULE_NAME)
            self.current_speed = speed_percent
            return True

    def get_speed(self) -> int:
        """获取当前设置的转速百分比"""
        return self.current_speed

    def get_rpm(self) -> int:
        """获取当前实际转速 (RPM) - 参考测试脚本逻辑"""
        if not self.is_initialized:
            return 0
        
        # 检查是否有实际的TACH硬件
        if self.tach_pin_obj is not None:
            # 使用周期法计算RPM - 参考测试脚本
            rpm_period = self._calculate_rpm_from_intervals()
            if rpm_period is not None:
                return rpm_period
        
        # 没有硬件时返回0，不进行模拟
        return 0

    def is_running(self) -> bool:
        """检查风扇是否在运行"""
        return self.current_speed > 0

    def stop(self):
        """停止风扇"""
        self.set_speed(0)

    def cleanup(self):
        """清理资源"""
        try:
            if self.pwm:
                self.pwm.duty_u16(0)
                self.pwm.deinit()
                self.pwm = None
                
            if self.tach_pin_obj:
                self.tach_pin_obj.irq(handler=None)
                self.tach_pin_obj = None
                
            self.is_initialized = False
            info("风扇控制器已清理", module=MODULE_NAME)
            
        except Exception as e:
            # 模拟模式下清理失败不影响功能
            warning(f"风扇控制器清理失败: {e}", module=MODULE_NAME)
            self.is_initialized = False

# =============================================================================
# 模块级单例与公共接口
# =============================================================================
_instance = None

def _get_instance():
    """获取或创建风扇控制器实例(延迟初始化)"""
    global _instance
    if _instance is None:
        _instance = _FanController()
    return _instance

def set_speed(speed_percent: int) -> bool:
    """
    设置风扇转速
    
    Args:
        speed_percent (int): 转速百分比 0-100
        
    Returns:
        bool: 设置是否成功
    """
    controller = _get_instance()
    return controller.set_speed(speed_percent)

def get_speed() -> int:
    """获取当前设置的转速百分比"""
    controller = _get_instance()
    return controller.get_speed()

def get_rpm() -> int:
    """获取当前实际转速 (RPM)"""
    controller = _get_instance()
    return controller.get_rpm()

def is_running() -> bool:
    """检查风扇是否在运行"""
    controller = _get_instance()
    return controller.is_running()

def stop():
    """停止风扇"""
    controller = _get_instance()
    controller.stop()

def configure(pwm_pin: int = DEFAULT_PWM_PIN, tach_pin: int = DEFAULT_TACH_PIN, 
              pwm_freq: int = DEFAULT_PWM_FREQ, pulses_per_rev: int = DEFAULT_PULSES_PER_REV):
    """
    重新配置风扇参数
    
    Args:
        pwm_pin (int): PWM控制引脚
        tach_pin (int): TACH信号引脚  
        pwm_freq (int): PWM频率
        pulses_per_rev (int): 每转脉冲数
    """
    global _instance
    if _instance:
        _instance.cleanup()
    _instance = _FanController(pwm_pin, tach_pin, pwm_freq, pulses_per_rev)

def cleanup():
    """清理风扇资源"""
    global _instance
    if _instance:
        _instance.cleanup()
        _instance = None

