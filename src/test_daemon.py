# -*- coding: utf-8 -*-
"""
守护进程测试脚本

用于测试守护进程的各项功能
"""

import time
import daemon

def test_led_control():
    """测试LED控制"""
    print("[TEST] 测试LED控制...")
    
    # 测试各种LED状态
    states = ['normal', 'warning', 'error', 'safe_mode', 'off']
    
    for state in states:
        print(f"[TEST] 设置LED状态: {state}")
        daemon._led_controller.set_status(state)
        time.sleep(2)
    
    print("[TEST] LED控制测试完成")

def test_temperature_monitoring():
    """测试温度监控"""
    print("[TEST] 测试温度监控...")
    
    temp = daemon._get_temperature()
    if temp:
        print(f"[TEST] 当前温度: {temp:.1f}°C")
        print(f"[TEST] 温度阈值: {daemon.TEMP_THRESHOLD}°C")
        
        if temp >= daemon.TEMP_THRESHOLD:
            print("[TEST] 温度超过阈值，将进入安全模式")
    else:
        print("[TEST] 无法读取温度")
    
    print("[TEST] 温度监控测试完成")

def test_memory_monitoring():
    """测试内存监控"""
    print("[TEST] 测试内存监控...")
    
    memory = daemon._get_memory_usage()
    if memory:
        print(f"[TEST] 内存使用: {memory['percent']:.1f}%")
        print(f"[TEST] 内存阈值: {daemon.MEMORY_THRESHOLD}%")
        print(f"[TEST] 可用内存: {memory['free']}字节")
        
        if memory['percent'] >= daemon.MEMORY_THRESHOLD:
            print("[TEST] 内存使用超过阈值，将进入安全模式")
    else:
        print("[TEST] 无法获取内存信息")
    
    print("[TEST] 内存监控测试完成")

def test_safe_mode():
    """测试安全模式"""
    print("[TEST] 测试安全模式...")
    
    # 模拟进入安全模式
    daemon._enter_safe_mode("测试")
    
    # 等待几秒观察LED
    for i in range(10):
        status = daemon.get_daemon_status()
        print(f"[TEST] 安全模式状态: {status['safe_mode']}")
        time.sleep(1)
    
    print("[TEST] 安全模式测试完成")

def test_daemon_integration():
    """测试守护进程集成"""
    print("[TEST] 测试守护进程集成...")
    
    # 检查守护进程是否活跃
    if daemon.is_daemon_active():
        print("[TEST] 守护进程已启动")
        
        # 获取完整状态
        status = daemon.get_daemon_status()
        print(f"[TEST] 守护进程状态: {status}")
        
        # 等待一段时间观察监控
        print("[TEST] 观察30秒监控...")
        for i in range(30):
            time.sleep(1)
            if i % 10 == 0:
                status = daemon.get_daemon_status()
                print(f"[TEST] {i}s: 温度={status['temperature']}, 安全模式={status['safe_mode']}")
    else:
        print("[TEST] 守护进程未启动")
    
    print("[TEST] 守护进程集成测试完成")

def main():
    """主测试函数"""
    print("=" * 50)
    print("ESP32C3 守护进程测试")
    print("=" * 50)
    
    # 确保守护进程已启动
    if not daemon.is_daemon_active():
        print("[TEST] 启动守护进程...")
        daemon.start_daemon()
        time.sleep(2)
    
    # 运行测试
    try:
        test_led_control()
        test_temperature_monitoring()
        test_memory_monitoring()
        test_safe_mode()
        test_daemon_integration()
        
        print("\n[TEST] 所有测试完成")
        
    except Exception as e:
        print(f"[TEST] 测试过程中出错: {e}")
    
    print("=" * 50)

if __name__ == "__main__":
    main()