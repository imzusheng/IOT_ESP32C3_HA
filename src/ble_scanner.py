# -*- coding: utf-8 -*-
"""
蓝牙BLE扫描器模块

提供蓝牙设备扫描和设备名称解析功能，专门针对ESP32C3设备优化。
支持高效的数据包解析和设备名称提取。

内存优化说明：
- 使用预分配的缓冲区减少内存分配
- 实现高效的数据包解析算法
- 避免不必要的字符串操作
- 支持异步扫描减少阻塞时间
"""

import bluetooth
import ubinascii
import ustruct
import time
import gc
from micropython import const

# =============================================================================
# 蓝牙数据包类型常量
# =============================================================================

# GAP数据类型
GAP_TYPE_FLAGS = const(0x01)                    # 标志
GAP_TYPE_INCOMPLETE_LIST_16BIT_SERVICE_UUIDS = const(0x02)  # 不完整的16位服务UUID列表
GAP_TYPE_COMPLETE_LIST_16BIT_SERVICE_UUIDS = const(0x03)    # 完整的16位服务UUID列表
GAP_TYPE_INCOMPLETE_LIST_32BIT_SERVICE_UUIDS = const(0x04)  # 不完整的32位服务UUID列表
GAP_TYPE_COMPLETE_LIST_32BIT_SERVICE_UUIDS = const(0x05)    # 完整的32位服务UUID列表
GAP_TYPE_INCOMPLETE_LIST_128BIT_SERVICE_UUIDS = const(0x06) # 不完整的128位服务UUID列表
GAP_TYPE_COMPLETE_LIST_128BIT_SERVICE_UUIDS = const(0x07)   # 完整的128位服务UUID列表
GAP_TYPE_SHORT_LOCAL_NAME = const(0x08)         # 短本地名称
GAP_TYPE_COMPLETE_LOCAL_NAME = const(0x09)      # 完整本地名称
GAP_TYPE_TX_POWER_LEVEL = const(0x0A)           # 发射功率级别
GAP_TYPE_DEVICE_CLASS = const(0x0D)            # 设备类别
GAP_TYPE_SIMPLE_PAIRING_HASH_C = const(0x0E)   # 简单配对哈希C
GAP_TYPE_SIMPLE_PAIRING_RANDOMIZER_R = const(0x0F)  # 简单配对随机数R
GAP_TYPE_SECURITY_MANAGER_TK_VALUE = const(0x10)  # 安全管理器TK值
GAP_TYPE_SECURITY_MANAGER_OOB_FLAGS = const(0x11)  # 安全管理器OOB标志
GAP_TYPE_SLAVE_CONNECTION_INTERVAL_RANGE = const(0x12)  # 从设备连接间隔范围
GAP_TYPE_SERVICE_DATA = const(0x16)             # 服务数据
GAP_TYPE_PUBLIC_TARGET_ADDRESS = const(0x17)   # 公共目标地址
GAP_TYPE_RANDOM_TARGET_ADDRESS = const(0x18)   # 随机目标地址
GAP_TYPE_APPEARANCE = const(0x19)               # 外观
GAP_TYPE_ADVERTISING_INTERVAL = const(0x1A)    # 广播间隔
GAP_TYPE_LE_BLUETOOTH_DEVICE_ADDRESS = const(0x1B)  # LE蓝牙设备地址
GAP_TYPE_LE_ROLE = const(0x1C)                  # LE角色
GAP_TYPE_SIMPLE_PAIRING_HASH_C256 = const(0x1D)  # 简单配对哈希C-256
GAP_TYPE_SIMPLE_PAIRING_RANDOMIZER_R256 = const(0x1E)  # 简单配对随机数R-256
GAP_TYPE_SERVICE_DATA_32BIT_UUID = const(0x20)  # 32位UUID服务数据
GAP_TYPE_SERVICE_DATA_128BIT_UUID = const(0x21)  # 128位UUID服务数据
GAP_TYPE_LE_SECURE_CONNECTIONS_CONFIRMATION_VALUE = const(0x22)  # LE安全连接确认值
GAP_TYPE_LE_SECURE_CONNECTIONS_RANDOM_VALUE = const(0x23)  # LE安全连接随机值
GAP_TYPE_URI = const(0x24)                      # URI
GAP_TYPE_INDOOR_POSITIONING = const(0x25)      # 室内定位
GAP_TYPE_TRANSPORT_DISCOVERY_DATA = const(0x26)  # 传输发现数据
GAP_TYPE_LE_SUPPORTED_FEATURES = const(0x27)   # LE支持的功能
GAP_TYPE_CHANNEL_MAP_UPDATE_INDICATION = const(0x28)  # 信道映射更新指示
GAP_TYPE_MANUFACTURER_SPECIFIC_DATA = const(0xFF)  # 制造商特定数据

# =============================================================================
# 蓝牙扫描器类
# =============================================================================

class BLEScanner:
    """
    蓝牙BLE扫描器
    
    作用：扫描并解析BLE设备的广播数据
    内存影响：极低（约200字节）
    """
    
    def __init__(self):
        self.ble = None
        self.scan_results = []
        self.scan_callback = None
        self.scanning = False
        self.max_devices = 20  # 限制最大设备数量
        self._parse_buffer = bytearray(31)  # 预分配解析缓冲区
        self.debug_mode = False  # 调试模式
        
    def initialize(self):
        """初始化蓝牙扫描器"""
        try:
            self.ble = bluetooth.BLE()
            self.ble.active(True)
            time.sleep_ms(100)  # 等待蓝牙激活
            print("[BLE] 扫描器初始化完成")
            return True
        except Exception as e:
            print(f"[BLE] 初始化失败: {e}")
            return False
    
    def deinitialize(self):
        """关闭蓝牙扫描器"""
        try:
            if self.scanning:
                self.stop_scan()
            if self.ble:
                self.ble.active(False)
                self.ble = None
            print("[BLE] 扫描器已关闭")
        except Exception as e:
            print(f"[BLE] 关闭失败: {e}")
    
    def start_scan(self, duration=10000, callback=None):
        """
        开始扫描蓝牙设备
        
        参数:
            duration: 扫描持续时间（毫秒）
            callback: 扫描结果回调函数
        """
        if not self.ble:
            if not self.initialize():
                return False
        
        try:
            # 执行垃圾回收
            gc.collect()
            
            self.scan_callback = callback
            self.scan_results = []
            self.scanning = True
            
            # 设置IRQ处理
            self.ble.irq(self._irq_handler)
            
            # 开始扫描 - 使用更短的扫描间隔
            self.ble.gap_scan(duration, 20000, 20000)
            print(f"[BLE] 开始扫描，持续时间: {duration}ms")
            print(f"[内存] 可用内存: {gc.mem_free()} 字节")
            return True
            
        except Exception as e:
            print(f"[BLE] 扫描启动失败: {e}")
            self.scanning = False
            return False
    
    def stop_scan(self):
        """停止扫描"""
        try:
            if self.ble and self.scanning:
                self.ble.gap_scan(None)
                self.scanning = False
                print("[BLE] 扫描已停止")
        except Exception as e:
            print(f"[BLE] 停止扫描失败: {e}")
    
    def _irq_handler(self, event, data):
        """蓝牙事件处理"""
        try:
            if event == 5:  # IRQ_SCAN_RESULT
                addr_type, addr, adv_type, rssi, adv_data = data
                
                # 立即执行垃圾回收
                gc.collect()
                
                # 解析设备信息
                device_info = self._parse_adv_data(addr_type, addr, adv_type, rssi, adv_data)
                
                if device_info:
                    # 检查是否已存在相同地址的设备
                    device_mac = device_info['address']
                    existing_device = None
                    
                    for i, existing in enumerate(self.scan_results):
                        if existing['address'] == device_mac:
                            existing_device = i
                            break
                    
                    if existing_device is not None:
                        # 更新现有设备信息（保留信号强度更强的信息）
                        if device_info['rssi'] > self.scan_results[existing_device]['rssi']:
                            self.scan_results[existing_device] = device_info
                    else:
                        # 添加新设备，限制设备数量
                        if len(self.scan_results) < self.max_devices:
                            self.scan_results.append(device_info)
                        
                        # 调用回调函数
                        if self.scan_callback:
                            self.scan_callback(device_info)
                        
            elif event == 6:  # IRQ_SCAN_DONE
                self.scanning = False
                print(f"[BLE] 扫描完成，发现 {len(self.scan_results)} 个设备")
                
        except Exception as e:
            print(f"[BLE] IRQ处理失败: {e}")
            # 发生错误时清理内存
            gc.collect()
    
    def _format_mac_address(self, mac_address):
        """格式化MAC地址为标准格式（使用冒号分隔）"""
        if len(mac_address) == 12:
            # 将连续的十六进制字符串格式化为XX:XX:XX:XX:XX:XX
            return ':'.join([mac_address[i:i+2] for i in range(0, 12, 2)])
        return mac_address
    
    def _parse_device_name(self, adv_data):
        """
        解析设备名称 - 修复版本（基于BLE_ADV.md）
        
        主要修复：
        1. 修正长度字段的解析逻辑
        2. 增强错误处理和边界检查
        3. 优化字符编码处理
        4. 改进调试输出
        5. 分别保存完整名称和短名称，优先使用完整名称
        """
        if not adv_data:
            return "未知"
        
        # 转换为bytes
        try:
            if isinstance(adv_data, memoryview):
                adv_bytes = bytes(adv_data)
            elif isinstance(adv_data, (bytes, bytearray)):
                adv_bytes = bytes(adv_data)
            else:
                return "未知"
        except:
            return "未知"
        
        if len(adv_bytes) == 0:
            return "未知"
        
        # 解析AD结构
        index = 0
        device_name = ""
        complete_name = ""  # 优先保存完整名称
        short_name = ""     # 备用短名称
        
        # 调试模式：显示解析过程
        if self.debug_mode:
            print(f"[DEBUG] 开始解析设备名称，数据长度: {len(adv_bytes)}")
            print(f"[DEBUG] 原始数据: {ubinascii.hexlify(adv_bytes).decode()}")
        
        while index < len(adv_bytes):
            try:
                # 读取长度字段 (1个字节)
                if index >= len(adv_bytes):
                    break
                
                length = adv_bytes[index]
                if length == 0:
                    # 长度为0，跳出循环
                    break
                
                # 检查是否有足够的数据（长度字段本身不包含在长度计算中）
                if index + 1 + length > len(adv_bytes):
                    if self.debug_mode:
                        print(f"[DEBUG] 数据不完整，位置: {index}, 长度: {length}, 剩余数据: {len(adv_bytes) - index}")
                    break
                
                # 读取类型字段 (1个字节)
                if index + 1 >= len(adv_bytes):
                    break
                
                ad_type = adv_bytes[index + 1]
                
                # 计算数据长度 (length - 1，因为length包含了类型字节)
                data_len = length - 1
                data_start = index + 2
                data_end = data_start + data_len
                
                # 调试模式：显示每个字段
                if self.debug_mode:
                    print(f"[DEBUG] 字段位置: {index}, 长度字段值: {length}, 类型: 0x{ad_type:02X}, 数据长度: {data_len}")
                
                # 检查是否是设备名称类型
                if ad_type in [0x08, 0x09]:  # 0x08=短名称, 0x09=完整名称
                    if data_len > 0 and data_end <= len(adv_bytes):  # 确保有名称数据且不越界
                        name_bytes = adv_bytes[data_start:data_end]
                        
                        if self.debug_mode:
                            print(f"[DEBUG] 发现名称字段，类型: 0x{ad_type:02X}, 原始数据: {ubinascii.hexlify(name_bytes).decode()}")
                        
                        # 解析名称数据
                        try:
                            # 首先尝试UTF-8编码
                            parsed_name = name_bytes.decode('utf-8').strip()
                            
                            # 过滤掉控制字符和不可打印字符
                            clean_name = ''.join(c for c in parsed_name if c.isprintable() and ord(c) >= 32)
                            
                            if clean_name and len(clean_name.strip()) > 0:
                                clean_name = clean_name.strip()
                                
                                if ad_type == 0x09:  # 完整名称
                                    complete_name = clean_name
                                    if self.debug_mode:
                                        print(f"[DEBUG] 成功解析完整名称: {complete_name}")
                                elif ad_type == 0x08:  # 短名称
                                    short_name = clean_name
                                    if self.debug_mode:
                                        print(f"[DEBUG] 成功解析短名称: {short_name}")
                                        
                        except UnicodeDecodeError:
                            # UTF-8解码失败，尝试ASCII编码
                            try:
                                parsed_name = name_bytes.decode('ascii', errors='ignore').strip()
                                clean_name = ''.join(c for c in parsed_name if c.isprintable() and ord(c) >= 32)
                                
                                if clean_name and len(clean_name.strip()) > 0:
                                    clean_name = clean_name.strip()
                                    
                                    if ad_type == 0x09:  # 完整名称
                                        complete_name = clean_name
                                        if self.debug_mode:
                                            print(f"[DEBUG] 成功解析完整名称(ASCII): {complete_name}")
                                    elif ad_type == 0x08:  # 短名称
                                        short_name = clean_name
                                        if self.debug_mode:
                                            print(f"[DEBUG] 成功解析短名称(ASCII): {short_name}")
                            except:
                                if self.debug_mode:
                                    print(f"[DEBUG] 名称解析失败，原始数据: {ubinascii.hexlify(name_bytes).decode()}")
                
                # 移动到下一个AD结构
                # 关键修复：正确的偏移量计算
                index += 1 + length  # 1字节长度字段 + length字节的数据（包含类型字段）
                
            except Exception as e:
                if self.debug_mode:
                    print(f"[DEBUG] 解析AD结构时出错: {e}")
                break
        
        # 确定最终的设备名称
        # 优先级：完整名称 > 短名称 > 未知
        if complete_name:
            device_name = complete_name
        elif short_name:
            device_name = short_name
        else:
            device_name = "未知"
        
        if self.debug_mode:
            print(f"[DEBUG] 最终设备名称: {device_name}")
        
        return device_name
    
        
    def _parse_adv_data(self, addr_type, addr, adv_type, rssi, adv_data):
        """
        解析广播数据（增强版）
        
        参数:
            addr_type: 地址类型
            addr: 设备地址
            adv_type: 广播类型
            rssi: 信号强度
            adv_data: 广播数据
            
        返回:
            设备信息字典
        """
        try:
            # 使用增强的设备信息结构
            mac_address = ubinascii.hexlify(addr).decode()
            formatted_mac = self._format_mac_address(mac_address)
            
            device_info = {
                'address': formatted_mac,
                'address_raw': mac_address,  # 保留原始地址
                'address_type': addr_type,
                'rssi': rssi,
                'name': '',
                'type': adv_type,
                'adv_data_hex': '',
                'services': [],
                'manufacturer_data': '',
                'appearance': '',
                'tx_power': None,
                'flags': ''
            }
            
            # 转换广播数据为十六进制字符串用于显示
            device_info['adv_data_hex'] = ubinascii.hexlify(adv_data).decode()
            
            # 调试模式：显示原始广播数据
            if self.debug_mode and len(adv_data) > 0:
                print(f"[DEBUG] 设备 {device_info['address']} 原始广播数据: {device_info['adv_data_hex']}")
            
            # 解析广播数据
            pos = 0
            data_len = len(adv_data)
            
            while pos + 1 < data_len:
                # 获取字段长度
                field_len = adv_data[pos]
                if field_len == 0:
                    break
                
                # 检查是否超出数据范围
                if pos + field_len >= data_len:
                    break
                
                # 获取字段类型
                field_type = adv_data[pos + 1]
                
                # 解析不同类型的字段
                if field_type == GAP_TYPE_SHORT_LOCAL_NAME or field_type == GAP_TYPE_COMPLETE_LOCAL_NAME:
                    # 名称解析由_parse_device_name方法统一处理
                    pass
                
                # 调试模式：显示所有字段解析过程
                if self.debug_mode:
                    print(f"[DEBUG] 字段 - 长度: {field_len}, 类型: 0x{field_type:02X} ({self._get_field_type_name(field_type)})")
                    field_data = adv_data[pos + 2:pos + field_len + 1]
                    print(f"[DEBUG] 数据: {ubinascii.hexlify(field_data).decode()}")
                
                elif field_type == GAP_TYPE_FLAGS:
                    try:
                        flags_data = adv_data[pos + 2:pos + field_len + 1]
                        device_info['flags'] = ubinascii.hexlify(flags_data).decode()
                    except:
                        pass
                
                elif field_type == GAP_TYPE_TX_POWER_LEVEL:
                    try:
                        device_info['tx_power'] = adv_data[pos + 2]
                    except:
                        pass
                
                elif field_type == GAP_TYPE_APPEARANCE:
                    try:
                        appearance_data = adv_data[pos + 2:pos + field_len + 1]
                        device_info['appearance'] = ubinascii.hexlify(appearance_data).decode()
                    except:
                        pass
                
                elif field_type == GAP_TYPE_MANUFACTURER_SPECIFIC_DATA:
                    try:
                        mfg_data = adv_data[pos + 2:pos + field_len + 1]
                        device_info['manufacturer_data'] = ubinascii.hexlify(mfg_data).decode()
                    except:
                        pass
                
                elif field_type in [GAP_TYPE_COMPLETE_LIST_16BIT_SERVICE_UUIDS, 
                                 GAP_TYPE_INCOMPLETE_LIST_16BIT_SERVICE_UUIDS]:
                    try:
                        service_data = adv_data[pos + 2:pos + field_len + 1]
                        # 解析16位服务UUID
                        for i in range(0, len(service_data), 2):
                            if i + 1 < len(service_data):
                                uuid_bytes = service_data[i:i+2]
                                uuid_hex = ubinascii.hexlify(uuid_bytes).decode()
                                device_info['services'].append(uuid_hex)
                    except:
                        pass
                
                # 移动到下一个字段
                pos += field_len + 1
            
            # 使用_parse_device_name方法解析设备名称
            device_info['name'] = self._parse_device_name(adv_data)
            
            return device_info
            
        except Exception as e:
            print(f"[BLE] 解析广播数据失败: {e}")
            return None
    
    def get_scan_results(self):
        """获取扫描结果"""
        return self.scan_results.copy()
    
    def get_scan_results_sorted_by_rssi(self):
        """获取按信号强度排序的扫描结果"""
        return sorted(self.scan_results, key=lambda x: x.get('rssi', -100), reverse=True)
    
    def clear_scan_results(self):
        """清空扫描结果"""
        self.scan_results = []

# =============================================================================
# 模块初始化
# =============================================================================

# 创建全局实例
_ble_scanner = None

def get_ble_scanner():
    """获取蓝牙扫描器实例"""
    global _ble_scanner
    if _ble_scanner is None:
        _ble_scanner = BLEScanner()
    return _ble_scanner

# =============================================================================
# 交互式蓝牙扫描器
# =============================================================================

class InteractiveBLEScanner:
    """
    交互式蓝牙扫描器
    
    作用：提供交互式蓝牙设备扫描和选择功能
    内存影响：低（约300字节）
    """
    
    def __init__(self):
        self.scanner = get_ble_scanner()
        self.selected_device = None
        self.debug_mode = False  # 调试模式标志
        
    def set_debug_mode(self, enabled):
        """设置调试模式"""
        self.debug_mode = enabled
        print(f"[BLE] 调试模式: {'开启' if enabled else '关闭'}")
        
    def scan_and_display(self, duration=10000):
        """
        扫描并显示蓝牙设备
        
        参数:
            duration: 扫描持续时间（毫秒）
        """
        print("[BLE] 开始扫描蓝牙设备...")
        
        # 执行垃圾回收
        gc.collect()
        print(f"[内存] 扫描前可用内存: {gc.mem_free()} 字节")
        
        # 设置调试模式
        self.scanner.debug_mode = self.debug_mode
        
        # 开始扫描
        if not self.scanner.start_scan(duration):
            print("[BLE] 扫描启动失败")
            return False
        
        # 等待扫描完成
        import time
        start_time = time.ticks_ms()
        while self.scanner.scanning:
            if time.ticks_diff(time.ticks_ms(), start_time) > duration + 2000:
                print("[BLE] 扫描超时")
                break
            time.sleep_ms(200)  # 增加延迟减少CPU使用
        
        # 执行垃圾回收
        gc.collect()
        print(f"[内存] 扫描后可用内存: {gc.mem_free()} 字节")
        
        # 获取排序后的结果
        devices = self.scanner.get_scan_results_sorted_by_rssi()
        
        if not devices:
            print("[BLE] 未发现任何蓝牙设备")
            return False
        
        # 显示设备列表
        self._display_device_table(devices)
        
        return True
    
    def _display_device_table(self, devices):
        """显示设备表格（增强版，包含详细解析信息）"""
        print("\n" + "="*100)
        print("蓝牙设备扫描结果 (按信号强度排序)")
        print("="*100)
        print(f"{'序号':<4} {'信号':<6} {'地址':<12} {'名称':<20} {'类型':<8} {'服务':<8} {'详细数据':<25}")
        print("-" * 100)
        
        for i, device in enumerate(devices):
            index = i + 1
            rssi = device.get('rssi', -100)
            address = device.get('address', 'Unknown')
            name = device.get('name', 'Unknown')
            addr_type = device.get('address_type', 0)
            services = device.get('services', [])
            adv_data_hex = device.get('adv_data_hex', '')
            
            # 截断过长的名称
            if len(name) > 18:
                name = name[:15] + "..."
            
            # 地址类型显示
            addr_type_str = "Public" if addr_type == 0 else "Random"
            
            # 服务数量显示
            services_str = f"{len(services)}" if services else "0"
            
            # 解析广播数据显示主要信息
            details = []
            if adv_data_hex:
                try:
                    adv_data = bytearray.fromhex(adv_data_hex)
                    pos = 0
                    data_len = len(adv_data)
                    
                    while pos + 1 < data_len:
                        field_len = adv_data[pos]
                        if field_len == 0:
                            break
                        
                        if pos + field_len >= data_len:
                            break
                        
                        field_type = adv_data[pos + 1]
                        
                        # 显示主要字段类型
                        if field_type == GAP_TYPE_FLAGS:
                            details.append("FLAGS")
                        elif field_type == GAP_TYPE_TX_POWER_LEVEL:
                            try:
                                tx_power = adv_data[pos + 2]
                                details.append(f"TX:{tx_power}")
                            except:
                                details.append("TX:?")
                        elif field_type == GAP_TYPE_APPEARANCE:
                            details.append("APP")
                        elif field_type == GAP_TYPE_MANUFACTURER_SPECIFIC_DATA:
                            details.append("MFG")
                        elif field_type in [GAP_TYPE_COMPLETE_LIST_16BIT_SERVICE_UUIDS, 
                                         GAP_TYPE_INCOMPLETE_LIST_16BIT_SERVICE_UUIDS]:
                            details.append("SVC")
                        
                        # 限制显示的字段数量
                        if len(details) >= 3:
                            break
                        
                        pos += field_len + 1
                except:
                    pass
            
            details_str = "+".join(details) if details else "N/A"
            if len(details_str) > 23:
                details_str = details_str[:20] + "..."
            
            print(f"{index:<4} {rssi:<6} {address:<12} {name:<20} {addr_type_str:<8} {services_str:<8} {details_str:<25}")
        
        print("="*100)
        print(f"共发现 {len(devices)} 个设备")
        print()
        
        # 显示前3个设备的详细信息
        if len(devices) > 0:
            print("\n" + "="*80)
            print("前3个设备的详细解析信息")
            print("="*80)
            
            for i in range(min(3, len(devices))):
                device = devices[i]
                print(f"\n设备 {i+1}: {device.get('name', 'Unknown')} ({device.get('address', 'Unknown')})")
                print("-" * 60)
                
                adv_data_hex = device.get('adv_data_hex', '')
                if adv_data_hex:
                    self._parse_and_display_adv_data(adv_data_hex)
                else:
                    print("无广播数据")
            
            print("="*80)
    
    def _display_device_details(self, device):
        """显示设备详细信息"""
        print("\n" + "="*60)
        print("设备详细信息")
        print("="*60)
        
        # 基本信息
        name = device.get('name', 'Unknown')
        address = device.get('address', 'Unknown')
        addr_type = device.get('address_type', 0)
        rssi = device.get('rssi', -100)
        adv_type = device.get('type', 'Unknown')
        
        print(f"设备名称: {name}")
        print(f"设备地址: {address}")
        print(f"地址类型: {'Public' if addr_type == 0 else 'Random'}")
        print(f"信号强度: {rssi} dBm")
        print(f"广播类型: {adv_type}")
        
        # 发射功率
        tx_power = device.get('tx_power')
        if tx_power is not None:
            print(f"发射功率: {tx_power} dBm")
        
        # 外观
        appearance = device.get('appearance')
        if appearance:
            print(f"外观标识: {appearance}")
        
        # 标志
        flags = device.get('flags')
        if flags:
            print(f"标志位: {flags}")
        
        # 制造商数据
        manufacturer_data = device.get('manufacturer_data')
        if manufacturer_data:
            print(f"制造商数据: {manufacturer_data}")
        
        # 服务UUID
        services = device.get('services', [])
        if services:
            print(f"服务UUID: {', '.join(services)}")
        
        # 广播数据（十六进制）
        adv_data_hex = device.get('adv_data_hex')
        if adv_data_hex:
            print(f"广播数据: {adv_data_hex}")
            
            # 显示解析后的广播数据
            print("\n广播数据解析:")
            self._parse_and_display_adv_data(adv_data_hex)
        
        print("="*60)
    
    def _parse_and_display_adv_data(self, hex_data):
        """解析并显示广播数据结构"""
        try:
            # 转换为字节数组
            adv_data = bytearray.fromhex(hex_data)
            
            pos = 0
            data_len = len(adv_data)
            
            while pos + 1 < data_len:
                field_len = adv_data[pos]
                if field_len == 0:
                    break
                
                if pos + field_len >= data_len:
                    break
                
                field_type = adv_data[pos + 1]
                field_data = adv_data[pos + 2:pos + field_len + 1]
                
                # 显示字段信息
                type_name = self._get_field_type_name(field_type)
                field_hex = ubinascii.hexlify(field_data).decode()
                
                print(f"  长度: {field_len}, 类型: 0x{field_type:02X} ({type_name})")
                print(f"  数据: {field_hex}")
                
                # 如果是名称字段，显示可读内容
                if field_type in [GAP_TYPE_SHORT_LOCAL_NAME, GAP_TYPE_COMPLETE_LOCAL_NAME]:
                    try:
                        name = field_data.decode('utf-8', errors='ignore')
                        print(f"  名称: {name}")
                    except:
                        pass
                
                print()
                
                pos += field_len + 1
                
        except Exception as e:
            print(f"  解析错误: {e}")
    
    def _get_field_type_name(self, field_type):
        """获取字段类型名称"""
        type_names = {
            0x01: "标志",
            0x02: "不完整16位服务UUID列表",
            0x03: "完整16位服务UUID列表",
            0x04: "不完整32位服务UUID列表",
            0x05: "完整32位服务UUID列表",
            0x06: "不完整128位服务UUID列表",
            0x07: "完整128位服务UUID列表",
            0x08: "短本地名称",
            0x09: "完整本地名称",
            0x0A: "发射功率",
            0x0D: "设备类别",
            0x12: "从设备连接间隔范围",
            0x16: "服务数据",
            0x17: "公共目标地址",
            0x18: "随机目标地址",
            0x19: "外观",
            0x1A: "广播间隔",
            0x1B: "LE蓝牙设备地址",
            0x1C: "LE角色",
            0x20: "32位UUID服务数据",
            0x21: "128位UUID服务数据",
            0x24: "URI",
            0x25: "室内定位",
            0x26: "传输发现数据",
            0x27: "LE支持的功能",
            0x28: "信道映射更新指示",
            0xFF: "制造商特定数据"
        }
        return type_names.get(field_type, "未知类型")
    
    
    def select_device_interactive(self):
        """交互式选择设备（增强版）"""
        devices = self.scanner.get_scan_results_sorted_by_rssi()
        
        if not devices:
            print("[BLE] 没有可选择的设备")
            return None
        
        while True:
            try:
                print("\n可用操作:")
                print("  1-{}: 选择设备".format(len(devices)))
                print("  d <序号>: 查看设备详细信息")
                print("  q: 退出")
                
                user_input = input("请输入操作: ").strip()
                
                if user_input.lower() == 'q':
                    print("[BLE] 退出设备选择")
                    return None
                
                # 检查是否为详细信息命令
                if user_input.lower().startswith('d '):
                    try:
                        detail_index = int(user_input[2:]) - 1
                        if 0 <= detail_index < len(devices):
                            self._display_device_details(devices[detail_index])
                        else:
                            print(f"[BLE] 无效的设备序号，请输入 1-{len(devices)}")
                    except ValueError:
                        print("[BLE] 请输入有效的数字序号")
                    continue
                
                # 普通选择
                device_index = int(user_input) - 1
                
                if 0 <= device_index < len(devices):
                    selected = devices[device_index]
                    print(f"[BLE] 已选择设备: {selected.get('name', 'Unknown')} ({selected.get('address', 'Unknown')})")
                    
                    # 显示设备详细信息
                    self._display_device_details(selected)
                    
                    # 确认选择
                    confirm = input("\n确认选择此设备? (y/n): ").lower()
                    if confirm == 'y':
                        self.selected_device = selected
                        return selected
                    else:
                        print("[BLE] 重新选择设备")
                else:
                    print(f"[BLE] 无效的设备序号，请输入 1-{len(devices)}")
                    
            except ValueError:
                print("[BLE] 请输入有效的数字序号")
            except KeyboardInterrupt:
                print("[BLE] 用户中断选择")
                return None
    
    def get_selected_device(self):
        """获取当前选中的设备"""
        return self.selected_device
    
    def clear_selection(self):
        """清除选择"""
        self.selected_device = None

# =============================================================================
# 扫描和连接工具函数
# =============================================================================

def scan_ble_devices_interactive(duration=10000):
    """
    交互式扫描蓝牙设备
    
    参数:
        duration: 扫描持续时间（毫秒）
    
    返回:
        选择的设备信息字典，如果未选择则返回None
    """
    interactive_scanner = InteractiveBLEScanner()
    
    if interactive_scanner.scan_and_display(duration):
        return interactive_scanner.select_device_interactive()
    else:
        return None

def connect_to_selected_device(device_info):
    """
    连接到选中的设备
    
    参数:
        device_info: 设备信息字典
    
    返回:
        连接状态
    """
    if not device_info:
        print("[BLE] 没有选择设备")
        return False
    
    try:
        address = device_info.get('address')
        addr_type = device_info.get('address_type', 0)
        name = device_info.get('name', 'Unknown')
        
        print(f"[BLE] 正在连接到设备: {name} ({address})")
        
        # 这里需要实现具体的连接逻辑
        # 由于MicroPython的蓝牙连接API可能因版本而异，这里提供框架
        
        # 示例连接代码（需要根据实际API调整）:
        # ble = bluetooth.BLE()
        # ble.active(True)
        # ble.gap_connect(addr_type, bytes.fromhex(address))
        
        print("[BLE] 连接功能需要根据具体蓝牙API实现")
        return False
        
    except Exception as e:
        print(f"[BLE] 连接失败: {e}")
        return False

def parse_adv_data_hex(hex_data):
    """
    解析十六进制格式的广播数据（独立函数）
    
    参数:
        hex_data: 十六进制格式的广播数据字符串
    
    返回:
        解析后的设备信息字典
    """
    try:
        # 转换为字节数组
        adv_data = bytearray.fromhex(hex_data)
        
        # 创建虚拟设备信息
        device_info = {
            'address': 'N/A',
            'address_type': 0,
            'rssi': 0,
            'name': '',
            'type': 'Unknown',
            'adv_data_hex': hex_data,
            'services': [],
            'manufacturer_data': '',
            'appearance': '',
            'tx_power': None,
            'flags': ''
        }
        
        # 解析广播数据
        pos = 0
        data_len = len(adv_data)
        
        while pos + 1 < data_len:
            field_len = adv_data[pos]
            if field_len == 0:
                break
            
            if pos + field_len >= data_len:
                break
            
            field_type = adv_data[pos + 1]
            field_data = adv_data[pos + 2:pos + field_len + 1]
            
            # 解析不同类型的字段
            if field_type == GAP_TYPE_SHORT_LOCAL_NAME or field_type == GAP_TYPE_COMPLETE_LOCAL_NAME:
                try:
                    device_info['name'] = field_data.decode('utf-8', errors='ignore')
                except:
                    device_info['name'] = ''
            
            elif field_type == GAP_TYPE_FLAGS:
                try:
                    device_info['flags'] = ubinascii.hexlify(field_data).decode()
                except:
                    pass
            
            elif field_type == GAP_TYPE_TX_POWER_LEVEL:
                try:
                    device_info['tx_power'] = field_data[0]
                except:
                    pass
            
            elif field_type == GAP_TYPE_APPEARANCE:
                try:
                    device_info['appearance'] = ubinascii.hexlify(field_data).decode()
                except:
                    pass
            
            elif field_type == GAP_TYPE_MANUFACTURER_SPECIFIC_DATA:
                try:
                    device_info['manufacturer_data'] = ubinascii.hexlify(field_data).decode()
                except:
                    pass
            
            elif field_type in [GAP_TYPE_COMPLETE_LIST_16BIT_SERVICE_UUIDS, 
                             GAP_TYPE_INCOMPLETE_LIST_16BIT_SERVICE_UUIDS]:
                try:
                    # 解析16位服务UUID
                    for i in range(0, len(field_data), 2):
                        if i + 1 < len(field_data):
                            uuid_bytes = field_data[i:i+2]
                            uuid_hex = ubinascii.hexlify(uuid_bytes).decode()
                            device_info['services'].append(uuid_hex)
                except:
                    pass
            
            pos += field_len + 1
        
        return device_info
        
    except Exception as e:
        print(f"[BLE] 解析失败: {e}")
        return None

def display_adv_data_analysis(hex_data):
    """
    显示广播数据的详细分析
    
    参数:
        hex_data: 十六进制格式的广播数据字符串
    """
    print("=" * 80)
    print("广播数据分析")
    print("=" * 80)
    
    print(f"原始数据: {hex_data}")
    print()
    
    # 解析数据
    device_info = parse_adv_data_hex(hex_data)
    
    if device_info:
        print("解析结果:")
        print(f"  设备名称: {device_info.get('name', 'N/A')}")
        print(f"  信号强度: {device_info.get('rssi', 'N/A')} dBm")
        print(f"  地址类型: {'Public' if device_info.get('address_type') == 0 else 'Random'}")
        print(f"  发射功率: {device_info.get('tx_power', 'N/A')}")
        print(f"  外观标识: {device_info.get('appearance', 'N/A')}")
        print(f"  标志位: {device_info.get('flags', 'N/A')}")
        print(f"  制造商数据: {device_info.get('manufacturer_data', 'N/A')}")
        
        services = device_info.get('services', [])
        if services:
            print(f"  服务UUID: {', '.join(services)}")
        else:
            print("  服务UUID: 无")
        
        print()
        print("详细字段解析:")
        interactive_scanner = InteractiveBLEScanner()
        interactive_scanner._parse_and_display_adv_data(hex_data)
    else:
        print("解析失败")
    
    print("=" * 80)

def parse_coros_data_enhanced(hex_data):
    """
    增强版COROS数据解析函数 - 集成到BLE扫描器中使用
    
    参数:
        hex_data: 十六进制字符串
    
    返回:
        解析后的列表和设备名称
    """
    result = []
    device_name = "未知设备"
    index = 0
    len_hex = len(hex_data)
    
    # 类型描述映射
    type_descriptions = {
        0x01: "标志",
        0x08: "短本地名称", 
        0x09: "完整设备名称",
        0x19: "外观",
        0x43: "设备标识",
        0x32: "设备信息",
        0xFF: "制造商特定数据"
    }
    
    print(f"[COROS] 解析数据: {hex_data}")
    
    while index < len_hex:
        # 读取长度 (2个十六进制字符 = 1字节)
        if index + 2 > len_hex:
            break
        length = int(hex_data[index:index+2], 16)
        index += 2
        
        print(f"[COROS] 位置 {index-2}: 长度字段 = {length}")
        
        # 读取类型 (2个十六进制字符 = 1字节)
        if index + 2 > len_hex:
            break
        type_val = int(hex_data[index:index+2], 16)
        index += 2
        
        print(f"[COROS] 位置 {index-2}: 类型字段 = 0x{type_val:02X}")
        
        # 关键修正：数据长度应该是 (length - 1) * 2
        data_len = (length - 1) * 2
        if index + data_len > len_hex:
            data_hex = hex_data[index:]
            index = len_hex
        else:
            data_hex = hex_data[index:index+data_len]
            index += data_len
        
        print(f"[COROS] 数据长度: {data_len//2} 字节, 数据: {data_hex}")
        
        # 解析数据
        data = ""
        description = ""
        
        # 针对0x09类型（完整设备名称）进行专门处理
        if type_val == 0x09:
            try:
                # 转换为ASCII字符串
                data = bytes.fromhex(data_hex).decode('ascii').strip()
                description = f"{type_descriptions[type_val]}: {data}"
                device_name = data
                print(f"[COROS] 成功解析设备名称: {device_name}")
            except Exception as e:
                data = data_hex
                description = f"完整设备名称 (解析失败: {str(e)})"
                print(f"[COROS] 名称解析失败: {e}")
                
        elif type_val == 0x19:  # 外观类型
            # 反转字节顺序
            bytes_list = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
            reversed_bytes = bytes_list[::-1]
            uuid_hex = ''.join(reversed_bytes)
            data = f"0x{uuid_hex}"
            description = f"外观: {data}"
            
        else:  # 其他类型
            try:
                # 尝试解析为字符串
                str_data = bytes.fromhex(data_hex).decode('ascii').strip()
                data = str_data
                description = f"{type_descriptions.get(type_val, f'类型0x{type_val:02X}')}: {data}"
            except:
                data = data_hex
                description = f"{type_descriptions.get(type_val, f'类型0x{type_val:02X}')} (二进制数据)"
        
        # 添加到结果
        result.append((
            length, 
            f"0x{type_val:02X}", 
            type_descriptions.get(type_val, f"未知类型0x{type_val:02X}"), 
            data, 
            description
        ))
    
    return result, device_name

def test_name_parsing():
    """测试名称解析功能"""
    print("=" * 80)
    print("BLE设备名称解析测试")
    print("=" * 80)
    
    # 测试数据1: COROS数据
    test_data_1 = "0319C1001409434F524F532050414345203220414232453037"
    print(f"\n测试数据1: {test_data_1}")
    parsed_data_1, device_name_1 = parse_coros_data_enhanced(test_data_1)
    print(f"解析结果: {device_name_1}")
    
    # 测试数据2: 模拟标准BLE广播数据
    # 长度=12, 类型=0x09(完整名称), 数据="Test Device"
    test_name = "Test Device"
    test_name_hex = test_name.encode('ascii').hex()
    test_data_2 = f"0C09{test_name_hex}"
    print(f"\n测试数据2: {test_data_2}")
    print(f"预期名称: {test_name}")
    
    # 手动解析测试
    adv_bytes = bytes.fromhex(test_data_2)
    length = adv_bytes[0]  # 12
    ad_type = adv_bytes[1]  # 0x09
    name_data = adv_bytes[2:2+(length-1)]  # 去掉类型字节
    parsed_name = name_data.decode('ascii')
    
    print(f"手动解析: 长度={length}, 类型=0x{ad_type:02X}, 名称={parsed_name}")
    
    print("=" * 80)

# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口"""
    print("=" * 60)
    print("ESP32-C3 蓝牙设备扫描器")
    print("=" * 60)
    
    try:
        # 解析命令行参数
        import sys
        args = sys.argv[1:] if len(sys.argv) > 1 else []
        
        # 测试模式
        if len(args) > 0 and args[0] == "test":
            test_name_parsing()
            return
        
        # 解析模式
        if len(args) > 0 and args[0] == "parse":
            if len(args) > 1:
                hex_data = args[1]
                parse_coros_data_enhanced(hex_data)
            else:
                print("请提供要解析的十六进制数据")
                print("用法: python ble_scanner.py parse <hex_data>")
            return
        
        # 执行初始垃圾回收
        gc.collect()
        print(f"[内存] 初始可用内存: {gc.mem_free()} 字节")
        
        # 解析扫描参数
        scan_duration = 10000  # 默认10秒扫描时间
        debug_mode = False
        
        # 解析命令行参数
        for arg in args:
            if arg == "debug":
                debug_mode = True
            elif arg.isdigit():
                scan_duration = int(arg) * 1000  # 转换为毫秒
        
        print(f"[设置] 扫描时间: {scan_duration//1000} 秒")
        print(f"[设置] 调试模式: {'开启' if debug_mode else '关闭'}")
        
        # 创建交互式扫描器
        scanner = InteractiveBLEScanner()
        scanner.set_debug_mode(debug_mode)
        
        # 扫描并显示设备
        if scanner.scan_and_display(scan_duration):
            # 选择设备
            selected_device = scanner.select_device_interactive()
            
            if selected_device:
                print(f"\n[结果] 最终选择的设备:")
                print(f"  名称: {selected_device.get('name', 'Unknown')}")
                print(f"  地址: {selected_device.get('address', 'Unknown')}")
                print(f"  信号强度: {selected_device.get('rssi', -100)} dBm")
                
                # 尝试连接（可选）
                try:
                    connect_choice = input("\n是否尝试连接到此设备? (y/n): ").lower()
                    if connect_choice == 'y':
                        connect_to_selected_device(selected_device)
                except KeyboardInterrupt:
                    print("\n[用户] 取消连接")
            else:
                print("[结果] 未选择任何设备")
        else:
            print("[错误] 扫描失败")
            
    except KeyboardInterrupt:
        print("\n[用户] 程序被用户中断")
    except Exception as e:
        print(f"[错误] 程序运行出错: {e}")
    finally:
        # 执行最终垃圾回收
        gc.collect()
        print(f"[内存] 最终可用内存: {gc.mem_free()} 字节")
        print("\n[完成] 程序结束")


# =============================================================================
# 程序入口点
# =============================================================================

if __name__ == "__main__":
    # 只有主模式
    main()

# 执行垃圾回收
gc.collect()