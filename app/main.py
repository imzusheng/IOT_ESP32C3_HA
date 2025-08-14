"""main.py - 依赖注入容器和系统启动"""

import utime as time
import machine

# 1. 导入所有类
from config import get_config
from lib.lock.event_bus import EventBus
from lib.logger import info, debug, error
from fsm.core import create_state_machine
from net import NetworkManager
from hw.led import LEDPatternController

class MainController:
    """主控制器 - 负责系统初始化和事件订阅"""
    
    def __init__(self, config):
        self.config = config
        
        # 日志系统现在自动初始化，无需手动调用
        
        # 初始化核心服务
        debug("开始初始化EventBus...", module="Main")
        self.event_bus = EventBus()
        debug("EventBus初始化完成", module="Main")
          
        # 启动指标与恢复信息（稳定性优先，低侵入）
        
        # 初始化网络管理器
        debug("开始初始化NetworkManager...", module="Main")
        self.network_manager = NetworkManager(self.event_bus, config)
        debug("NetworkManager初始化完成", module="Main")
        
        # 初始化硬件模块
        debug("开始初始化LED...", module="Main")
        led_pins = config.get('daemon', {}).get('led_pins', [12, 13])
        self.led = LEDPatternController(led_pins)
        debug("LED初始化完成", module="Main")
        
        # 创建状态机
        debug("开始初始化状态机...", module="Main")
        self.state_machine = create_state_machine(
            event_bus=self.event_bus,
            config=config,
            network_manager=self.network_manager,
            led_controller=self.led
        )
        debug("状态机初始化完成", module="Main")
        
        debug("MainController初始化完成", module="Main")
        
  
    def start_system(self):
        """启动系统"""
        debug("开始启动系统...", module="Main")
        info("启动ESP32-C3 IoT设备", module="Main")
        
          
        # 新版状态机是完全事件驱动的，不需要独立的主循环
        # 系统启动后，所有工作都由事件总线的后台定时器驱动
        info("新版状态机已启动，采用事件驱动架构", module="Main")
        
        try:
            # 简单的事件循环，主要用于保持程序运行和处理用户中断
            debug("进入事件驱动主循环", module="Main")
            info("进入事件驱动主循环", module="Main")
            
            # 持续运行，直到收到关机信号
            loop_count = 0
            while self.state_machine.get_current_state() != "SHUTDOWN":
                loop_count += 1
                if loop_count % 10 == 0:  # 每10次循环输出一次调试信息
                    debug("主循环运行中... 当前状态: {}, 循环次数: {}", 
                          self.state_machine.get_current_state(), loop_count, module="Main")
                
                # 更新状态机（状态机内部会根据需要调用网络管理器）
                self.state_machine.update()
                # 喂看门狗
                self.state_machine.feed_watchdog()
                
                # 简单的延迟，避免CPU占用过高
                main_loop_delay = self.config.get('system', {}).get('main_loop_delay', 300)
                time.sleep_ms(main_loop_delay)
                
                # 更新静态缓存
            
            # 如果到达这里，说明系统进入了SHUTDOWN状态
            info("系统已进入关机状态", module="Main")
            
        except KeyboardInterrupt:
            info("用户中断，正在关闭", module="Main")
            self.cleanup()
        except Exception as e:
            error(f"致命错误: {e}", module="Main")
            self.cleanup()
            # 系统重启
            machine.reset()
    
    def cleanup(self):
        """清理资源"""
        try:
            info("开始清理过程", module="Main")
            
            # 停止状态机
            if hasattr(self, 'state_machine') and self.state_machine:
                self.state_machine.force_state("SHUTDOWN")
            
            # 清理LED
            if hasattr(self, 'led') and self.led:
                self.led.cleanup()
            
            # 断开网络连接
            if hasattr(self, 'network_manager') and self.network_manager:
                self.network_manager.disconnect_all()
            
            # 保存缓存
            
            info("清理完成", module="Main")
        except Exception as e:
            error(f"清理失败: {e}", module="Main")

def main():
    """主函数 - 系统入口点"""
    
    # 加载配置
    config = get_config()

    # 创建主控制器
    main_controller = MainController(config)
    
    # 启动系统
    main_controller.start_system()

if __name__ == "__main__":
    main()