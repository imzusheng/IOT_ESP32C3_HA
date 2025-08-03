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
                    # 限制设备数量
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
                    try:
                        name_data = adv_data[pos + 2:pos + field_len + 1]
                        device_info['name'] = name_data.decode('utf-8', errors='ignore')
                        
                        # 调试模式：显示解析过程
                        if self.debug_mode:
                            print(f"[DEBUG] 解析设备名称: {device_info['name']}")
                            print(f"[DEBUG] 原始数据: {ubinascii.hexlify(name_data).decode()}")
                            
                    except Exception as e:
                        device_info['name'] = ''
                        if self.debug_mode:
                            print(f"[DEBUG] 名称解析失败: {e}")
                
                # 临时启用调试模式，显示所有字段解析过程
                if self.debug_mode:
                    print(f"[DEBUG] 字段 - 长度: {field_len}, 类型: 0x{field_type:02X} ({self._get_field_type_name(field_type)})")
                    field_data = adv_data[pos + 2:pos + field_len + 1]
                    print(f"[DEBUG] 数据: {ubinascii.hexlify(field_data).decode()}")
                    
                    # 尝试将字段数据作为名称解析
                    if field_type not in [GAP_TYPE_SHORT_LOCAL_NAME, GAP_TYPE_COMPLETE_LOCAL_NAME]:
                        try:
                            potential_name = field_data.decode('utf-8', errors='ignore')
                            if potential_name and potential_name.isprintable() and len(potential_name) > 2:
                                print(f"[DEBUG] 可能的名称: {potential_name}")
                                if not device_info['name']:  # 如果还没有名称，使用这个
                                    device_info['name'] = potential_name
                        except:
                            pass
                
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
            
            # 如果没有找到名称，尝试替代方法
            if not device_info['name']:
                alternative_name = self.try_alternative_name_parsing(adv_data)
                if alternative_name:
                    device_info['name'] = alternative_name
                    if self.debug_mode:
                        print(f"[DEBUG] 使用替代方法解析到名称: {alternative_name}")
            
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
# 优化的设备名称解析器
# =============================================================================

class DeviceNameParser:
    """
    设备名称解析器
    
    作用：高效解析蓝牙设备广播数据中的设备名称
    内存影响：极低（约200字节）
    """
    
    def __init__(self):
        # 预分配缓冲区
        self._name_buffer = bytearray(32)
        
    def parse_device_name(self, adv_data):
        """
        从广播数据中解析设备名称
        
        参数:
            adv_data: 广播数据字节数组
            
        返回:
            设备名称字符串
        """
        try:
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
                
                # 检查是否为名称字段
                if field_type == GAP_TYPE_COMPLETE_LOCAL_NAME or field_type == GAP_TYPE_SHORT_LOCAL_NAME:
                    # 提取名称数据
                    name_data = adv_data[pos + 2:pos + field_len + 1]
                    
                    # 复制到缓冲区
                    if len(name_data) > 0:
                        buffer_len = min(len(name_data), len(self._name_buffer))
                        for i in range(buffer_len):
                            self._name_buffer[i] = name_data[i]
                        
                        # 转换为字符串
                        try:
                            return bytes(self._name_buffer[:buffer_len]).decode('utf-8', errors='ignore')
                        except:
                            return ''
                
                # 移动到下一个字段
                pos += field_len + 1
            
            return ''
            
        except Exception as e:
            print(f"[BLE] 名称解析失败: {e}")
            return ''
    
    def parse_device_name_optimized(self, adv_data):
        """
        优化的设备名称解析算法
        
        基于提供的调试数据示例:
        0319C1001409434F524F532050414345203220414232453037
        
        解析结构:
        03 19 C1 00        - 长度3，类型0x19，UUID 0x00C1
        14 09 434F524F532050414345203220414232453037 - 长度20，类型0x09(完整名称)，数据"COROS PACE 2 AB2E07"
        
        参数:
            adv_data: 广播数据字节数组
            
        返回:
            设备名称字符串
        """
        try:
            # 使用标准解析算法确保兼容性
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
                
                # 检查是否为名称字段
                if field_type == GAP_TYPE_COMPLETE_LOCAL_NAME or field_type == GAP_TYPE_SHORT_LOCAL_NAME:
                    # 提取名称数据
                    name_data = adv_data[pos + 2:pos + field_len + 1]
                    
                    # 复制到缓冲区
                    if len(name_data) > 0:
                        buffer_len = min(len(name_data), len(self._name_buffer))
                        for i in range(buffer_len):
                            self._name_buffer[i] = name_data[i]
                        
                        # 转换为字符串
                        try:
                            decoded_name = bytes(self._name_buffer[:buffer_len]).decode('utf-8', errors='ignore')
                            
                            # 调试信息：显示解析过程
                            print(f"[DEBUG] 名称字段 - 长度: {field_len}, 类型: 0x{field_type:02X}")
                            print(f"[DEBUG] 原始数据: {ubinascii.hexlify(name_data).decode()}")
                            print(f"[DEBUG] 解析结果: {decoded_name}")
                            
                            return decoded_name
                        except Exception as e:
                            print(f"[DEBUG] UTF-8解码失败: {e}")
                            # 尝试其他编码
                            try:
                                return bytes(self._name_buffer[:buffer_len]).decode('latin-1', errors='ignore')
                            except:
                                return ''
                
                # 移动到下一个字段
                pos += field_len + 1
            
            return ''
            
        except Exception as e:
            print(f"[BLE] 优化名称解析失败: {e}")
            return ''
    
    def parse_adv_packet_hex(self, hex_data):
        """
        从十六进制字符串解析广播数据
        
        参数:
            hex_data: 十六进制格式的广播数据字符串
            
        返回:
            设备名称字符串
        """
        try:
            # 转换十六进制字符串为字节数组
            adv_data = bytearray.fromhex(hex_data)
            return self.parse_device_name_optimized(adv_data)
        except Exception as e:
            print(f"[BLE] 十六进制解析失败: {e}")
            return ''

# =============================================================================
# 全局函数
# =============================================================================

def parse_device_name_from_hex(hex_data):
    """
    从十六进制字符串解析设备名称（全局函数）
    
    参数:
        hex_data: 十六进制格式的广播数据字符串
        
    返回:
        设备名称字符串
    """
    parser = DeviceNameParser()
    return parser.parse_adv_packet_hex(hex_data)

# =============================================================================
# 测试函数
# =============================================================================

def test_name_parsing():
    """测试设备名称解析功能"""
    print("[BLE] 测试设备名称解析...")
    
    parser = DeviceNameParser()
    
    # 测试数据
    test_data = "0319C1001409434F524F532050414345203220414232453037"
    
    # 解析名称
    device_name = parser.parse_adv_packet_hex(test_data)
    print(f"[BLE] 解析结果: {device_name}")
    
    # 预期结果: "COROS PACE 2 AB2E07"
    expected = "COROS PACE 2 AB2E07"
    if device_name == expected:
        print("[BLE] 测试通过!")
        return True
    else:
        print(f"[BLE] 测试失败! 预期: {expected}")
        return False

# =============================================================================
# 模块初始化
# =============================================================================

# 创建全局实例
_ble_scanner = None
_name_parser = None

def get_ble_scanner():
    """获取蓝牙扫描器实例"""
    global _ble_scanner
    if _ble_scanner is None:
        _ble_scanner = BLEScanner()
    return _ble_scanner

def get_name_parser():
    """获取名称解析器实例"""
    global _name_parser
    if _name_parser is None:
        _name_parser = DeviceNameParser()
    return _name_parser

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
        """显示设备表格（增强版）"""
        print("\n" + "="*80)
        print("蓝牙设备扫描结果 (按信号强度排序)")
        print("="*80)
        print(f"{'序号':<4} {'信号':<6} {'地址':<12} {'名称':<20} {'类型':<8} {'服务':<15}")
        print("-" * 80)
        
        for i, device in enumerate(devices):
            index = i + 1
            rssi = device.get('rssi', -100)
            address = device.get('address', 'Unknown')
            name = device.get('name', 'Unknown')
            addr_type = device.get('address_type', 0)
            services = device.get('services', [])
            
            # 截断过长的名称
            if len(name) > 18:
                name = name[:15] + "..."
            
            # 地址类型显示
            addr_type_str = "Public" if addr_type == 0 else "Random"
            
            # 服务数量显示
            services_str = f"{len(services)}个" if services else "无"
            
            print(f"{index:<4} {rssi:<6} {address:<12} {name:<20} {addr_type_str:<8} {services_str:<15}")
        
        print("="*80)
        print(f"共发现 {len(devices)} 个设备")
        print()
    
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
    
    def try_alternative_name_parsing(self, adv_data):
        """尝试多种方法解析设备名称"""
        try:
            # 方法1：扫描整个数据包寻找可能的名称
            for i in range(len(adv_data) - 2):
                # 寻找可能的ASCII字符序列
                if adv_data[i] >= 0x20 and adv_data[i] <= 0x7E:  # 可打印ASCII范围
                    # 尝试提取连续的可打印字符
                    name_parts = []
                    j = i
                    while j < len(adv_data) and adv_data[j] >= 0x20 and adv_data[j] <= 0x7E and len(name_parts) < 20:
                        name_parts.append(chr(adv_data[j]))
                        j += 1
                    
                    if len(name_parts) >= 3:  # 至少3个字符
                        potential_name = ''.join(name_parts)
                        # 过滤掉一些无意义的组合
                        if not all(c in '0123456789ABCDEF' for c in potential_name):
                            return potential_name
        except:
            pass
        
        return None
    
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

# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口"""
    print("=" * 60)
    print("ESP32-C3 蓝牙设备扫描器")
    print("=" * 60)
    
    try:
        # 执行初始垃圾回收
        gc.collect()
        print(f"[内存] 初始可用内存: {gc.mem_free()} 字节")
        
        # 检查系统参数
        import sys
        scan_duration = 8000  # 减少默认扫描时间到8秒
        debug_mode = False
        
        # 简单的命令行参数处理
        if len(sys.argv) > 1:
            try:
                if sys.argv[1] == "debug":
                    debug_mode = True
                    print("[设置] 调试模式: 开启")
                    if len(sys.argv) > 2:
                        scan_duration = int(sys.argv[2]) * 1000
                else:
                    scan_duration = int(sys.argv[1]) * 1000
                
                # 限制最大扫描时间
                if scan_duration > 15000:
                    scan_duration = 15000
                print(f"[设置] 扫描时间: {scan_duration//1000} 秒")
            except ValueError:
                print(f"[警告] 无效的扫描时间参数，使用默认值: {scan_duration//1000} 秒")
        
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

def test_hex_parsing():
    """测试十六进制数据解析（增强版）"""
    print("=" * 80)
    print("测试设备广播数据解析功能")
    print("=" * 80)
    
    # 测试数据
    test_cases = [
        "0319C1001409434F524F532050414345203220414232453037",
        "020A00030219C1001409434F524F532050414345203220414232453037",
        "090948454C4C4F20574F524C44",  # HELLO WORLD
        "02010603030218140AFF580A0C11070A18",  # 带有服务UUID的复杂数据
        "02010603030218140AFF580A0C11070A1809095465737420446576696365",  # 带有名称的复杂数据
    ]
    
    parser = DeviceNameParser()
    
    for i, test_data in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}:")
        print(f"输入数据: {test_data}")
        print("-" * 60)
        
        # 解析名称
        result = parser.parse_adv_packet_hex(test_data)
        print(f"解析结果: {result}")
        
        # 显示完整解析
        print("\n完整解析:")
        interactive_scanner = InteractiveBLEScanner()
        interactive_scanner._parse_and_display_adv_data(test_data)
        
        if result:
            print(f"✓ 解析成功")
        else:
            print(f"✗ 解析失败")
        
        print("=" * 80)

def scan_simple():
    """简单扫描模式（增强版）"""
    print("=" * 80)
    print("简单蓝牙扫描模式 - 增强版")
    print("=" * 80)
    
    scanner = BLEScanner()
    scanner.debug_mode = True  # 简单模式默认开启调试
    
    if not scanner.initialize():
        print("[错误] 蓝牙初始化失败")
        return
    
    try:
        # 开始扫描
        if not scanner.start_scan(5000):
            print("[错误] 扫描启动失败")
            return
        
        print("[扫描] 正在扫描蓝牙设备...")
        
        # 等待扫描完成
        import time
        start_time = time.ticks_ms()
        while scanner.scanning:
            if time.ticks_diff(time.ticks_ms(), start_time) > 7000:
                print("[超时] 扫描超时")
                break
            time.sleep_ms(100)
        
        # 获取结果
        devices = scanner.get_scan_results_sorted_by_rssi()
        
        if devices:
            print(f"\n[结果] 发现 {len(devices)} 个设备:")
            print("-" * 80)
            print(f"{'序号':<4} {'信号':<6} {'地址':<12} {'名称':<20} {'类型':<8} {'服务':<10}")
            print("-" * 80)
            
            for i, device in enumerate(devices, 1):
                name = device.get('name', 'Unknown')
                address = device.get('address', 'Unknown')
                rssi = device.get('rssi', -100)
                addr_type = device.get('address_type', 0)
                services = device.get('services', [])
                
                # 截断过长的名称
                if len(name) > 18:
                    name = name[:15] + "..."
                
                # 地址类型显示
                addr_type_str = "Public" if addr_type == 0 else "Random"
                
                # 服务数量显示
                services_str = f"{len(services)}个" if services else "无"
                
                print(f"{i:<4} {rssi:<6} {address:<12} {name:<20} {addr_type_str:<8} {services_str:<10}")
            
            print("-" * 80)
            
            # 显示第一个设备的详细信息作为示例
            if devices:
                print("\n[示例] 第一个设备的详细信息:")
                interactive_scanner = InteractiveBLEScanner()
                interactive_scanner._display_device_details(devices[0])
                
        else:
            print("[结果] 未发现任何设备")
            
    finally:
        scanner.deinitialize()

# =============================================================================
# 程序入口点
# =============================================================================

if __name__ == "__main__":
    # 检查运行模式
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 测试模式
        test_hex_parsing()
    elif len(sys.argv) > 1 and sys.argv[1] == "simple":
        # 简单扫描模式
        scan_simple()
    elif len(sys.argv) > 1 and sys.argv[1] == "parse":
        # 解析模式 - 解析指定的十六进制数据
        if len(sys.argv) > 2:
            display_adv_data_analysis(sys.argv[2])
        else:
            print("用法: python ble_scanner.py parse <十六进制数据>")
            print("示例: python ble_scanner.py parse 0319C1001409434F524F532050414345203220414232453037")
    else:
        # 交互模式
        main()

# 执行垃圾回收
gc.collect()