# -*- coding: utf-8 -*-
"""
增强主程序

使用新的模块化架构重构ESP32C3主程序：
- 统一配置管理
- 增强错误处理
- 模块化组件
- 内存优化
- 可靠性提升
"""

import time
import machine
import gc
import sys

# 导入新模块
try:
    import config
    import error_handler
    import enhanced_daemon as daemon
    import wifi_manager
    import mqtt
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    sys.exit(1)

# =============================================================================
# 应用程序类
# =============================================================================

class ESP32C3Application:
    """ESP32C3应用程序主类"""
    
    def __init__(self):
        self._logger = error_handler.get_logger()
        self._error_handler = error_handler.get_error_handler()
        self._config_manager = config.get_config_manager()
        self._mqtt_client = None
        self._running = False
        self._loop_count = 0
        self._last_status_report = 0
        
        # 验证配置
        if not self._config_manager.is_valid():
            self._logger.critical("配置验证失败", "Main")
            return
        
        self._logger.info("应用程序初始化", "Main")
    
    def start(self):
        """启动应用程序"""
        try:
            self._logger.info("启动ESP32C3应用程序...", "Main")
            
            # 连接WiFi
            if not self._connect_wifi():
                self._logger.critical("WiFi连接失败", "Main")
                return False
            
            # 初始化MQTT
            if not self._init_mqtt():
                self._logger.error("MQTT初始化失败", "Main")
                # 继续运行，但不使用MQTT
            
            # 设置MQTT客户端给其他模块
            if self._mqtt_client:
                error_handler.set_mqtt_client(self._mqtt_client)
                daemon.state.set('mqtt_client', self._mqtt_client)
            
            # 启动守护进程
            if not daemon.start_daemon():
                self._logger.error("守护进程启动失败", "Main")
                return False
            
            self._running = True
            self._logger.info("应用程序启动成功", "Main")
            return True
            
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.SYSTEM, e, "ApplicationStart"
            )
            return False
    
    def _connect_wifi(self) -> bool:
        """连接WiFi"""
        try:
            self._logger.info("连接WiFi...", "Main")
            connection_successful = wifi_manager.connect_wifi()
            
            if connection_successful:
                self._logger.info("WiFi连接成功", "Main")
                return True
            else:
                self._logger.error("WiFi连接失败", "Main")
                return False
                
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.WIFI, e, "WiFiConnection"
            )
            return False
    
    def _init_mqtt(self) -> bool:
        """初始化MQTT客户端"""
        try:
            self._logger.info("初始化MQTT客户端...", "Main")
            
            # 从配置获取MQTT设置
            broker = config.get_config('mqtt.broker', config.MQTTConfig.BROKER)
            port = config.get_config('mqtt.port', config.MQTTConfig.PORT)
            topic = config.get_config('mqtt.topic', config.MQTTConfig.TOPIC)
            
            # 生成客户端ID
            client_id = f"esp32c3-{machine.unique_id().hex()}"
            
            # 创建MQTT客户端
            self._mqtt_client = mqtt.MqttServer(
                client_id=client_id,
                server=broker,
                port=port,
                topic=topic
            )
            
            # 连接MQTT
            if self._mqtt_client.connect():
                self._logger.info("MQTT连接成功", "Main")
                return True
            else:
                self._logger.warning("MQTT连接失败，将离线运行", "Main")
                return False
                
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.MQTT, e, "MQTTInit"
            )
            return False
    
    def run(self):
        """运行主循环"""
        if not self._running:
            self._logger.error("应用程序未启动", "Main")
            return
        
        self._logger.info("进入主循环", "Main")
        
        try:
            while self._running:
                self._main_loop()
                
        except KeyboardInterrupt:
            self._logger.info("收到中断信号，停止应用程序", "Main")
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.SYSTEM, e, "MainLoop"
            )
        finally:
            self._stop()
    
    def _main_loop(self):
        """主循环逻辑"""
        try:
            self._loop_count += 1
            
            # 检查安全模式
            if daemon.is_safe_mode():
                if self._loop_count % 10 == 0:  # 每10次循环打印一次
                    self._logger.warning("系统处于安全模式，暂停正常操作", "Main")
                time.sleep_ms(config.SystemConfig.MAIN_LOOP_DELAY)
                return
            
            # 定期状态报告
            if self._loop_count % config.SystemConfig.STATUS_REPORT_INTERVAL == 0:
                self._report_status()
            
            # 内存管理
            if self._loop_count % 50 == 0:
                self._manage_memory()
            
            # MQTT连接管理
            self._manage_mqtt_connection()
            
            # 检查系统健康状态
            if self._loop_count % 100 == 0:
                self._check_system_health()
            
            # 短暂休眠，避免CPU空转
            time.sleep_ms(config.SystemConfig.MAIN_LOOP_DELAY)
            
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.SYSTEM, e, "MainLoop"
            )
            
            # 如果主循环出错，暂停一下
            time.sleep_ms(1000)
    
    def _report_status(self):
        """报告系统状态"""
        try:
            # 获取守护进程状态
            daemon_status = daemon.get_daemon_status()
            
            # 获取错误统计
            error_stats = error_handler.get_error_stats()
            total_errors = sum(stats.get('count', 0) for stats in error_stats.values())
            
            # 构建状态消息
            status_msg = (
                f"循环: {self._loop_count}, "
                f"守护进程: {'活跃' if daemon_status.get('active') else '停止'}, "
                f"安全模式: {'是' if daemon_status.get('safe_mode') else '否'}, "
                f"温度: {daemon_status.get('temperature', '未知')}°C, "
                f"内存: {daemon_status.get('memory_usage', '未知')}%, "
                f"错误: {total_errors}, "
                f"监控次数: {daemon_status.get('monitor_count', 0)}"
            )
            
            self._logger.info(status_msg, "Main")
            
            # 如果MQTT可用，发送状态
            if self._mqtt_client and self._mqtt_client.is_connected:
                self._mqtt_client.log("INFO", f"[Main] {status_msg}")
            
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.SYSTEM, e, "StatusReport"
            )
    
    def _manage_memory(self):
        """内存管理"""
        try:
            # 显示内存使用情况
            if config.SystemConfig.DEBUG_MODE:
                free_before = gc.mem_free()
                self._logger.debug(f"内存使用情况 - 空闲: {free_before}字节", "Main")
            
            # 执行垃圾回收
            gc.collect()
            
            if config.SystemConfig.DEBUG_MODE:
                free_after = gc.mem_free()
                freed = free_after - free_before
                if freed > 0:
                    self._logger.debug(f"垃圾回收释放: {freed}字节", "Main")
            
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.MEMORY, e, "MemoryManagement"
            )
    
    def _manage_mqtt_connection(self):
        """管理MQTT连接"""
        if not self._mqtt_client:
            return
        
        try:
            if not self._mqtt_client.is_connected:
                self._logger.warning("MQTT断开连接，尝试重连...", "Main")
                
                # 使用指数退避重连
                if self._mqtt_client.connect():
                    self._logger.info("MQTT重连成功", "Main")
                    # 重新设置MQTT客户端
                    error_handler.set_mqtt_client(self._mqtt_client)
                else:
                    self._logger.error("MQTT重连失败", "Main")
            else:
                # 检查连接状态
                self._mqtt_client.check_connection()
                
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.MQTT, e, "MQTTConnection"
            )
    
    def _check_system_health(self):
        """检查系统健康状态"""
        try:
            # 获取系统状态
            daemon_status = daemon.get_daemon_status()
            
            # 检查守护进程是否活跃
            if not daemon_status.get('active'):
                self._logger.warning("守护进程不活跃", "Main")
            
            # 检查错误统计
            error_stats = error_handler.get_error_stats()
            total_errors = sum(stats.get('count', 0) for stats in error_stats.values())
            
            if total_errors > 50:  # 如果错误过多
                self._logger.warning(f"系统错误过多: {total_errors}", "Main")
                
                # 如果错误过多，可以考虑重启
                if total_errors > 100:
                    self._logger.critical("系统错误过多，建议重启", "Main")
            
            # 检查内存使用
            memory_usage = daemon_status.get('memory_usage')
            if memory_usage and memory_usage > 95:
                self._logger.critical(f"内存使用过高: {memory_usage}%", "Main")
                # 强制垃圾回收
                gc.collect()
            
        except Exception as e:
            self._error_handler.handle_error(
                error_handler.ErrorType.SYSTEM, e, "HealthCheck"
            )
    
    def _stop(self):
        """停止应用程序"""
        self._logger.info("停止应用程序...", "Main")
        
        self._running = False
        
        # 停止守护进程
        daemon.stop_daemon()
        
        # 断开MQTT连接
        if self._mqtt_client:
            try:
                self._mqtt_client.disconnect()
            except:
                pass
        
        # 最终垃圾回收
        gc.collect()
        
        self._logger.info("应用程序已停止", "Main")
    
    def stop(self):
        """外部停止接口"""
        self._stop()

# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口"""
    try:
        # 打印启动信息
        print("=" * 50)
        print("ESP32C3 IoT 设备启动")
        print("=" * 50)
        
        # 创建应用程序实例
        app = ESP32C3Application()
        
        # 启动应用程序
        if app.start():
            # 运行主循环
            app.run()
        else:
            print("❌ 应用程序启动失败")
            
            # 如果启动失败，进入深度睡眠
            print("进入深度睡眠模式...")
            try:
                machine.deepsleep(60000)  # 60秒后重启
            except:
                print("深度睡眠不可用，系统停止")
        
    except Exception as e:
        print(f"❌ 主程序异常: {e}")
        
        # 记录未处理的异常
        try:
            error_handler.log_error(
                error_handler.ErrorType.SYSTEM, e, "MainEntry"
            )
        except:
            pass
        
        # 系统重启
        print("系统重启...")
        try:
            machine.reset()
        except:
            print("重启不可用，系统停止")

if __name__ == "__main__":
    main()