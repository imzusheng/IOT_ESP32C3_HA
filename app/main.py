"""
main.py - 依赖注入容器和系统启动
按照 REFACTOR_PLAN.md 中的伪代码实现
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
from event_const import EVENT
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
        
        # 初始化日志系统（使用配置）
        log_config = config.get('logging', {})
        log_level_str = log_config.get('log_level', 'INFO')
        
        # 转换日志级别
        level_map = {
            'DEBUG': EVENT.LOG_DEBUG,
            'INFO': EVENT.LOG_INFO,
            'WARNING': EVENT.LOG_WARN,
            'ERROR': EVENT.LOG_ERROR,
            'CRITICAL': EVENT.LOG_ERROR
        }
        log_level = level_map.get(log_level_str, EVENT.LOG_INFO)
        
        self.logger = Logger(level=log_level, config=log_config)
        self.logger.setup(self.event_bus)
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
        
        # NTP 时间同步事件
        self.event_bus.subscribe(EVENT.NTP_SYNC_STARTED, self._on_ntp_sync_started)
        self.event_bus.subscribe(EVENT.NTP_SYNC_SUCCESS, self._on_ntp_sync_success)
        self.event_bus.subscribe(EVENT.NTP_SYNC_FAILED, self._on_ntp_sync_failed)
        self.event_bus.subscribe(EVENT.TIME_UPDATED, self._on_time_updated)
        
        # WiFi 连接事件
        self.event_bus.subscribe(EVENT.WIFI_CONNECTING, self._on_wifi_connecting)
        self.event_bus.subscribe(EVENT.WIFI_CONNECTED, self._on_wifi_connected)
        self.event_bus.subscribe(EVENT.WIFI_DISCONNECTED, self._on_wifi_disconnected)
        
        # MQTT 连接事件
        self.event_bus.subscribe(EVENT.MQTT_CONNECTED, self._on_mqtt_connected)
        self.event_bus.subscribe(EVENT.MQTT_DISCONNECTED, self._on_mqtt_disconnected)
        
        # 系统状态事件
        self.event_bus.subscribe(EVENT.SYSTEM_ERROR, self._on_system_error)
        self.event_bus.subscribe(EVENT.SYSTEM_WARNING, self._on_system_warning)
        self.event_bus.subscribe(EVENT.MEMORY_CRITICAL, self._on_memory_critical)
        
        self.logger.info("System event subscriptions registered", module="Main")
    
    # =================== NTP 时间同步事件处理 ===================
    def _on_ntp_sync_started(self, event_name, ntp_server=None):
        """处理 NTP 同步开始事件"""
        self.logger.info(f"Starting NTP time synchronization: {ntp_server or 'default'}", module="Main")
    
    def _on_ntp_sync_success(self, event_name, ntp_server=None, attempts=None, timestamp=None):
        """处理 NTP 同步成功事件"""
        msg = f"NTP time sync successful! Server: {ntp_server or 'unknown'}, attempts: {attempts or 'unknown'}"
        self.logger.info(msg, module="Main")
        
        # 获取并显示当前时间
        try:
            import time
            current_time = time.localtime()
            time_str = f"{current_time[0]}-{current_time[1]:02d}-{current_time[2]:02d} {current_time[3]:02d}:{current_time[4]:02d}:{current_time[5]:02d}"
            self.logger.info(f"System time updated: {time_str}", module="Main")
        except Exception as e:
            self.logger.error(f"Failed to get current time: {e}", module="Main")
    
    def _on_ntp_sync_failed(self, event_name, ntp_server=None, attempts=None, error=None):
        """处理 NTP 同步失败事件"""
        if isinstance(error, Exception):
            error_msg = str(error)
        else:
            error_msg = error or "unknown error"
        
        msg = f"NTP sync failed after {attempts} attempts. Error: {error_msg}"
        self.logger.warning(msg, module="Main")
        
        self.logger.info("System time updated, other modules can start time-dependent functions", module="Main")
    
    # =================== WiFi 连接事件处理 ===================
    def _on_wifi_connecting(self, event_name):
        """处理 WiFi 连接开始事件"""
        self.logger.info("Starting WiFi connection", module="Main")
    
    def _on_wifi_connected(self, event_name, ip=None, ssid=None):
        """处理 WiFi 连接成功事件"""
        ssid_info = f" (SSID: {ssid})" if ssid else ""
        msg = f"WiFi connected successfully! IP address: {ip}{ssid_info}"
        self.logger.info(msg, module="Main")
        
        self.logger.info("Network ready, can start network services", module="Main")
    
    def _on_wifi_disconnected(self, event_name, reason=None, ssid=None):
        """处理 WiFi 断开事件"""
        ssid_info = f" (SSID: {ssid})" if ssid else ""
        msg = f"WiFi disconnected: {reason or 'unknown'}{ssid_info}"
        self.logger.warning(msg, module="Main")
    
    # =================== MQTT 连接事件处理 ===================
    def _on_mqtt_connected(self, event_name, broker=None):
        """处理 MQTT 连接成功事件"""
        msg = f"MQTT connected successfully!"
        if broker:
            msg += f" Broker: {broker}"
        self.logger.info(msg, module="Main")
    
    def _on_mqtt_disconnected(self, event_name, reason=None, broker=None):
        """处理 MQTT 断开事件"""
        broker_info = f" (Broker: {broker})" if broker else ""
        msg = f"MQTT disconnected: {reason or 'unknown'}{broker_info}"
        self.logger.warning(msg, module="Main")
    
    def _on_time_updated(self, event_name, timestamp=None, **kwargs):
        """处理时间更新事件"""
        if timestamp:
            try:
                import time
                time_tuple = time.localtime(timestamp)
                time_str = f"{time_tuple[0]:04d}-{time_tuple[1]:02d}-{time_tuple[2]:02d} " \
                          f"{time_tuple[3]:02d}:{time_tuple[4]:02d}:{time_tuple[5]:02d}"
                msg = f"System time updated to: {time_str} (timestamp: {timestamp}), other modules can start time-dependent functions"
                self.logger.info(msg, module="Main")
            except Exception as e:
                self.logger.warning(f"Failed to parse timestamp: {e}, timestamp: {timestamp}", module="Main")
                self.logger.info(f"System time updated (timestamp: {timestamp})", module="Main")
        else:
            self.logger.info("System time updated, other modules can start time-dependent functions", module="Main")
            self.logger.info("System time update completed", module="Main")
    
    # =================== 系统状态事件处理 ===================
    def _on_system_error(self, event_name, error_msg=None):
        """处理系统错误事件"""
        msg = f"System error: {error_msg or 'unknown'}"
        self.logger.error(msg, module="Main")
    
    def _on_system_warning(self, event_name, warning_msg=None):
        """处理系统警告事件"""
        msg = f"System warning: {warning_msg or 'unknown'}"
        self.logger.warning(msg, module="Main")
    
    def _on_memory_critical(self, event_name, mem_info=None):
        """处理内存临界事件"""
        msg = f"Critical memory usage: {mem_info or 'unknown'}"
        self.logger.error(msg, module="Main")
        
        self.logger.info("Performing emergency garbage collection...", module="Main")
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)
    
    def on_emergency_shutdown(self, event_name, error_context=None):
        """处理紧急关机事件"""
        self.logger.critical("Emergency shutdown triggered!", module="Main")
        
        if error_context:
            self.logger.critical(f"Shutdown reason: {error_context}", module="Main")
        
        # 执行紧急清理
        self.emergency_cleanup()

    def emergency_cleanup(self):
        """紧急清理程序"""
        self.logger.info("Performing emergency garbage collection...", module="Main")
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)
    
    def setup_object_pools(self):
        """配置对象池"""
        self.object_pool.add_pool("mqtt_messages", lambda: {}, 10)
        self.object_pool.add_pool("sensor_data", lambda: {}, 5)
        self.object_pool.add_pool("log_messages", lambda: "", 20)
        self.object_pool.add_pool("system_events", lambda: {}, 15)
        self.logger.info("Object pools configured", module="Main")
    
    def start_system(self):
        """启动系统"""
        self.logger.info("Starting ESP32-C3 IoT device", module="Main")
        
        # 配置对象池
        self.setup_object_pools()
        
        # 启动状态机主循环
        try:
            self.logger.info("Starting system state machine", module="Main")
            self.fsm.run()
        except KeyboardInterrupt:
            self.logger.info("User interrupted, shutting down", module="Main")
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", module="Main")
            self.cleanup()
            # 系统重启
            machine.reset()
    
    def cleanup(self):
        """清理资源"""
        try:
            self.logger.info("Starting cleanup process", module="Main")
            
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
            
            self.logger.info("Cleanup completed", module="Main")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}", module="Main")

def main():
    """主函数 - 系统入口点"""
    
    # 加载配置
    config = get_config()
    
    # 创建临时logger用于启动信息
    from lib.logger import Logger
    temp_logger = Logger()
    temp_logger.info("=== ESP32-C3 IoT Device Starting ===", module="Main")
    temp_logger.info("Configuration loaded", module="Main")
    
    # 创建主控制器
    main_controller = MainController(config)
    
    # 启动系统
    main_controller.start_system()

if __name__ == "__main__":
    main()