# main.py
"""
主程序入口 - IoT ESP32C3 系统 (重构版本)

这个文件是整个IoT系统的核心控制器，重构后具有以下特点：
1. 事件驱动架构：所有模块通过事件总线通信
2. 配置驱动：所有配置通过config模块管理
3. 模块化设计：各模块独立，减少耦合
4. 错误隔离：单个模块失败不影响整体系统

系统架构：
- 事件总线：核心通信机制，连接所有模块
- 守护进程：负责硬件监控、看门狗、安全模式
- 异步任务：处理WiFi连接、NTP同步、LED效果
- 配置管理：集中管理所有系统配置
- 日志系统：事件驱动的日志记录和处理

设计原则：
- 事件驱动：模块间通过事件通信，避免直接依赖
- 配置驱动：避免硬编码，提高可维护性
- 稳定性优先：关键功能独立运行
- 异步非阻塞：避免单点阻塞影响系统
- 错误隔离：单个模块失败不影响整体
- 资源优化：合理使用内存和CPU资源
"""

import time
import gc
import uasyncio as asyncio

# 导入系统模块
import config
import event_bus
import daemon
import utils
import logger

async def main_business_loop():
    """
    主业务循环 - 系统核心运行逻辑 (重构版本)
    
    这个函数是系统的心脏，重构后具有以下特点：
    1. 事件驱动：通过事件总线监听和发布系统事件
    2. 配置驱动：使用config模块获取循环参数
    3. 模块化：各功能独立，减少耦合
    4. 错误隔离：单个任务失败不影响整体循环
    
    主要功能：
    - 定期处理日志队列
    - 执行垃圾回收
    - 系统状态监控
    - 发布系统心跳事件
    - 错误恢复机制
    
    设计特点：
    - 异步非阻塞：不影响其他任务运行
    - 事件驱动：通过事件总线与其他模块通信
    - 配置驱动：循环间隔等参数从配置获取
    - 错误隔离：单个任务失败不影响整体循环
    - 资源管理：主动进行内存管理
    
    注意：
    - 这个循环会一直运行，直到系统关闭
    - 所有操作都包含异常处理
    - 通过事件总线发布系统状态
    """
    print("\n[MAIN] 启动主业务循环...")
    
    # 从配置获取循环参数
    general_config = config.get_general_config()
    loop_interval = general_config.get('main_loop_interval', 5)
    gc_interval = general_config.get('gc_interval_loops', 20)
    status_check_interval = general_config.get('status_check_interval_loops', 12)
    
    loop_count = 0
    
    # 发布主循环启动事件
    event_bus.publish('main_loop_started')
    
    try:
        while True:
            loop_count += 1
            
            # 1. 处理日志队列（最高优先级）
            try:
                logger.process_log_queue()
            except Exception as e:
                print(f"[MAIN] [ERROR] 日志处理失败: {e}")
                event_bus.publish('log_critical', message=f"日志处理失败: {e}")
            
            # 2. 定期状态报告和心跳
            if loop_count % status_check_interval == 0:
                print(f"\n[MAIN] 系统运行正常，循环计数: {loop_count}")
                event_bus.publish('system_heartbeat', loop_count=loop_count)
                
                # 获取并发布系统状态
                try:
                    status = utils.get_system_status()
                    event_bus.publish('system_status_check', status=status, loop_count=loop_count)
                    
                    # 检查关键状态并发布相应事件
                    if not status.get('wifi_connected', False):
                        print("[MAIN] [WARNING] WiFi连接丢失")
                        event_bus.publish('wifi_disconnected_detected')
                        event_bus.publish('log_warning', message="WiFi连接丢失")
                    
                    if not status.get('ntp_synced', False):
                        print("[MAIN] [WARNING] 时间未同步")
                        event_bus.publish('ntp_not_synced_detected')
                        event_bus.publish('log_warning', message="时间未同步")
                        
                except Exception as e:
                    print(f"[MAIN] [ERROR] 系统状态检查失败: {e}")
                    event_bus.publish('log_critical', message=f"系统状态检查失败: {e}")
            
            # 3. 定期垃圾回收
            if loop_count % gc_interval == 0:
                try:
                    gc.collect()
                    mem_free = gc.mem_free()
                    print(f"[MAIN] 执行垃圾回收，可用内存: {mem_free} bytes")
                    
                    # 发布内存状态事件
                    event_bus.publish('memory_status', 
                                     free_bytes=mem_free, 
                                     loop_count=loop_count)
                    
                    # 内存使用检查
                    low_memory_threshold = general_config.get('low_memory_threshold', 10000)
                    if mem_free < low_memory_threshold:
                        print(f"[MAIN] [WARNING] 内存不足: {mem_free} bytes")
                        event_bus.publish('low_memory_warning', free_bytes=mem_free)
                        event_bus.publish('log_warning', message=f"内存不足: {mem_free} bytes")
                        
                except Exception as e:
                    print(f"[MAIN] [ERROR] 垃圾回收失败: {e}")
                    event_bus.publish('log_critical', message=f"垃圾回收失败: {e}")
            
            await asyncio.sleep(loop_interval)
            
            # 防止循环计数器溢出
            if loop_count >= 1000000:
                loop_count = 0
                event_bus.publish('loop_counter_reset')
            
    except asyncio.CancelledError:
        print("\n[MAIN] 主业务循环已停止")
        event_bus.publish('main_loop_stopped')
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 主业务循环异常: {e}")
        event_bus.publish('log_critical', message=f"主业务循环异常: {e}")

def start_critical_daemon():
    """
    启动关键系统守护进程 (重构版本)
    
    使用事件总线和配置管理启动守护进程：
    1. 初始化事件总线
    2. 加载系统配置
    3. 启动守护进程
    4. 发布系统启动事件
    
    返回:
        bool: 启动成功返回True，失败返回False
    """
    try:
        print("[MAIN] 初始化事件总线...")
        event_bus.init()
        
        print("[MAIN] 加载系统配置...")
        config.load_all_configs()
        
        print("[MAIN] 启动守护进程...")
        daemon_result = daemon.start_critical_daemon()
        
        if daemon_result:
            print("[MAIN] 守护进程启动成功")
            event_bus.publish('daemon_started')
            event_bus.publish('log_info', message="守护进程启动成功")
            return True
        else:
            print("[MAIN] [ERROR] 守护进程启动失败")
            event_bus.publish('daemon_start_failed')
            event_bus.publish('log_critical', message="守护进程启动失败")
            return False
            
    except Exception as e:
        print(f"[MAIN] [ERROR] 守护进程初始化异常: {e}")
        try:
            event_bus.publish('log_critical', message=f"守护进程初始化异常: {e}")
        except:
            pass  # 如果事件总线也失败，至少保证程序不崩溃
        return False

def main():
    """
    主程序入口：启动守护进程和异步系统 (重构版本)
    
    重构后的启动流程：
    1. 初始化事件总线和配置系统
    2. 启动关键系统守护进程（硬件监控、看门狗）
    3. 启动异步任务系统（WiFi、NTP、LED、业务逻辑）
    4. 进入主循环直到系统停止
    
    设计特点：
    - 事件驱动：所有模块通过事件总线通信
    - 配置驱动：系统参数通过配置管理
    - 错误隔离：单个模块失败不影响整体系统
    - 优雅关闭：支持中断信号和异常处理
    """
    print("\n" + "="*60)
    print("         ESP32-C3 IoT系统启动 (重构版本)")
    print("="*60)
    
    # 启动关键系统守护进程
    if not start_critical_daemon():
        print("[CRITICAL] 守护进程启动失败！系统无法继续运行")
        return

    print("[MAIN] 守护进程启动成功，开始初始化异步系统...")
    
    # 初始化日志系统
    try:
        print("[MAIN] 初始化日志系统...")
        logger.init_logger()
        event_bus.publish('logger_initialized')
        print("[MAIN] 日志系统初始化成功")
    except Exception as e:
        print(f"[MAIN] [ERROR] 日志系统初始化失败: {e}")
        # 日志系统失败不应阻止系统启动
    
    # 初始化LED系统
    try:
        print("[MAIN] 初始化LED系统...")
        if utils.init_leds():
            print("[MAIN] LED系统初始化成功")
        else:
            print("[MAIN] [WARNING] LED系统初始化失败")
    except Exception as e:
        print(f"[MAIN] [ERROR] LED系统初始化异常: {e}")
        # LED系统失败不应阻止系统启动
    
    # 发布系统启动事件
    event_bus.publish('system_starting')
    event_bus.publish('log_info', message="系统启动中...")

    try:
        # 定义异步系统运行函数
        async def run_system():
            # 发布异步系统启动事件
            event_bus.publish('async_system_starting')
            
            # 启动所有异步任务
            tasks = [
                asyncio.create_task(utils.start_all_tasks()),
                asyncio.create_task(main_business_loop())
            ]
            
            # 发布任务启动完成事件
            event_bus.publish('async_tasks_started', task_count=len(tasks))
            event_bus.publish('log_info', message=f"启动了 {len(tasks)} 个异步任务")
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                print(f"[MAIN] [ERROR] 系统任务错误: {e}")
                event_bus.publish('log_critical', message=f"系统任务错误: {e}")
                event_bus.publish('system_task_error', error=str(e))
            finally:
                # 清理任务
                print("[MAIN] 正在清理异步任务...")
                event_bus.publish('async_tasks_cleanup_started')
                
                for i, task in enumerate(tasks):
                    if not task.done():
                        task.cancel()
                        print(f"[MAIN] 取消任务 {i+1}/{len(tasks)}")
                
                event_bus.publish('async_tasks_cleanup_completed')
                event_bus.publish('log_info', message="异步任务清理完成")
        
        # 运行异步系统
        print("[MAIN] 启动异步任务系统...")
        event_bus.publish('log_info', message="启动异步任务系统")
        asyncio.run(run_system())
        
    except KeyboardInterrupt:
        print("\n[MAIN] 收到中断信号，正在关闭系统...")
        event_bus.publish('system_shutdown_requested', reason="keyboard_interrupt")
        event_bus.publish('log_info', message="收到中断信号，正在关闭系统")
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 系统运行错误: {e}")
        event_bus.publish('system_error', error=str(e))
        event_bus.publish('log_critical', message=f"系统运行错误: {e}")
    finally:
        # 发布系统关闭事件
        event_bus.publish('system_shutting_down')
        
        # 最后处理日志队列
        try:
            logger.process_log_queue()
        except Exception as e:
            print(f"[MAIN] [ERROR] 最终日志处理失败: {e}")
        
        print("[MAIN] 系统已停止，守护进程继续运行")
        event_bus.publish('system_stopped')
        
        # 执行垃圾回收
        gc.collect()
        print("[MAIN] 最终垃圾回收完成")


if __name__ == "__main__":
    main()