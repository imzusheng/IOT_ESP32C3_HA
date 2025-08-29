"""
ESP32-C3 蓝牙模块
"""

import bluetooth
import time
from micropython import const
import micropython
from machine import Timer

# 蓝牙常量
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# 新增: 从配置读取支持
try:
    from app.config import get_config as _get_config
except Exception:
    _get_config = None
try:
    from app.utils.json_utils import load_json_file as _load_json
except Exception:
    _load_json = None

class ESP32C3BluetoothWorking:
    """ESP32-C3蓝牙类"""
    
    def __init__(self, name="ESP32-C3", use_hid=True, adv_interval_ms=150):
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
        # 电量模拟定时器相关
        self._sim_timer = None
        self._sim_batt = 100
        self._sim_step = -1
        self._sim_min = 0
        # 新增: 支持通过 HardwareTimerManager 管理电量模拟定时器
        self._sim_timer_manager = None
        self._sim_timer_managed = False
        # 新增: 广播间隔(微秒)
        try:
            self._adv_interval_us = int(adv_interval_ms) * 1000
        except Exception:
            self._adv_interval_us = 150_000
        
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
        """服务初始化"""
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
        """广播设置"""
        try:
            # 将名称放到扫描响应里, 主广播仅携带 Flags+HID UUID+Appearance, 以提升被发现速度
            adv = self._build_adv_payload("", include_hid=self._use_hid)
            sr = self._build_scan_resp_payload(self.name)
            # 使用配置的广播间隔(默认 150ms)
            self.ble.gap_advertise(self._adv_interval_us, adv_data=adv, resp_data=sr)
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
        """BLE事件处理"""
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
            # 先停止电量模拟
            self.stop_battery_simulation()
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

    # 电量模拟: 使用硬件定时器触发, 在 IRQ 中仅调度到主上下文执行
    def start_battery_simulation(self, start=100, step=-1, min_level=0, period_ms=10000, timer_id=0):
        """启动电量模拟与通知
        start: 初始电量百分比
        step: 每次变化步长, 默认每次 -1
        min_level: 最低电量值, 低于该值则回到 100
        period_ms: 触发周期, 默认 10000ms
        timer_id: 定时器编号, 默认 0; 传入 <0 时使用 HardwareTimerManager 自动分配
        """
        self._sim_batt = int(start)
        self._sim_step = int(step)
        self._sim_min = int(min_level)
        # 先停止已有定时器
        if self._sim_timer:
            try:
                if self._sim_timer_managed and self._sim_timer_manager:
                    self._sim_timer_manager.release_timer(self._sim_timer)
                else:
                    self._sim_timer.deinit()
            except Exception:
                pass
            self._sim_timer = None
            self._sim_timer_managed = False

        # 选择创建方式: 管理器或直接 Timer
        if timer_id is not None and int(timer_id) < 0:
            try:
                from app.utils import get_hardware_timer_manager
                self._sim_timer_manager = get_hardware_timer_manager()
                self._sim_timer = self._sim_timer_manager.create_timer(int(period_ms), self._on_timer_batt)
                if self._sim_timer:
                    self._sim_timer_managed = True
                    print(f"电量模拟(管理器)已启动: start={self._sim_batt}, step={self._sim_step}, period={period_ms}ms")
                    return
                else:
                    print("电量模拟(管理器)启动失败: 无可用硬件定时器")
            except Exception as e:
                print(f"电量模拟(管理器)异常: {e}")
                self._sim_timer = None
                self._sim_timer_managed = False

        # 回退: 使用指定的硬件定时器编号
        try:
            self._sim_timer = Timer(int(timer_id))
            self._sim_timer.init(period=int(period_ms), mode=Timer.PERIODIC, callback=self._on_timer_batt)
            self._sim_timer_managed = False
            print(f"电量模拟已启动: start={self._sim_batt}, step={self._sim_step}, period={period_ms}ms, timer_id={timer_id}")
        except Exception as e:
            print(f"电量模拟启动失败: {e}")
            try:
                if self._sim_timer:
                    self._sim_timer.deinit()
            except Exception:
                pass
            self._sim_timer = None
            self._sim_timer_managed = False

    def stop_battery_simulation(self):
        """停止电量模拟定时器"""
        if self._sim_timer:
            try:
                if self._sim_timer_managed and self._sim_timer_manager:
                    self._sim_timer_manager.release_timer(self._sim_timer)
                else:
                    self._sim_timer.deinit()
            except Exception:
                pass
            self._sim_timer = None
            self._sim_timer_managed = False
            print("电量模拟已停止")

    def _on_timer_batt(self, t):
        # 将电量更新任务调度到主上下文, 避免在中断里直接操作 BLE
        try:
            micropython.schedule(self._scheduled_batt_update, 0)
        except Exception:
            pass

    def _scheduled_batt_update(self, _):
        try:
            # 计算下一次电量
            next_lvl = self._sim_batt + self._sim_step
            if next_lvl < self._sim_min:
                next_lvl = 100
            if next_lvl > 100:
                next_lvl = 100
            self._sim_batt = next_lvl
            # 写入并通知
            self.update_battery(self._sim_batt)
        except Exception as e:
            print(f"电量模拟更新失败: {e}")

def main():
    """主函数"""
    print("ESP32-C3 蓝牙模块")
    
    # 读取 BLE 配置(默认层来自 app/config.py, 运行时层来自 /config.json)
    ble_defaults = None
    if _get_config:
        try:
            ble_defaults = _deep_copy(_get_config('ble'))
        except Exception:
            ble_defaults = None
    if not isinstance(ble_defaults, dict):
        ble_defaults = {
            "enabled": True,
            "use_hid": False,
            "device_name": "ESP32-C3",
            "adv": {"interval_ms": 150},
            "simulation": {"battery": {"enabled": False, "start": 100, "step": -1, "min": 0, "period_ms": 10000, "timer_id": 0}},
            "config_service": {"persistence_path": "/config.json"},
        }
    # 加载运行时覆盖
    try:
        persistence_path = ble_defaults.get("config_service", {}).get("persistence_path", "/config.json")
    except Exception:
        persistence_path = "/config.json"
    runtime_overlay = {}
    if _load_json:
        try:
            runtime_overlay = _load_json(persistence_path, {})
        except Exception:
            runtime_overlay = {}
    overlay_ble = runtime_overlay.get("ble") if isinstance(runtime_overlay, dict) else None
    if isinstance(overlay_ble, dict):
        _deep_merge(ble_defaults, overlay_ble)
    ble_conf = ble_defaults
    
    # 配置未启用时直接返回
    if not ble_conf.get("enabled", True):
        print("BLE 功能未启用, 退出")
        return None
    
    # 创建蓝牙实例
    name = ble_conf.get("device_name", "ESP32-C3")
    use_hid = ble_conf.get("use_hid", False)
    adv_ms = int(ble_conf.get("adv", {}).get("interval_ms", 150))
    bt = ESP32C3BluetoothWorking(name, use_hid=use_hid, adv_interval_ms=adv_ms)
    
    print("蓝牙初始化完成")
    print(f"设备名称: {name}")
    print(f"状态: {bt.get_status()}")
    
    # 启动电量模拟(可选)
    try:
        sim = ble_conf.get("simulation", {}).get("battery", {})
        if sim.get("enabled", True):
            bt.start_battery_simulation(
                start=int(sim.get("start", 100)),
                step=int(sim.get("step", -1)),
                min_level=int(sim.get("min", 0)),
                period_ms=int(sim.get("period_ms", 10000)),
                timer_id=int(sim.get("timer_id", 0)),
            )
    except Exception as e:
        print(f"启动电量模拟失败: {e}")
    
    return bt

if __name__ == "__main__":
    try:
        bt = main()
        print("蓝牙模块已启动")
    except KeyboardInterrupt:
        print("程序被中断")
    except Exception as e:
        print(f"运行错误: {e}")
        import traceback
        traceback.print_exc()

# 新增: 配置合并工具
def _deep_copy(obj):
    try:
        if isinstance(obj, dict):
            return {k: _deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [ _deep_copy(x) for x in obj ]
    except Exception:
        pass
    return obj

def _deep_merge(dst, src):
    try:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _deep_merge(dst[k], v)
            else:
                dst[k] = v
    except Exception:
        pass
    return dst