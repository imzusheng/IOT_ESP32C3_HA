#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Home Assistant 仪表板自动配置脚本
用于自动创建风扇转速Gauge卡片

使用方法：
1. 修改下面的配置参数
2. 运行脚本：python setup_ha_dashboard.py
"""

import requests
import json
import os

# 配置参数
HA_URL = "http://192.168.1.100:8123"  # 修改为您的Home Assistant地址
HA_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."  # 修改为您的长期访问令牌
DEVICE_ID = "esp32c3_7df23340"  # 您的设备ID

def create_lovelace_config():
    """创建Lovelace配置文件内容"""
    config = {
        "title": "Home",
        "views": [
            {
                "title": "设备控制",
                "path": "devices",
                "cards": [
                    {
                        "type": "gauge",
                        "entity": f"sensor.{DEVICE_ID}_fan_speed",
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
                    },
                    {
                        "type": "entities",
                        "title": "设备状态",
                        "entities": [
                            f"sensor.{DEVICE_ID}_temperature",
                            f"sensor.{DEVICE_ID}_humidity",
                            f"sensor.{DEVICE_ID}_fan_rpm"
                        ]
                    }
                ]
            }
        ]
    }
    return config

def save_lovelace_config():
    """保存Lovelace配置到文件"""
    config = create_lovelace_config()
    
    # 保存到当前目录
    config_file = "ui-lovelace.yaml"
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write("title: Home\n")
        f.write("views:\n")
        f.write("  - title: 设备控制\n")
        f.write("    path: devices\n")
        f.write("    cards:\n")
        f.write("      - type: gauge\n")
        f.write(f"        entity: sensor.{DEVICE_ID}_fan_speed\n")
        f.write("        name: 风扇转速\n")
        f.write("        unit: '%'\n")
        f.write("        min: 0\n")
        f.write("        max: 100\n")
        f.write("        severity:\n")
        f.write("          green: 0\n")
        f.write("          yellow: 30\n")
        f.write("          red: 70\n")
        f.write("        needle: true\n")
        f.write("      - type: entities\n")
        f.write("        title: 设备状态\n")
        f.write("        entities:\n")
        f.write(f"          - sensor.{DEVICE_ID}_temperature\n")
        f.write(f"          - sensor.{DEVICE_ID}_humidity\n")
        f.write(f"          - sensor.{DEVICE_ID}_fan_rpm\n")
    
    print(f"✅ Lovelace配置文件已保存: {config_file}")
    print("请将此文件复制到Home Assistant配置目录，并重启Home Assistant")

def main():
    """主函数"""
    print("Home Assistant 仪表板自动配置脚本")
    print(f"设备ID: {DEVICE_ID}")
    print()
    
    # 创建配置文件
    save_lovelace_config()
    
    print()
    print("📋 使用说明：")
    print("1. 将生成的 ui-lovelace.yaml 文件复制到Home Assistant配置目录")
    print("2. 在 configuration.yaml 中添加：")
    print("   lovelace:")
    print("     mode: yaml")
    print("3. 重启Home Assistant")
    print("4. 在仪表板中查看'设备控制'视图")

if __name__ == "__main__":
    main()
