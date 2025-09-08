#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Home Assistant 自动配置仪表板脚本
用于自动创建风扇转速Gauge卡片

使用方法：
1. 修改下面的配置参数
2. 运行脚本：python auto_configure_dashboard.py
"""

import requests
import json
import time

# Home Assistant 配置
HA_URL = "http://your-ha-ip:8123"  # 修改为您的Home Assistant地址
HA_TOKEN = "your-long-lived-access-token"  # 修改为您的长期访问令牌

# 设备配置
DEVICE_ID = "esp32c3_7df23340"  # 您的设备ID
SENSOR_ENTITY = f"sensor.{DEVICE_ID}_fan_speed"  # 风扇转速传感器实体

def create_gauge_card():
    """创建Gauge卡片配置"""
    gauge_config = {
        "type": "gauge",
        "entity": SENSOR_ENTITY,
        "name": "风扇转速",
        "unit": "%",
        "min": 0,
        "max": 100,
        "severity": {
            "green": 0,
            "yellow": 30,
            "red": 70
        },
        "needle": True
    }
    return gauge_config

def get_dashboard_config():
    """获取当前仪表板配置"""
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{HA_URL}/api/lovelace/config", headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"获取仪表板配置失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def update_dashboard_config(config):
    """更新仪表板配置"""
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{HA_URL}/api/lovelace/config", 
            headers=headers, 
            data=json.dumps(config)
        )
        if response.status_code == 200:
            print("仪表板配置更新成功！")
            return True
        else:
            print(f"更新仪表板配置失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def add_gauge_to_dashboard():
    """将Gauge卡片添加到仪表板"""
    # 获取当前配置
    config = get_dashboard_config()
    if not config:
        print("无法获取仪表板配置")
        return False
    
    # 创建Gauge卡片
    gauge_card = create_gauge_card()
    
    # 查找或创建视图
    if "views" not in config:
        config["views"] = []
    
    # 查找设备控制视图
    device_view = None
    for view in config["views"]:
        if view.get("title") == "设备控制" or "device" in view.get("title", "").lower():
            device_view = view
            break
    
    # 如果没有找到设备视图，创建一个
    if not device_view:
        device_view = {
            "title": "设备控制",
            "path": "devices",
            "cards": []
        }
        config["views"].append(device_view)
    
    # 检查是否已存在Gauge卡片
    gauge_exists = False
    for card in device_view.get("cards", []):
        if (card.get("type") == "gauge" and 
            card.get("entity") == SENSOR_ENTITY):
            gauge_exists = True
            break
    
    # 如果不存在，添加Gauge卡片
    if not gauge_exists:
        if "cards" not in device_view:
            device_view["cards"] = []
        device_view["cards"].append(gauge_card)
        print(f"已添加Gauge卡片到视图: {device_view['title']}")
    else:
        print("Gauge卡片已存在，跳过添加")
    
    # 更新配置
    return update_dashboard_config(config)

def main():
    """主函数"""
    print("开始自动配置Home Assistant仪表板...")
    print(f"设备ID: {DEVICE_ID}")
    print(f"传感器实体: {SENSOR_ENTITY}")
    
    # 检查Home Assistant连接
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{HA_URL}/api/", headers=headers)
        if response.status_code != 200:
            print(f"无法连接到Home Assistant: {response.status_code}")
            return
    except Exception as e:
        print(f"连接Home Assistant失败: {e}")
        return
    
    print("Home Assistant连接成功！")
    
    # 添加Gauge卡片
    if add_gauge_to_dashboard():
        print("✅ 仪表板配置完成！")
        print("请在Home Assistant中刷新页面查看效果")
    else:
        print("❌ 仪表板配置失败")

if __name__ == "__main__":
    main()
