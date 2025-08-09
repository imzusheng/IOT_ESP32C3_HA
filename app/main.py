"""
main.py - 依赖注入容器和系统启动
按照 REFACTOR_PLAN.md 中的伪代码实现
"""

import time
import machine
import gc
import sys

# 1. 导入所有类
from app.config import get_config
from app.lib.event_bus import EventBus
from app.lib.object_pool import ObjectPoolManager
from app.lib.static_cache import StaticCache
from app.lib.logger import Logger
from app.event_const import EVENT
from app.fsm import SystemFSM
from app.net.wifi import WifiManager
from app.net.mqtt import MqttController
from app.hw.led import LEDPatternController
from app.hw.sensor import SensorManager

def main():
    """主函数 - 依赖注入容器"""
    
    print("=== ESP32-C3 IoT Device Starting ===")
    
    # 2. 加载配置
    config = get_config()
    print("[Main] Configuration loaded")
    
    # 3. 初始化核心服务
    event_bus = EventBus()
    object_pool = ObjectPoolManager()
    static_cache = StaticCache()
    logger = Logger()
    logger.setup(event_bus)  # 注册 logger
    
    print("[Main] Core services initialized")
    
    # 设置对象池
    object_pool.add_pool("mqtt_messages", lambda: {}, 10)
    object_pool.add_pool("sensor_data", lambda: {}, 5)
    object_pool.add_pool("log_messages", lambda: "", 20)
    object_pool.add_pool("system_events", lambda: {}, 15)
    
    print("[Main] Object pools configured")
    
    # 4. 初始化模块控制器
    wifi = WifiManager(event_bus, config.get('wifi', {}))
    mqtt = MqttController(event_bus, object_pool, config.get('mqtt', {}))
    
    # 初始化硬件模块
    led_pins = config.get('daemon', {}).get('led_pins', [12, 13])
    led = LEDPatternController(led_pins)
    
    sensor = SensorManager(event_bus, object_pool)
    
    print("[Main] Module controllers initialized")
    
    # 5. 创建并启动状态机，注入所有依赖
    fsm = SystemFSM(
        event_bus=event_bus,
        object_pool=object_pool,
        static_cache=static_cache,
        config=config,
        wifi_manager=wifi,
        mqtt_controller=mqtt,
        led_controller=led
    )
    
    print("[Main] SystemFSM created")
    
    # 6. 启动系统
    try:
        print("Starting system...")
        fsm.run()  # 启动 FSM 主循环
    except KeyboardInterrupt:
        print("[Main] User interrupted, shutting down...")
        cleanup(fsm, mqtt, wifi, led, static_cache)
    except Exception as e:
        print(f"[Main] Fatal error: {e}")
        cleanup(fsm, mqtt, wifi, led, static_cache)
        # 系统重启
        machine.reset()

def cleanup(fsm, mqtt, wifi, led, static_cache):
    """清理资源"""
    try:
        # 停止状态机
        if fsm:
            fsm.force_state("SHUTDOWN")
        
        # 清理LED
        if led:
            led.cleanup()
        
        # 断开网络连接
        if mqtt:
            mqtt.disconnect()
        
        if wifi:
            wifi.disconnect()
        
        # 保存缓存
        if static_cache:
            static_cache.save(force=True)
        
        print("[Main] Cleanup completed")
    except Exception as e:
        print(f"[Main] Cleanup failed: {e}")

if __name__ == "__main__":
    main()