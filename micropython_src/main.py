# main.py
import time
import gc
import utils
from daemon import start_critical_daemon
import logger

# --- WiFi凭据 ---
WIFI_SSID = "Lejurobot"
WIFI_PASSWORD = "Leju2022"

def main():
    # ==================================================================
    # 步骤1: 立即启动关键守护进程
    # ==================================================================
    if not start_critical_daemon():
        print("[CRITICAL] 守护进程启动失败！系统处于不稳定状态。")
        return

    print("="*50)
    print("[主程序] 守护进程已激活。现在开始初始化网络...")
    print("="*50)

    # ==================================================================
    # 步骤2: 连接到WiFi网络
    # ==================================================================
    if not utils.connect_wifi(WIFI_SSID, WIFI_PASSWORD):
        print("\n[CRITICAL] WiFi连接失败！主程序将终止。")
        print("[INFO] 守护进程将继续在后台运行以保护系统。")
        return

    # ==================================================================
    # 步骤2.5: WiFi连接成功后，设置默认的低功耗灯效
    # ==================================================================
    print("\n[主程序] 网络连接成功，设置默认灯效：LED 1 常亮。")
    # 调用新的 utils 函数来控制灯光。这个设置是静态的，不会持续消耗CPU。
    utils.set_effect('single_on', led_num=1)

    # --- 其他灯效示例 (注释掉备用) ---
    # 如果需要恢复双灯呼吸效果，可以调用:
    # utils.set_effect('breathing')
    #
    # 如果需要关闭所有灯，可以调用:
    # utils.set_effect('off')
    #
    # 如果需要让两个灯都常亮，可以调用:
    # utils.set_effect('both_on', brightness_u16=30000) # 可以指定亮度
    # -----------------------------------

    # ==================================================================
    # 步骤3: 同步NTP时间
    # ==================================================================
    if not utils.sync_ntp_time():
        print("[主程序] [WARNING] 时间同步失败！日志时间戳可能不准确。")
    
    print("\n[主程序] 网络初始化完成，开始执行核心业务逻辑...")
    
    # ==================================================================
    # 步骤4: 主业务逻辑循环
    # ==================================================================
    loop_count = 0
    try:
        while True:
            loop_count += 1
            print(f"\n[主程序] 正在执行业务逻辑，循环次数: {loop_count}。")
            
            logger.process_log_queue()
            
            time.sleep(10)
            
            if loop_count % 10 == 0:
                gc.collect()
                print(f"[主程序] 主程序执行了一次垃圾回收。")

    except KeyboardInterrupt:
        print("\n[主程序] 收到中断信号 (Ctrl+C)。")
    except Exception as e:
        print(f"\n[主程序] 主循环发生未捕获的异常: {e}")
    finally:
        logger.process_log_queue()
        print("[INFO] 主程序已停止。守护进程将继续在后台运行。")


if __name__ == "__main__":
    main()