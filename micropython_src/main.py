# main.py
"""
ESP32-C3 IoT系统主程序

系统架构：
- 守护进程：负责硬件监控、看门狗、安全模式管理
- 异步任务：处理WiFi连接、NTP同步、LED效果
- 事件驱动：WiFi连接成功后自动触发NTP同步

主要功能：
1. WiFi智能连接（支持多网络配置）
2. NTP时间同步（事件驱动）
3. LED状态指示（呼吸灯、常亮等）
4. 系统监控（温度、看门狗、错误处理）
5. 日志记录（异步队列处理）
"""

import time
import gc
import utils
from daemon import start_critical_daemon
import logger
import uasyncio as asyncio

async def main_business_loop():
    """
    主业务逻辑异步循环：处理日志队列和系统维护
    """
    loop_count = 0
    print("\n[MAIN] 启动主业务循环...")
    
    try:
        while True:
            loop_count += 1
            
            # 处理日志队列
            logger.process_log_queue()
            
            # 定期状态报告
            if loop_count % 12 == 0:  # 每60秒报告一次
                print(f"\n[MAIN] 系统运行正常，循环计数: {loop_count}")
            
            # 定期垃圾回收
            if loop_count % 20 == 0:  # 每100秒执行一次
                gc.collect()
                print(f"[MAIN] 执行垃圾回收")
            
            await asyncio.sleep(5)
            
    except asyncio.CancelledError:
        print("\n[MAIN] 主业务循环已停止")
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 主业务循环异常: {e}")

def main():
    """
    主程序入口：启动守护进程和异步系统
    
    启动流程：
    1. 启动关键系统守护进程（硬件监控、看门狗）
    2. 启动异步任务系统（WiFi、NTP、LED、业务逻辑）
    3. 进入主循环直到系统停止
    """
    print("\n" + "="*60)
    print("         ESP32-C3 IoT系统启动")
    print("="*60)
    
    # 启动关键系统守护进程
    if not start_critical_daemon():
        print("[CRITICAL] 守护进程启动失败！系统无法继续运行")
        return

    print("[MAIN] 守护进程启动成功，开始初始化异步系统...")

    try:
        # 定义异步系统运行函数
        async def run_system():
            # 启动所有异步任务
            tasks = [
                asyncio.create_task(utils.start_all_tasks()),
                asyncio.create_task(main_business_loop())
            ]
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                print(f"[MAIN] [ERROR] 系统任务错误: {e}")
            finally:
                # 清理任务
                for task in tasks:
                    if not task.done():
                        task.cancel()
        
        # 运行异步系统
        print("[MAIN] 启动异步任务系统...")
        asyncio.run(run_system())
        
    except KeyboardInterrupt:
        print("\n[MAIN] 收到中断信号，正在关闭系统...")
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 系统运行错误: {e}")
    finally:
        # 最后处理日志队列
        logger.process_log_queue()
        print("[MAIN] 系统已停止，守护进程继续运行")
        # 执行垃圾回收
        gc.collect()


if __name__ == "__main__":
    main()