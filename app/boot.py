# -*- coding: utf-8 -*-
"""
boot.py - ESP32C3 启动引导
精简启动入口, 完成最基础的初始化后启动主应用
"""

def main():
    """主启动流程"""
    try:
        # 安全模式检查
        from daemon import boot_safe_mode_check
        if boot_safe_mode_check():
            return  # 已进入安全模式, 退出启动
    except Exception as e:
        print("Boot safe mode check error:", e)
    
    try:
        # 启动主应用
        import main as app_main
        app_main.main()
    except Exception as e:
        print("Boot main app error:", e)

if __name__ == "__main__":
    main()
