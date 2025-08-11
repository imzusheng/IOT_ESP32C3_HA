"""main.py - 依赖注入容器和系统启动
按照 REFACTOR_PLAN.md 中的伪代码实现
注意：Logger 现在是独立工作的，不再依赖 EventBus
"""

import utime as time
import machine
import gc
import sys

# 1. 导入所有类
from config import get_config
from lib.event_bus import EventBus
from lib.object_pool import ObjectPoolManager
from lib.static_cache import StaticCache
from lib.logger import Logger, set_global_logger
from lib.event_bus import EVENTS
from fsm import SystemFSM
from net.wifi import WifiManager
from net.mqtt import MqttController
from hw.led import LEDPatternController
from hw.sensor import SensorManager

class MainController:
    """主控制器 - 负责系统初始化和事件订阅"""
    
    def __init__(self, config):
        self.config = config
        
        # 初始化核心服务
        self.event_bus = EventBus()
        self.object_pool = ObjectPoolManager()
        self.static_cache = StaticCache()
          
        # 启动指标与恢复信息（稳定性优先，低侵入）
        try:
            boot_count = self.static_cache.get('boot_count', 0) + 1
            self.static_cache.set('boot_count', boot_count)
            # 记录上次启动时间（设备上电/复位后第一个毫秒计数）
            self.static_cache.set('last_boot_ms', time.ticks_ms())
            # 记录复位原因（若可用）
            reset_cause = None
            try:
                if hasattr(machine, 'reset_cause'):
                    reset_cause = machine.reset_cause()
            except Exception:
                reset_cause = None
            if reset_cause is not None:
                self.static_cache.set('last_reset_cause', reset_cause)
            # 记录固件/配置版本信息（若配置中存在）
            fw = {}
            v = self.config.get('version')
            if v is not None:
                fw['version'] = v
            b = self.config.get('build')
            if b is not None:
                fw['build'] = b
            if fw:
                self.static_cache.set('firmware', fw)
            # 立即持久化，避免掉电丢失
            self.static_cache.save(force=True)
        except Exception:
            # 静默处理缓存写入错误，避免影响启动
            pass
        
        # 初始化日志系统（使用配置）
        log_config = config.get('logging', {})
        log_level_str = log_config.get('log_level', 'INFO')
        
        # 转换日志级别 - Logger 现在是独立工作的，不再依赖 EventBus
        level_map = {
            'DEBUG': 10,  # logging.DEBUG
            'INFO': 20,   # logging.INFO
            'WARNING': 30, # logging.WARNING
            'ERROR': 40,  # logging.ERROR
            'CRITICAL': 50 # logging.CRITICAL
        }
        log_level = level_map.get(log_level_str, 20)  # 默认 INFO 级别
        
        self.logger = Logger(level=log_level, config=log_config)
        # Logger 现在是独立的，不需要 EventBus 设置
        set_global_logger(self.logger)
        
        # 初始化模块控制器
        self.wifi = WifiManager(self.event_bus, config.get('wifi', {}))
        self.mqtt = MqttController(self.event_bus, self.object_pool, config.get('mqtt', {}))
        
        # 初始化硬件模块
        led_pins = config.get('daemon', {}).get('led_pins', [12, 13])
        self.led = LEDPatternController(led_pins)
        self.sensor = SensorManager(self.event_bus, self.object_pool)
        
        # 创建状态机
        self.fsm = SystemFSM(
            event_bus=self.event_bus,
            object_pool=self.object_pool,
            static_cache=self.static_cache,
            config=config,
            wifi_manager=self.wifi,
            mqtt_controller=self.mqtt,
            led_controller=self.led
        )
        
        # 订阅系统事件
        self._subscribe_system_events()
        
    def _subscribe_system_events(self):
        """订阅系统级事件，处理 NTP 同步、连接状态等"""
        
        # NTP 时间同步状态变化事件
        self.event_bus.subscribe(EVENTS.NTP_STATE_CHANGE, self._on_ntp_state_change)
        
        # 系统状态事件（仅用于监控和日志记录）
        self.event_bus.subscribe(EVENTS.SYSTEM_ERROR, self._on_system_error)
        self.event_bus.subscribe(EVENTS.SYSTEM_STATE_CHANGE, self._on_system_state_change)
        
        self.logger.info("系统事件订阅已注册", module="Main")
    
    # =================== NTP 时间同步事件处理 ===================
    def _on_ntp_state_change(self, event_name, state, **kwargs):
        """处理 NTP 状态变化事件"""
        if state == 'started':
            ntp_server = kwargs.get('ntp_server', 'default')
            self.logger.info("开始NTP时间同步: {}", ntp_server, module="Main")
        elif state == 'success':
            ntp_server = kwargs.get('ntp_server', 'unknown')
            attempts = kwargs.get('attempts', 'unknown')
            self.logger.info("NTP时间同步成功！服务器: {}, 尝试次数: {}", 
                            ntp_server, attempts, module="Main")
        elif state == 'failed':
            attempts = kwargs.get('attempts')
            error = kwargs.get('error')
            if isinstance(error, Exception):
                error_msg = str(error)
            else:
                error_msg = error or "未知错误"
            
            msg = f"NTP同步失败，尝试次数: {attempts}。错误: {error_msg}"
            self.logger.warning(msg, module="Main")
    
    # =================== WiFi 连接事件处理 ===================
        
        

    
    # =================== 系统状态事件处理 ===================
    def _on_system_error(self, event_name, error_type=None, error_context=None, **kwargs):
        """处理统一的系统错误事件"""
        if error_type == 'memory_critical':
            # 处理内存临界错误
            mem_info = error_context.get('mem_info') if error_context else None
            msg = f"内存使用严重: {mem_info or '未知'}"
            self.logger.error(msg, module="Main")
            
            self.logger.info("执行紧急垃圾回收...", module="Main")
            for _ in range(3):
                gc.collect()
                time.sleep_ms(50)
        elif error_type == 'callback_error':
            # 处理事件回调错误
            if error_context:
                error_msg = error_context.get('error', '未知错误')
                event = error_context.get('event', '未知事件')
                callback = error_context.get('callback', '未知回调')
                msg = f"事件回调执行失败: {event} -> {callback}, 错误: {error_msg}"
            else:
                msg = "事件回调执行失败: 未知错误"
            self.logger.error(msg, module="Main")
        else:
            # 处理其他系统错误
            error_msg = error_context.get('error_msg') if error_context else None
            msg = f"系统错误 ({error_type or '未知类型'}): {error_msg or '未知错误'}"
            self.logger.error(msg, module="Main")
    
    def _on_system_state_change(self, event_name, state, **kwargs):
        """处理系统状态变化事件"""
        if state == 'warning':
            warning_msg = kwargs.get('warning_msg', '未知警告')
            msg = f"系统警告: {warning_msg}"
            self.logger.warning(msg, module="Main")
        elif state == 'queue_full_warning':
            queue_usage = kwargs.get('queue_usage', 0)
            msg = f"事件队列使用率过高: {int(queue_usage * 100)}%"
            self.logger.warning(msg, module="Main")
        elif state == 'shutdown':
            error_context = kwargs.get('error_context')
            self.logger.critical("触发系统关机！", module="Main")
            if error_context:
                self.logger.critical(f"关机原因: {error_context}", module="Main")
            self.emergency_cleanup()
        else:
            # 处理其他系统状态变化
            self.logger.info(f"系统状态变化: {state}", module="Main")
    
    def on_emergency_shutdown(self, event_name, error_context=None):
        """处理紧急关机事件"""
        self.logger.critical("触发紧急关机！", module="Main")
        
        if error_context:
            self.logger.critical(f"关机原因: {error_context}", module="Main")
        
        # 执行紧急清理
        self.emergency_cleanup()

    def emergency_cleanup(self):
        """紧急清理程序"""
        self.logger.info("执行紧急垃圾回收...", module="Main")
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)
    
    def setup_object_pools(self):
        """配置对象池"""
        # 为 MQTT 消息复用的字典池（重用频率最高）
        self.object_pool.add_pool("mqtt_messages", lambda: {"topic": "", "payload": "", "retain": False, "qos": 0}, 8)
        # 为传感器数据复用的字典池
        self.object_pool.add_pool("sensor_data", lambda: {"sensor_id": "", "value": None, "timestamp": 0}, 6)
        # 为状态机维护系统状态事件池
        self.object_pool.add_pool("system_events", lambda: {"event": "", "state": "", "duration": 0}, 5)
        # 为日志系统预留少量对象（可选，以防日志字符串过多）
        self.object_pool.add_pool("log_context", lambda: {"level": "", "module": "", "timestamp": 0}, 12)
        self.logger.info("对象池已配置 - 共{}个对象池", len(self.object_pool._pools), module="Main")
        
        # 可选：输出内存统计（调试信息）
        if self.config.get('logging', {}).get('log_level', 'INFO') == 'DEBUG':
            import gc
            mem_free = gc.mem_free()
            mem_alloc = gc.mem_alloc()
            self.logger.debug("对象池设置后内存统计 - 空闲: {}B, 已分配: {}B", mem_free, mem_alloc, module="Main")
    
    def start_system(self):
        """启动系统"""
        self.logger.info("启动ESP32-C3 IoT设备", module="Main")
        
        # 配置对象池
        self.setup_object_pools()
        
        # 启动状态机主循环
        try:
            self.logger.info("启动系统状态机", module="Main")
            self.fsm.run()
        except KeyboardInterrupt:
            self.logger.info("用户中断，正在关闭", module="Main")
            self.cleanup()
        except Exception as e:
            self.logger.error(f"致命错误: {e}", module="Main")
            self.cleanup()
            # 系统重启
            machine.reset()
    
    def cleanup(self):
        """清理资源"""
        try:
            self.logger.info("开始清理过程", module="Main")
            
            # 停止状态机
            if hasattr(self, 'fsm') and self.fsm:
                self.fsm.force_state("SHUTDOWN")
            
            # 清理LED
            if hasattr(self, 'led') and self.led:
                self.led.cleanup()
            
            # 断开网络连接
            if hasattr(self, 'mqtt') and self.mqtt:
                self.mqtt.disconnect()
            
            if hasattr(self, 'wifi') and self.wifi:
                self.wifi.disconnect()
            
            # 保存缓存
            if hasattr(self, 'static_cache') and self.static_cache:
                self.static_cache.save(force=True)
            
            self.logger.info("清理完成", module="Main")
        except Exception as e:
            self.logger.error(f"清理失败: {e}", module="Main")

def main():
    """主函数 - 系统入口点"""
    
    # 加载配置
    config = get_config()
    
    # 创建临时logger用于启动信息
    from lib.logger import Logger
    temp_logger = Logger()
    temp_logger.info("=== ESP32-C3 IoT设备启动中 ===", module="Main")
    temp_logger.info("配置已加载", module="Main")
    
    # 创建主控制器
    main_controller = MainController(config)
    
    # 启动系统
    main_controller.start_system()

if __name__ == "__main__":
    main()