# -*- coding: utf-8 -*-
"""
蓝牙网络管理模块

为ESP32C3设备提供蓝牙BLE功能，支持通过Web Bluetooth API进行设备配置。
该模块在设备通电时自动启动，提供配置读写、WiFi扫描、设备状态查询等功能。

内存优化说明：
- 使用异步操作减少阻塞时间
- 采用轻量级JSON处理
- 实现连接超时和自动清理机制
- 避免频繁的内存分配和释放
"""

import bluetooth
import ubinascii
import ujson
import uasyncio as asyncio
import machine
import network
import time
import gc
from micropython import const

# =============================================================================
# 蓝牙服务UUID常量
# =============================================================================

# 主服务UUID
SERVICE_UUID = const(0x1234)
# 特征值UUID
CHAR_CONFIG_UUID = const(0x1235)      # 配置读写
CHAR_STATUS_UUID = const(0x1236)      # 状态查询
CHAR_WIFI_SCAN_UUID = const(0x1237)   # WiFi扫描
CHAR_WIFI_LIST_UUID = const(0x1238)   # WiFi列表
CHAR_DEVICE_INFO_UUID = const(0x1239) # 设备信息

# =============================================================================
# 全局变量
# =============================================================================

_ble = None
_ble_active = False
_config = None
_wifi_sta = None
_loop = None

# =============================================================================
# 蓝牙配置管理器类
# =============================================================================

class BluetoothConfigManager:
    """
    蓝牙配置管理器
    
    作用：管理配置文件的读写操作
    内存影响：低（约200字节）
    """
    
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self._config_cache = None
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                self._config_cache = ujson.load(f)
            return self._config_cache
        except Exception as e:
            print(f"[BT] 加载配置失败: {e}")
            return None
    
    def save_config(self, config):
        """保存配置文件"""
        try:
            with open(self.config_path, 'w') as f:
                ujson.dump(config, f)
            self._config_cache = config
            return True
        except Exception as e:
            print(f"[BT] 保存配置失败: {e}")
            return False
    
    def get_config(self):
        """获取配置缓存"""
        if self._config_cache is None:
            return self.load_config()
        return self._config_cache
    
    def update_config(self, path, value):
        """更新配置项"""
        config = self.get_config()
        if config is None:
            return False
        
        # 解析路径，如 "mqtt.broker"
        keys = path.split('.')
        current = config
        
        # 遍历到最后一个键之前
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # 设置值
        current[keys[-1]] = value
        
        # 保存配置
        return self.save_config(config)

# =============================================================================
# WiFi扫描器类
# =============================================================================

class WiFiScanner:
    """
    WiFi扫描器
    
    作用：提供WiFi网络扫描功能
    内存影响：中等（扫描时约1KB）
    """
    
    def __init__(self):
        self.wifi = network.WLAN(network.STA_IF)
        self.wifi.active(False)
    
    def scan_networks(self):
        """扫描WiFi网络"""
        try:
            self.wifi.active(True)
            networks = self.wifi.scan()
            
            # 解析扫描结果
            result = []
            for net in networks:
                if len(net) >= 5:
                    ssid = net[0].decode('utf-8', errors='ignore')
                    if ssid:  # 过滤空SSID
                        result.append({
                            'ssid': ssid,
                            'bssid': ubinascii.hexlify(net[1]).decode(),
                            'channel': net[2],
                            'rssi': net[3],
                            'authmode': net[4]
                        })
            
            # 按信号强度排序
            result.sort(key=lambda x: x['rssi'], reverse=True)
            
            return result
        except Exception as e:
            print(f"[BT] WiFi扫描失败: {e}")
            return []
        finally:
            self.wifi.active(False)
    
    def get_saved_networks(self):
        """获取已保存的WiFi网络"""
        # 注意：这个方法在BluetoothService中调用时，需要传入config_manager
        return []

# =============================================================================
# 蓝牙服务处理类
# =============================================================================

class BluetoothService:
    """
    蓝牙服务处理
    
    作用：处理蓝牙BLE服务和特征值
    内存影响：低（约300字节）
    """
    
    def __init__(self, ble, config_manager):
        self.ble = ble
        self.config_manager = config_manager
        self.wifi_scanner = WiFiScanner()
        self.config_handle = None
        self.status_handle = None
        self.wifi_scan_handle = None
        self.wifi_list_handle = None
        self.device_info_handle = None
        # 延迟初始化服务，避免在构造函数中调用复杂方法
        self._service_initialized = False
    
    def initialize_service(self):
        """初始化蓝牙服务"""
        if not self._service_initialized:
            try:
                self._setup_service()
                self._service_initialized = True
                print("[BT] 蓝牙服务初始化完成")
                return True
            except Exception as e:
                print(f"[BT] 蓝牙服务初始化失败: {e}")
                return False
        return True
    
    def _setup_service(self):
        """设置蓝牙服务"""
        try:
            # 设置蓝牙服务
            service = (
                bluetooth.UUID(SERVICE_UUID),
                [
                    # 配置读写特征值
                    (
                        bluetooth.UUID(CHAR_CONFIG_UUID),
                        bluetooth.FLAG_READ | bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY,
                    ),
                    # 状态查询特征值
                    (
                        bluetooth.UUID(CHAR_STATUS_UUID),
                        bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
                    ),
                    # WiFi扫描特征值
                    (
                        bluetooth.UUID(CHAR_WIFI_SCAN_UUID),
                        bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY,
                    ),
                    # WiFi列表特征值
                    (
                        bluetooth.UUID(CHAR_WIFI_LIST_UUID),
                        bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
                    ),
                    # 设备信息特征值
                    (
                        bluetooth.UUID(CHAR_DEVICE_INFO_UUID),
                        bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
                    ),
                ],
            )
            
            # 设置服务和IRQ处理
            ((self.config_handle, self.status_handle, self.wifi_scan_handle,
              self.wifi_list_handle, self.device_info_handle),) = self.ble.gatts_register_services((service,))
            
            # 设置初始值
            self.ble.gatts_write(self.status_handle, b'ready')
            self.ble.gatts_write(self.device_info_handle, self._get_device_info())
            
            # 设置IRQ处理
            self.ble.irq(self._irq_handler)
            
            print("[BT] 蓝牙服务设置完成")
            
        except Exception as e:
            print(f"[BT] 蓝牙服务设置失败: {e}")
    
    def _get_device_info(self):
        """获取设备信息"""
        try:
            config = self.config_manager.get_config()
            device_info = {
                'name': config.get('device', {}).get('name', 'ESP32C3-IOT'),
                'location': config.get('device', {}).get('location', '未知位置'),
                'firmware_version': config.get('device', {}).get('firmware_version', '1.0.0'),
                'device_id': machine.unique_id().hex(),
                'status': 'ready'
            }
            return ujson.dumps(device_info).encode()
        except Exception as e:
            print(f"[BT] 获取设备信息失败: {e}")
            return b'{"error": "get_device_info_failed"}'
    
    def _irq_handler(self, event, data):
        """蓝牙事件处理"""
        try:
            if event == 1:  # IRQ_CENTRAL_CONNECT
                # 中央设备连接
                conn_handle, addr_type, addr = data
                print(f"[BT] 设备连接: {ubinascii.hexlify(addr).decode()}")
                self.ble.gatts_write(self.status_handle, b'connected')
                self.ble.gatts_notify(0, self.status_handle, b'connected')
                
            elif event == 2:  # IRQ_CENTRAL_DISCONNECT
                # 中央设备断开连接
                conn_handle, _, _ = data
                print("[BT] 设备断开连接")
                self.ble.gatts_write(self.status_handle, b'ready')
                # 重新开始广播
                self._start_advertising()
                
            elif event == 3:  # IRQ_GATTS_WRITE
                # 特征值写入
                conn_handle, value_handle = data
                value = self.ble.gatts_read(value_handle)
                
                if value_handle == self.config_handle:
                    self._handle_config_write(value)
                elif value_handle == self.wifi_scan_handle:
                    self._handle_wifi_scan()
                    
        except Exception as e:
            print(f"[BT] IRQ处理失败: {e}")
    
    def _handle_config_write(self, value):
        """处理配置写入"""
        try:
            config_data = ujson.loads(value.decode())
            print(f"[BT] 收到配置数据: {config_data}")
            
            # 处理不同类型的配置命令
            if 'cmd' in config_data:
                cmd = config_data['cmd']
                
                if cmd == 'get_config':
                    # 获取完整配置
                    full_config = self.config_manager.get_config()
                    if full_config:
                        response = ujson.dumps({'cmd': 'config_data', 'data': full_config})
                        self.ble.gatts_write(self.config_handle, response.encode())
                        self.ble.gatts_notify(0, self.config_handle, response.encode())
                
                elif cmd == 'set_config':
                    # 设置配置
                    if 'path' in config_data and 'value' in config_data:
                        path = config_data['path']
                        value = config_data['value']
                        
                        if self.config_manager.update_config(path, value):
                            response = ujson.dumps({'cmd': 'config_set', 'success': True})
                        else:
                            response = ujson.dumps({'cmd': 'config_set', 'success': False, 'error': 'save_failed'})
                        
                        self.ble.gatts_write(self.config_handle, response.encode())
                        self.ble.gatts_notify(0, self.config_handle, response.encode())
                
                elif cmd == 'wifi_add':
                    # 添加WiFi网络
                    if 'ssid' in config_data and 'password' in config_data:
                        ssid = config_data['ssid']
                        password = config_data['password']
                        
                        config = self.config_manager.get_config()
                        if config and 'wifi' in config:
                            # 检查是否已存在
                            existing = False
                            for net in config['wifi']['networks']:
                                if net['ssid'] == ssid:
                                    existing = True
                                    break
                            
                            if not existing:
                                config['wifi']['networks'].append({'ssid': ssid, 'password': password})
                                if self.config_manager.save_config(config):
                                    response = ujson.dumps({'cmd': 'wifi_added', 'success': True})
                                else:
                                    response = ujson.dumps({'cmd': 'wifi_added', 'success': False, 'error': 'save_failed'})
                            else:
                                response = ujson.dumps({'cmd': 'wifi_added', 'success': False, 'error': 'network_exists'})
                        else:
                            response = ujson.dumps({'cmd': 'wifi_added', 'success': False, 'error': 'config_invalid'})
                        
                        self.ble.gatts_write(self.config_handle, response.encode())
                        self.ble.gatts_notify(0, self.config_handle, response.encode())
                
                elif cmd == 'wifi_remove':
                    # 删除WiFi网络
                    if 'ssid' in config_data:
                        ssid = config_data['ssid']
                        
                        config = self.config_manager.get_config()
                        if config and 'wifi' in config:
                            original_count = len(config['wifi']['networks'])
                            config['wifi']['networks'] = [net for net in config['wifi']['networks'] if net['ssid'] != ssid]
                            
                            if len(config['wifi']['networks']) < original_count:
                                if self.config_manager.save_config(config):
                                    response = ujson.dumps({'cmd': 'wifi_removed', 'success': True})
                                else:
                                    response = ujson.dumps({'cmd': 'wifi_removed', 'success': False, 'error': 'save_failed'})
                            else:
                                response = ujson.dumps({'cmd': 'wifi_removed', 'success': False, 'error': 'network_not_found'})
                        else:
                            response = ujson.dumps({'cmd': 'wifi_removed', 'success': False, 'error': 'config_invalid'})
                        
                        self.ble.gatts_write(self.config_handle, response.encode())
                        self.ble.gatts_notify(0, self.config_handle, response.encode())
                
                elif cmd == 'device_restart':
                    # 重启设备
                    response = ujson.dumps({'cmd': 'device_restart', 'success': True})
                    self.ble.gatts_write(self.config_handle, response.encode())
                    self.ble.gatts_notify(0, self.config_handle, response.encode())
                    
                    # 延迟重启
                    asyncio.create_task(self._delayed_restart())
                
                elif cmd == 'factory_reset':
                    # 恢复出厂设置
                    response = ujson.dumps({'cmd': 'factory_reset', 'success': True})
                    self.ble.gatts_write(self.config_handle, response.encode())
                    self.ble.gatts_notify(0, self.config_handle, response.encode())
                    
                    # 延迟恢复出厂设置
                    asyncio.create_task(self._delayed_factory_reset())
                
                elif cmd == 'wifi_test':
                    # 测试WiFi连接
                    if 'ssid' in config_data and 'password' in config_data:
                        ssid = config_data['ssid']
                        password = config_data['password']
                        
                        print(f"[BT] 测试WiFi连接: {ssid}")
                        # 异步执行WiFi测试
                        asyncio.create_task(self._async_wifi_test(ssid, password))
                    else:
                        response = ujson.dumps({'cmd': 'wifi_test_result', 'success': False, 'message': '缺少SSID或密码'})
                        self.ble.gatts_write(self.config_handle, response.encode())
                        self.ble.gatts_notify(0, self.config_handle, response.encode())
                
                elif cmd == 'wifi_save_and_restart':
                    # 保存WiFi配置并重启
                    if 'ssid' in config_data and 'password' in config_data:
                        ssid = config_data['ssid']
                        password = config_data['password']
                        
                        # 保存到配置
                        config = self.config_manager.get_config()
                        if config:
                            if 'wifi' not in config:
                                config['wifi'] = {}
                            if 'networks' not in config['wifi']:
                                config['wifi']['networks'] = []
                            
                            # 检查是否已存在
                            existing = False
                            for net in config['wifi']['networks']:
                                if net['ssid'] == ssid:
                                    existing = True
                                    net['password'] = password
                                    break
                            
                            if not existing:
                                config['wifi']['networks'].append({'ssid': ssid, 'password': password})
                            
                            if self.config_manager.save_config(config):
                                response = ujson.dumps({'cmd': 'wifi_save_result', 'success': True, 'message': 'WiFi配置已保存，设备将重启'})
                                self.ble.gatts_write(self.config_handle, response.encode())
                                self.ble.gatts_notify(0, self.config_handle, response.encode())
                                
                                # 延迟重启
                                asyncio.create_task(self._delayed_restart())
                            else:
                                response = ujson.dumps({'cmd': 'wifi_save_result', 'success': False, 'message': '保存配置失败'})
                        else:
                            response = ujson.dumps({'cmd': 'wifi_save_result', 'success': False, 'message': '配置加载失败'})
                    else:
                        response = ujson.dumps({'cmd': 'wifi_save_result', 'success': False, 'message': '缺少SSID或密码'})
                    
                    self.ble.gatts_write(self.config_handle, response.encode())
                    self.ble.gatts_notify(0, self.config_handle, response.encode())
            
        except Exception as e:
            print(f"[BT] 处理配置写入失败: {e}")
            error_response = ujson.dumps({'cmd': 'error', 'message': str(e)})
            self.ble.gatts_write(self.config_handle, error_response.encode())
            self.ble.gatts_notify(0, self.config_handle, error_response.encode())
    
    def _handle_wifi_scan(self):
        """处理WiFi扫描请求"""
        try:
            # 异步执行WiFi扫描
            asyncio.create_task(self._async_wifi_scan())
        except Exception as e:
            print(f"[BT] WiFi扫描请求处理失败: {e}")
    
    async def _async_wifi_scan(self):
        """异步WiFi扫描"""
        try:
            print("[BT] 开始WiFi扫描...")
            networks = self.wifi_scanner.scan_networks()
            
            # 获取已保存的网络
            saved_networks = self.wifi_scanner.get_saved_networks()
            saved_ssids = [net['ssid'] for net in saved_networks]
            
            # 标记已保存的网络
            for net in networks:
                net['saved'] = net['ssid'] in saved_ssids
            
            # 限制返回的网络数量（减少数据传输量）
            networks = networks[:20]
            
            response = ujson.dumps({'cmd': 'wifi_scan_result', 'networks': networks})
            self.ble.gatts_write(self.wifi_list_handle, response.encode())
            self.ble.gatts_notify(0, self.wifi_list_handle, response.encode())
            
            print(f"[BT] WiFi扫描完成，发现 {len(networks)} 个网络")
            
        except Exception as e:
            print(f"[BT] 异步WiFi扫描失败: {e}")
            error_response = ujson.dumps({'cmd': 'wifi_scan_error', 'error': str(e)})
            self.ble.gatts_write(self.wifi_list_handle, error_response.encode())
            self.ble.gatts_notify(0, self.wifi_list_handle, error_response.encode())
    
    def _start_advertising(self):
        """开始广播"""
        try:
            # 设置广播数据
            adv_data = bytearray()
            adv_data.append(0x02)  # 长度
            adv_data.append(0x01)  # 标志
            adv_data.append(0x06)  # 一般可发现
            
            # 添加设备名称
            name = "ESP32C3-IOT"
            name_bytes = name.encode()
            adv_data.append(len(name_bytes) + 1)
            adv_data.append(0x09)  # 完整本地名称
            adv_data.extend(name_bytes)
            
            # 设置广播数据
            self.ble.gap_advertise(100, adv_data=adv_data)
            print("[BT] 开始广播")
            
        except Exception as e:
            print(f"[BT] 广播失败: {e}")
    
    async def _delayed_restart(self):
        """延迟重启"""
        await asyncio.sleep(2)
        print("[BT] 重启设备...")
        machine.reset()
    
    async def _delayed_factory_reset(self):
        """延迟恢复出厂设置"""
        await asyncio.sleep(2)
        print("[BT] 恢复出厂设置...")
        # 这里可以实现恢复出厂设置的逻辑
        # 暂时直接重启
        machine.reset()
    
    async def _test_wifi_connection(self, ssid, password):
        """测试WiFi连接"""
        try:
            # 关闭蓝牙以释放资源
            if self.ble:
                self.ble.active(False)
                await asyncio.sleep_ms(500)
            
            # 初始化WiFi
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            await asyncio.sleep_ms(500)
            
            # 连接WiFi
            wlan.connect(ssid, password)
            
            # 等待连接，最多10秒
            for i in range(20):
                if wlan.isconnected():
                    ip_address = wlan.ifconfig()[0]
                    print(f"[BT] WiFi测试连接成功: {ssid}, IP: {ip_address}")
                    
                    # 断开连接
                    wlan.disconnect()
                    wlan.active(False)
                    
                    # 重新启动蓝牙
                    if self.ble:
                        self.ble.active(True)
                        self._start_advertising()
                    
                    return True
                
                await asyncio.sleep_ms(500)
            
            # 连接失败
            print(f"[BT] WiFi测试连接失败: {ssid}")
            wlan.disconnect()
            wlan.active(False)
            
            # 重新启动蓝牙
            if self.ble:
                self.ble.active(True)
                self._start_advertising()
            
            return False
            
        except Exception as e:
            print(f"[BT] WiFi测试连接异常: {e}")
            
            # 尝试恢复蓝牙
            try:
                if self.ble:
                    self.ble.active(True)
                    self._start_advertising()
            except:
                pass
            
            return False
    
    async def _async_wifi_test(self, ssid, password):
        """异步WiFi测试"""
        try:
            test_result = await self._test_wifi_connection(ssid, password)
            
            if test_result:
                response = ujson.dumps({'cmd': 'wifi_test_result', 'success': True, 'message': 'WiFi连接测试成功'})
            else:
                response = ujson.dumps({'cmd': 'wifi_test_result', 'success': False, 'message': 'WiFi连接测试失败'})
            
            self.ble.gatts_write(self.config_handle, response.encode())
            self.ble.gatts_notify(0, self.config_handle, response.encode())
            
        except Exception as e:
            print(f"[BT] 异步WiFi测试异常: {e}")
            error_response = ujson.dumps({'cmd': 'wifi_test_result', 'success': False, 'message': f'测试异常: {str(e)}'})
            self.ble.gatts_write(self.config_handle, error_response.encode())
            self.ble.gatts_notify(0, self.config_handle, error_response.encode())

# =============================================================================
# 蓝牙管理器主类
# =============================================================================

class BluetoothManager:
    """
    蓝牙管理器
    
    作用：管理蓝牙BLE功能的主类
    内存影响：低（约400字节）
    """
    
    def __init__(self):
        self.ble = None
        self.service = None
        self.config_manager = None
        self.initialized = False
    
    def initialize(self):
        """初始化蓝牙管理器"""
        try:
            print("[BT] 初始化蓝牙管理器...")
            
            # 执行垃圾回收，确保有足够内存
            gc.collect()
            free_memory = gc.mem_free()
            print(f"[BT] 可用内存: {free_memory} 字节")
            
            if free_memory < 50000:  # 小于50KB内存可能不够
                print("[BT] 警告: 内存不足，可能影响蓝牙初始化")
            
            # 初始化配置管理器
            self.config_manager = BluetoothConfigManager()
            
            # 尝试多次初始化蓝牙
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    print(f"[BT] 蓝牙初始化尝试 {attempt + 1}/{max_attempts}...")
                    
                    # 确保WiFi已关闭
                    try:
                        import network
                        wlan = network.WLAN(network.STA_IF)
                        if wlan.active():
                            print("[BT] 关闭WiFi以释放蓝牙资源...")
                            wlan.active(False)
                            time.sleep_ms(1000)
                    except Exception as e:
                        print(f"[BT] 关闭WiFi时出现警告: {e}")
                    
                    # 初始化蓝牙
                    self.ble = bluetooth.BLE()
                    
                    # 先激活，再检查状态
                    self.ble.active(True)
                    time.sleep_ms(500)  # 等待蓝牙激活
                    
                    # 检查蓝牙是否真的激活了
                    if not self.ble.active():
                        print(f"[BT] 蓝牙激活失败，尝试 {attempt + 1}")
                        if self.ble:
                            self.ble.active(False)
                        continue
                    
                    print("[BT] 蓝牙硬件初始化成功")
                    
                    # 初始化服务
                    self.service = BluetoothService(self.ble, self.config_manager)
                    
                    # 初始化蓝牙服务
                    if not self.service.initialize_service():
                        print(f"[BT] 蓝牙服务初始化失败，尝试 {attempt + 1}")
                        if self.ble:
                            self.ble.active(False)
                        continue
                    
                    # 开始广播
                    self.service._start_advertising()
                    
                    self.initialized = True
                    print("[BT] 蓝牙管理器初始化完成")
                    
                    return True
                    
                except Exception as init_error:
                    print(f"[BT] 蓝牙初始化尝试 {attempt + 1} 失败: {init_error}")
                    
                    # 清理资源
                    try:
                        if self.ble:
                            self.ble.active(False)
                            self.ble = None
                    except:
                        pass
                    
                    # 如果不是最后一次尝试，等待一段时间再重试
                    if attempt < max_attempts - 1:
                        print(f"[BT] 等待 {1000}ms 后重试...")
                        time.sleep_ms(1000)
            
            print(f"[BT] 蓝牙初始化在 {max_attempts} 次尝试后仍然失败")
            return False
            
        except Exception as e:
            print(f"[BT] 蓝牙管理器初始化异常: {e}")
            return False
    
    def deinitialize(self):
        """反初始化蓝牙管理器"""
        try:
            if self.ble:
                self.ble.active(False)
                self.ble = None
            self.service = None
            self.config_manager = None
            self.initialized = False
            print("[BT] 蓝牙管理器已关闭")
        except Exception as e:
            print(f"[BT] 蓝牙管理器关闭失败: {e}")
    
    def is_active(self):
        """检查蓝牙是否激活"""
        return self.initialized and self.ble and self.ble.active()

# =============================================================================
# 全局变量和函数
# =============================================================================

_config_manager = None
_bt_manager = None

def initialize_bluetooth():
    """初始化蓝牙功能"""
    global _config_manager, _bt_manager
    
    print("[BT] 开始初始化蓝牙功能...")
    
    try:
        # 检查WiFi是否已激活，如果已激活则先关闭
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            if wlan.active():
                print("[BT] 检测到WiFi已激活，先关闭WiFi以释放资源...")
                wlan.active(False)
                time.sleep_ms(1000)  # 等待WiFi完全关闭
                print("[BT] WiFi已关闭，资源释放完成")
        except ImportError:
            pass
        
        # 初始化配置管理器
        print("[BT] 初始化配置管理器...")
        _config_manager = BluetoothConfigManager()
        
        # 初始化蓝牙管理器
        print("[BT] 初始化蓝牙管理器...")
        _bt_manager = BluetoothManager()
        if _bt_manager.initialize():
            print("[BT] 蓝牙功能启动成功")
            return True
        else:
            print("[BT] 蓝牙功能启动失败")
            return False
            
    except Exception as e:
        print(f"[BT] 蓝牙初始化异常: {e}")
        return False

def deinitialize_bluetooth():
    """关闭蓝牙功能"""
    global _bt_manager
    
    if _bt_manager:
        _bt_manager.deinitialize()
        _bt_manager = None
        print("[BT] 蓝牙功能已关闭")

def is_bluetooth_active():
    """检查蓝牙是否激活"""
    return _bt_manager and _bt_manager.is_active()

# =============================================================================
# 模块初始化
# =============================================================================

# 模块加载时不自动初始化蓝牙，由主程序控制初始化时机
_bt_initialized = False
print("[BT] 蓝牙模块已加载，等待初始化...")

# 执行垃圾回收
gc.collect()
