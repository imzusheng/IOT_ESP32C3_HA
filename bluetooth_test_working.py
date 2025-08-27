"""
ESP32-C3 蓝牙模块测试 (极简版)
专注于最基础的连接功能
"""

import bluetooth
import time
import uasyncio as asyncio
from micropython import const

# 蓝牙常量
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

class ESP32C3BluetoothWorking:
    """ESP32-C3蓝牙测试类 (极简版)"""
    
    def __init__(self, name="ESP32-C3", use_hid=True):
        self.name = name
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        # 尝试设置 GAP 名称, 某些端口可能不支持
        try:
            self.ble.config(gap_name=self.name)
        except Exception:
            pass
        self.ble.irq(self._irq_handler)
        
        self._connections = set()
        self._device_info = {}
        self._is_advertising = False
        self._char_handle = None
        self._use_hid = use_hid
        self._hid_handles = {}
        
        # 初始化服务
        try:
            if self._use_hid:
                self._init_hid_service()
            else:
                self._init_service_working()
        except Exception as e:
            print(f"HID 初始化失败, 回退到基础服务: {e}")
            self._init_service_working()
    
    def _extract_first_int_handle(self, obj):
        """从 gatts_register_services 返回结构中提取第一个整型句柄"""
        if isinstance(obj, int):
            return obj
        if isinstance(obj, (list, tuple)):
            for item in obj:
                h = self._extract_first_int_handle(item)
                if isinstance(h, int):
                    return h
        return None
        
    def _init_service_working(self):
        """极简版的服务初始化"""
        try:
            print("尝试初始化蓝牙服务...")
            
            # 先测试基本的蓝牙功能
            print(f"蓝牙激活状态: {self.ble.active()}")
            
            # 定义最简单的标准服务和特征 (电池服务/电量特征)
            service_uuid = bluetooth.UUID(0x180F)  # 电池服务
            char_uuid = bluetooth.UUID(0x2A19)    # 电池电量特征值
            char_flags = bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY
            
            services = (
                (
                    service_uuid,
                    (
                        (char_uuid, char_flags),
                    ),
                ),
            )
            
            # 注册服务
            handles = self.ble.gatts_register_services(services)
            print(f"服务注册返回: {handles} (类型: {type(handles)})")
            
            # 提取特征值句柄
            ch = self._extract_first_int_handle(handles)
            if isinstance(ch, int):
                self._char_handle = ch
                print(f"特征值句柄: {self._char_handle}")
                try:
                    self.ble.gatts_write(self._char_handle, bytes([100]))
                    print("初始电量写入成功: 100%")
                except Exception as e:
                    print(f"写入初始值失败: {e}")
            else:
                print("未能解析到特征值句柄, 使用备用值 2")
                self._char_handle = 2
            
            # 开始广播
            self._start_advertising_working()
            
        except Exception as e:
            print(f"服务初始化失败: {e}")
            print("尝试最简单的广播...")
            # 设置默认值并直接开始广播
            self._char_handle = 2
            self._start_advertising_working()
    
    def _build_adv_payload(self, name: str, include_hid=False) -> bytes:
        adv = bytearray(b"\x02\x01\x06")  # Flags: LE General Discoverable, BR/EDR not supported
        
        if include_hid:
            adv += b"\x03\x03\x12\x18"   # HID Service UUID (0x1812)
            adv += b"\x03\x19\xC4\x03"   # Appearance: Game Controller (0x03C4)

        # 名称部分
        name_bytes = name.encode("utf-8")
        max_len = 31 - len(adv) - 2
        if len(name_bytes) > max_len:
            name_bytes = name_bytes[:max_len]
        if name_bytes:
            adv.append(len(name_bytes) + 1)
            adv.append(0x09)  # Complete Local Name
            adv.extend(name_bytes)

        return bytes(adv)
    
    def _build_scan_resp_payload(self, name: str) -> bytes:
        """构建扫描响应数据, 仅包含设备名称, 避免占用主广播空间"""
        try:
            name_bytes = name.encode('utf-8')
        except Exception:
            name_bytes = b"ESP32C3"
        sr = bytearray()
        if name_bytes:
            # Complete Local Name
            max_len = 31 - 2
            if len(name_bytes) > max_len:
                name_bytes = name_bytes[:max_len]
            sr.append(len(name_bytes) + 1)
            sr.append(0x09)
            sr.extend(name_bytes)
        return bytes(sr)
    
    def _start_advertising_working(self):
        """极简版的广播设置"""
        try:
            # 将名称放到扫描响应里, 主广播仅携带 Flags+HID UUID+Appearance, 以提升被发现速度
            adv = self._build_adv_payload("", include_hid=self._use_hid)
            sr = self._build_scan_resp_payload(self.name)
            # 使用更快的广播间隔以更快被发现, 150ms
            self.ble.gap_advertise(150_000, adv_data=adv, resp_data=sr)
            self._is_advertising = True
            print(f"广播已启动: {self.name}")
            
        except Exception as e:
            print(f"带名称的广播失败: {e}")
            try:
                # 退化为仅 Flags 的极简广播
                self.ble.gap_advertise(200_000, adv_data=b"\x02\x01\x06")
                self._is_advertising = True
                print("极简广播已启动")
            except Exception as e2:
                print(f"极简广播也失败: {e2}")
                self._is_advertising = False
    
    def _init_hid_service(self):
        """注册最小可行 HID over GATT 服务, 使用 Consumer Control 作为遥控器"""
        print("尝试初始化 HID 服务(遥控器)...")
        # 定义 UUID
        HID_UUID = bluetooth.UUID(0x1812)
        HID_INFO_UUID = bluetooth.UUID(0x2A4A)
        HID_REPORT_MAP_UUID = bluetooth.UUID(0x2A4B)
        HID_CONTROL_POINT_UUID = bluetooth.UUID(0x2A4C)
        HID_PROTOCOL_MODE_UUID = bluetooth.UUID(0x2A4E)
        HID_REPORT_UUID = bluetooth.UUID(0x2A4D)
        REPORT_REF_UUID = bluetooth.UUID(0x2908)
        
        # 报告描述符: Consumer Control 遥控器
        # 采用16位Usage作为输入, 单键按下即发送Usage, 释放发送0x0000
        report_map = bytes([
            0x05, 0x0C,       # Usage Page (Consumer)
            0x09, 0x01,       # Usage (Consumer Control)
            0xA1, 0x01,       # Collection (Application)
            0x85, 0x01,       #   Report ID (1)
            0x15, 0x00,       #   Logical Minimum (0)
            0x26, 0xFF, 0x07, #   Logical Maximum (2047) 容纳常见消费类按键
            0x75, 0x10,       #   Report Size (16)
            0x95, 0x01,       #   Report Count (1)
            0x19, 0x00,       #   Usage Minimum (0)
            0x2A, 0xFF, 0x07, #   Usage Maximum (2047)
            0x81, 0x00,       #   Input (Data,Array,Abs)
            0xC0              # End Collection
        ])
        
        # 特征与描述符
        hid_info = (HID_INFO_UUID, bluetooth.FLAG_READ)
        report_map_char = (HID_REPORT_MAP_UUID, bluetooth.FLAG_READ)
        hid_cp = (HID_CONTROL_POINT_UUID, bluetooth.FLAG_WRITE_NO_RESPONSE)
        proto_mode = (HID_PROTOCOL_MODE_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE_NO_RESPONSE)
        # 输入报告 (带报告引用描述符)
        in_report = (
            HID_REPORT_UUID,
            bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
            (
                (REPORT_REF_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            ),
        )
        # 输出报告(遥控器一般不需要, 保留兼容)
        out_report = (
            HID_REPORT_UUID,
            bluetooth.FLAG_READ | bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE,
            (
                (REPORT_REF_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            ),
        )
        
        services = (
            (
                HID_UUID,
                (
                    hid_info,
                    report_map_char,
                    hid_cp,
                    proto_mode,
                    in_report,
                    out_report,
                ),
            ),
        )
        
        handles = self.ble.gatts_register_services(services)
        print(f"HID 服务注册返回: {handles}")
        svc = handles[0]
        # 正确解析每个特征与描述符的句柄
        def _first(x):
            return self._extract_first_int_handle(x)
        h_info = _first(svc[0])
        h_report_map = _first(svc[1])
        h_cp = _first(svc[2])
        h_proto = _first(svc[3])
        in_tuple = svc[4] if isinstance(svc[4], (list, tuple)) else (svc[4],)
        h_in = _first(in_tuple[0])
        h_in_ref = in_tuple[1] if (isinstance(in_tuple, (list, tuple)) and len(in_tuple) > 1 and isinstance(in_tuple[1], int)) else None
        out_tuple = svc[5] if isinstance(svc[5], (list, tuple)) else (svc[5],)
        h_out = _first(out_tuple[0])
        h_out_ref = out_tuple[1] if (isinstance(out_tuple, (list, tuple)) and len(out_tuple) > 1 and isinstance(out_tuple[1], int)) else None
        
        self._hid_handles = {
            'info': h_info,
            'report_map': h_report_map,
            'control_point': h_cp,
            'protocol_mode': h_proto,
            'in_report': h_in,
            'in_report_ref': h_in_ref,
            'out_report': h_out,
            'out_report_ref': h_out_ref,
        }
        
        # 写入特征初始值
        try:
            # HID 信息: bcdHID 0x0111, 国家码0, flags 0x00
            self.ble.gatts_write(h_info, b"\x11\x01\x00\x00")
            # 协议模式: 1 = Report Protocol
            self.ble.gatts_write(h_proto, b"\x01")
            # 报告映射
            self.ble.gatts_write(h_report_map, report_map)
            # 报告引用: 输入报告 ID=1, 类型=1(Input)
            if h_in_ref is not None:
                self.ble.gatts_write(h_in_ref, b"\x01\x01")
            # 报告引用: 输出报告 ID=1, 类型=2(Output)
            if h_out_ref is not None:
                self.ble.gatts_write(h_out_ref, b"\x01\x02")
        except Exception as e:
            print(f"写入 HID 初始值失败: {e}")
        
        # 设置用于通知的句柄为输入报告
        self._char_handle = h_in
        print(f"HID 输入报告句柄: {self._char_handle}")
        
        # 开始广播
        self._start_advertising_working()
    
    def _irq_handler(self, event, data):
        """基础版BLE事件处理"""
        try:
            if event == _IRQ_CENTRAL_CONNECT:
                # 设备连接
                conn_handle, addr_type, addr = data
                addr_str = ':'.join(f'{b:02x}' for b in addr)
                
                self._connections.add(conn_handle)
                self._device_info[conn_handle] = {
                    'address': addr_str,
                    'type': addr_type,
                    'connect_time': time.time()
                }
                
                print(f"设备已连接: {addr_str}")
                print(f"特征值句柄: {self._char_handle}")
                
                # 停止广播
                self.ble.gap_advertise(None)
                self._is_advertising = False
                
            elif event == _IRQ_CENTRAL_DISCONNECT:
                # 设备断开
                conn_handle, _, _ = data
                if conn_handle in self._connections:
                    addr_str = self._device_info[conn_handle]['address']
                    del self._device_info[conn_handle]
                    self._connections.remove(conn_handle)
                    
                    print(f"设备已断开: {addr_str}")
                    
                    # 重新开始广播
                    self._start_advertising_working()
                    
            elif event == _IRQ_GATTS_WRITE:
                # 收到数据
                conn_handle, value_handle = data
                print(f"收到数据: conn={conn_handle}, handle={value_handle}")
                # 如果是输出报告, 可解析LED状态等
                if self._use_hid:
                    out_h = self._hid_handles.get('out_report')
                    if isinstance(out_h, int) and value_handle == out_h:
                        try:
                            data_bytes = self.ble.gatts_read(value_handle)
                            print(f"输出报告数据: {data_bytes}")
                        except Exception:
                            pass
                
        except Exception as e:
            print(f"事件处理错误: {e}")
    
    def update_battery(self, level):
        """更新电池电量"""
        if self._char_handle is None:
            print("特征值句柄未设置")
            return False
            
        try:
            # 限制电量范围
            level = max(0, min(100, level))
            battery_data = bytes([level])
            
            print(f"更新电量: {level}% -> 句柄 {self._char_handle}")
            
            # 更新特征值
            self.ble.gatts_write(self._char_handle, battery_data)
            
            # 通知所有连接的设备
            for conn_handle in self._connections:
                try:
                    self.ble.gatts_notify(conn_handle, self._char_handle, battery_data)
                    print(f"通知发送到连接 {conn_handle}")
                except Exception as e:
                    print(f"通知失败: {e}")
            
            return True
            
        except Exception as e:
            print(f"电量更新失败: {e}")
            return False
    
    def send_message(self, message):
        """发送遥控器按键 Usage 或简单文本(非HID)"""
        if self._char_handle is None:
            print("特征值句柄未设置")
            return False
            
        try:
            if self._use_hid:
                # 将 message 映射为 Consumer Control Usage
                data = self._build_hid_consumer_report(message)
                if data is None:
                    print("不支持的遥控输入, 支持: 'power','vol_up','vol_down','mute','play_pause','next','prev' 或 0..65535 数字")
                    return False
                print(f"发送 HID 遥控输入: {data}")
                # 按下
                self.ble.gatts_write(self._char_handle, data)
                for conn_handle in self._connections:
                    try:
                        self.ble.gatts_notify(conn_handle, self._char_handle, data)
                    except Exception as e:
                        print(f"通知失败: {e}")
                # 释放
                release = b"\x00\x00"
                self.ble.gatts_write(self._char_handle, release)
                for conn_handle in self._connections:
                    try:
                        self.ble.gatts_notify(conn_handle, self._char_handle, release)
                    except Exception as e:
                        print(f"通知失败: {e}")
                return True
            else:
                # 发送简单的数字而不是文本
                if isinstance(message, str):
                    # 尝试发送简单的ASCII字符
                    data = message.encode('ascii')
                else:
                    data = bytes([message])  # 单字节
                
                print(f"发送数据: {data} -> 句柄 {self._char_handle}")
                
                # 更新特征值
                self.ble.gatts_write(self._char_handle, data)
                
                # 通知所有连接的设备
                for conn_handle in self._connections:
                    try:
                        self.ble.gatts_notify(conn_handle, self._char_handle, data)
                        print(f"通知发送到连接 {conn_handle}")
                    except Exception as e:
                        print(f"通知失败: {e}")
                
                return True
            
        except Exception as e:
            print(f"消息发送失败: {e}")
            return False
    
    def _build_hid_consumer_report(self, message):
        """构造 Consumer Control 16位输入报告: 2字节Usage值, 0x0000表示释放"""
        # 允许传入字符串别名或直接数值
        aliases = {
            'power': 0x0030,       # Power
            'vol_up': 0x00E9,      # Volume Increment
            'vol_down': 0x00EA,    # Volume Decrement
            'mute': 0x00E2,        # Mute
            'play_pause': 0x00CD,  # Play/Pause
            'next': 0x00B5,        # Scan Next Track
            'prev': 0x00B6,        # Scan Previous Track
            'stop': 0x00B7,        # Stop
        }
        try:
            if isinstance(message, (bytes, bytearray)) and len(message) == 2:
                return bytes(message)
            if isinstance(message, str):
                key = message.strip().lower()
                if key in aliases:
                    u = aliases[key]
                    return bytes([u & 0xFF, (u >> 8) & 0xFF])
                # 尝试将字符串当作整数
                if key.isdigit():
                    u = int(key)
                    if 0 <= u <= 0xFFFF:
                        return bytes([u & 0xFF, (u >> 8) & 0xFF])
            if isinstance(message, int) and 0 <= message <= 0xFFFF:
                return bytes([message & 0xFF, (message >> 8) & 0xFF])
        except Exception:
            return None
        return None
    
    def is_connected(self):
        """检查是否有设备连接"""
        return len(self._connections) > 0
    
    def get_connection_count(self):
        """获取连接数量"""
        return len(self._connections)
    
    def get_status(self):
        """获取状态信息"""
        return {
            'active': self.ble.active(),
            'advertising': self._is_advertising,
            'connections': self.get_connection_count(),
            'devices': list(self._device_info.values()),
            'char_handle': self._char_handle,
            'hid': self._use_hid,
        }
    
    def stop(self):
        """停止蓝牙服务"""
        try:
            # 断开所有连接
            for conn_handle in list(self._connections):
                self.ble.gap_disconnect(conn_handle)
            
            # 停止广播
            self.ble.gap_advertise(None)
            
            # 停用蓝牙
            self.ble.active(False)
            
            print("蓝牙服务已停止")
            
        except Exception as e:
            print(f"停止服务失败: {e}")

# 测试函数
async def test_bluetooth_working():
    """极简版蓝牙测试"""
    print("=== ESP32-C3 蓝牙测试 (极简版) ===")
    print("专注于最基础的连接功能")
    print()
    
    try:
        # 创建蓝牙测试实例, 默认启用 HID
        bt = ESP32C3BluetoothWorking("ESP32 Sensor", use_hid=True)
        
        print("蓝牙初始化完成")
        print("请使用手机蓝牙APP搜索 'ESP32 Sensor'")
        print("按 Ctrl+C 停止测试")
        print()
        
        # 只显示状态, 不发送数据
        while True:
            try:
                status = bt.get_status()
                if bt.is_connected():
                    print(f"状态: 连接={status['connections']}, 设备={status['devices']}")
                else:
                    print(f"状态: 广播中={status['advertising']}, 等待连接...")
                
                await asyncio.sleep(3)
                
            except KeyboardInterrupt:
                print("测试被用户中断")
                break
            except Exception as e:
                print(f"测试错误: {e}")
                await asyncio.sleep(1)
        
        # 停止服务
        bt.stop()
        print("测试完成")
        
    except Exception as e:
        print(f"蓝牙初始化失败: {e}")
        await simple_test()

async def simple_test():
    """极简蓝牙测试"""
    print("=== 极简蓝牙测试 ===")
    
    try:
        print("步骤1: 检查蓝牙模块...")
        ble = bluetooth.BLE()
        print(f"蓝牙对象创建成功: {type(ble)}")
        
        print("步骤2: 激活蓝牙...")
        ble.active(True)
        print(f"蓝牙激活状态: {ble.active()}")
        
        print("步骤3: 检查可用方法...")
        methods = [method for method in dir(ble) if not method.startswith('_')]
        print(f"可用方法: {methods}")
        
        print("步骤4: 测试不同广播方式...")
        
        # 测试方式1: 最简单的广播
        print("测试方式1: 仅 Flags 广播...")
        ble.gap_advertise(500_000, adv_data=b"\x02\x01\x06")
        print("仅 Flags 广播已启动")
        await asyncio.sleep(5)
        ble.gap_advertise(None)
        print("仅 Flags 广播已停止")
        await asyncio.sleep(2)
        
        # 测试方式2: 带设备名称的广播
        print("测试方式2: 带名称广播...")
        name_bytes = "ESP32-C3".encode('utf-8')
        max_name_len = 31 - 3 - 2
        if len(name_bytes) > max_name_len:
            name_bytes = name_bytes[:max_name_len]
        adv = bytearray(b"\x02\x01\x06")
        adv.append(len(name_bytes) + 1)
        adv.append(0x09)
        adv.extend(name_bytes)
        ble.gap_advertise(500_000, adv_data=bytes(adv))
        print("带名称广播已启动")
        await asyncio.sleep(5)
        ble.gap_advertise(None)
        print("带名称广播已停止")
        await asyncio.sleep(2)
        
        # 测试方式3: 标准广播数据
        print("测试方式3: 标准广播数据...")
        adv_data = bytearray(b"\x02\x01\x06")
        name_bytes = "ESP32C3".encode('utf-8')
        adv_data.append(len(name_bytes) + 1)
        adv_data.append(0x09)
        adv_data.extend(name_bytes)
        
        ble.gap_advertise(500_000, adv_data=bytes(adv_data))
        print("标准广播数据已启动")
        await asyncio.sleep(5)
        ble.gap_advertise(None)
        print("标准广播数据已停止")
        
        print("步骤5: 清理...")
        ble.active(False)
        print("蓝牙已停用")
        
        print("极简测试完成")
        
    except Exception as e:
        print(f"极简测试失败: {e}")
        import traceback
        traceback.print_exc()

# 主函数
async def main():
    """主函数"""
    print("ESP32-C3 蓝牙模块测试 (极简版)")
    await test_bluetooth_working()

# 直接运行
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("程序被中断")
    except Exception as e:
        print(f"运行错误: {e}")
        import traceback
        traceback.print_exc()