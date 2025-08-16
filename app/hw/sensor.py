# app/hw/sensor.py
"""
ESP32-C3传感器管理器 (重构版本)
内部温度传感器和外部传感器支持

基于事件驱动架构, 通过对象池优化内存使用。
支持内部温度传感器和多种外部传感器(DHT11/DHT22/BMP280)。

特性:
- 事件驱动的数据采集
- 对象池内存优化
- 多传感器支持
- 统一的数据接口
"""

import utime as time
from lib.object_pool import get_object_pool_manager
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
import gc


class SensorManager:
    """
    传感器管理器
    管理内部和外部传感器数据采集
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.object_pool = get_object_pool_manager()
        # 移除logger实例, 直接使用全局日志函数
        self.sensors = {}
        self.sensor_data = {}
        self.last_read_time = {}
        self.read_intervals = {}

        # 数据变化检测和频率限制
        self.last_published_data = {}  # 存储上次发布的数据
        self.last_publish_time = {}  # 存储上次发布时间

        # 初始化logger
        # 移除logger实例, 直接使用全局日志函数
        self.min_publish_interval = 2000  # 最小发布间隔2秒
        self.data_change_threshold = 0.1  # 数据变化阈值10%

        # 初始化内部传感器
        self._init_internal_sensors()

    def _has_data_changed_significantly(self, sensor_id, new_data):
        """检查数据是否发生显著变化"""
        if sensor_id not in self.last_published_data:
            return True  # 首次发布

        old_data = self.last_published_data[sensor_id]

        # 处理不同类型的数据
        if isinstance(new_data, (int, float)) and isinstance(old_data, (int, float)):
            # 数值类型数据, 检查相对变化
            if old_data == 0:
                return new_data != 0  # 避免除零
            relative_change = abs(new_data - old_data) / abs(old_data)
            return relative_change > self.data_change_threshold
        elif isinstance(new_data, dict) and isinstance(old_data, dict):
            # 字典类型数据, 检查关键字段的变化
            for key in new_data:
                if key in old_data:
                    if isinstance(new_data[key], (int, float)) and isinstance(
                        old_data[key], (int, float)
                    ):
                        if old_data[key] == 0:
                            if new_data[key] != 0:
                                return True
                        else:
                            relative_change = abs(new_data[key] - old_data[key]) / abs(
                                old_data[key]
                            )
                            if relative_change > self.data_change_threshold:
                                return True
                else:
                    return True  # 新字段
            return False
        else:
            # 其他类型, 直接比较
            return new_data != old_data

    def _should_publish_sensor_data(self, sensor_id, data):
        """检查是否应该发布传感器数据"""
        now = time.ticks_ms()

        # 检查发布频率限制
        if sensor_id in self.last_publish_time:
            if (
                time.ticks_diff(now, self.last_publish_time[sensor_id])
                < self.min_publish_interval
            ):
                return False

        # 检查数据变化
        if not self._has_data_changed_significantly(sensor_id, data):
            return False

        return True

    def _init_internal_sensors(self):
        """初始化ESP32-C3内部传感器"""
        try:
            # 温度传感器
            self.add_sensor(
                "internal_temp",
                self._read_internal_temperature,
                interval=5000,  # 5秒间隔
            )
            info("内部温度传感器已初始化", module="Sensor")
        except Exception as e:
            error("初始化内部温度传感器失败: {}", e, module="Sensor")

    def add_sensor(self, sensor_id, read_func, interval=1000, enabled=True):
        """
        添加传感器
        Args:
            sensor_id: 传感器ID
            read_func: 读取函数
            interval: 读取间隔
            enabled: 是否启用
        """
        self.sensors[sensor_id] = {
            "read_func": read_func,
            "interval": interval,
            "enabled": enabled,
        }
        self.last_read_time[sensor_id] = 0
        self.sensor_data[sensor_id] = None

    def remove_sensor(self, sensor_id):
        """移除传感器"""
        if sensor_id in self.sensors:
            del self.sensors[sensor_id]
            del self.last_read_time[sensor_id]
            del self.sensor_data[sensor_id]

    def enable_sensor(self, sensor_id):
        """启用传感器"""
        if sensor_id in self.sensors:
            self.sensors[sensor_id]["enabled"] = True

    def disable_sensor(self, sensor_id):
        """禁用传感器"""
        if sensor_id in self.sensors:
            self.sensors[sensor_id]["enabled"] = False

    def read_sensor(self, sensor_id):
        """
        读取指定传感器数据
        返回传感器数据, 失败返回None
        """
        if sensor_id not in self.sensors:
            return None

        sensor = self.sensors[sensor_id]
        if not sensor["enabled"]:
            return None

        try:
            value = sensor["read_func"]()
            self.sensor_data[sensor_id] = value
            self.last_read_time[sensor_id] = time.ticks_ms()

            # 发布传感器数据事件(保持向后兼容的签名：sensor_id, value)
            if value is not None:
                # 检查是否应该发布(数据变化检测和频率限制)
                if self._should_publish_sensor_data(sensor_id, value):
                    self.event_bus.publish(EVENTS["SENSOR_DATA"], sensor_id, value)
                    # 更新发布记录
                    self.last_published_data[sensor_id] = value
                    self.last_publish_time[sensor_id] = time.ticks_ms()
                else:
                    # 数据无显著变化或发布频率过高, 跳过发布
                    debug(
                        "传感器{}数据无显著变化, 跳过发布", sensor_id, module="Sensor"
                    )

            return value
        except Exception as e:
            error("读取传感器{}失败: {}", sensor_id, e, module="Sensor")
            return None

    def get_sensor_data(self, sensor_id):
        """获取传感器最新数据"""
        return self.sensor_data.get(sensor_id)

    def update_all_sensors(self):
        """更新所有启用的传感器"""
        current_time = time.ticks_ms()

        for sensor_id, sensor in self.sensors.items():
            if not sensor["enabled"]:
                continue

            # 检查是否需要读取
            if (current_time - self.last_read_time[sensor_id]) >= sensor["interval"]:
                self.read_sensor(sensor_id)

    def get_all_sensor_data(self):
        """获取所有传感器数据"""
        return self.sensor_data.copy()

    def get_sensor_status(self):
        """获取所有传感器状态"""
        status = {}
        for sensor_id, sensor in self.sensors.items():
            status[sensor_id] = {
                "enabled": sensor["enabled"],
                "interval": sensor["interval"],
                "last_read": self.last_read_time[sensor_id],
                "has_data": self.sensor_data[sensor_id] is not None,
            }
        return status

    # 内部传感器读取函数
    def _read_internal_temperature(self):
        """读取ESP32-C3内部温度"""
        try:
            from utils.helpers import get_temperature

            return get_temperature()
        except Exception as e:
            error("内部温度读取错误: {}", e, module="Sensor")
            return None


class ExternalSensorManager:
    """
    外部传感器管理器
    支持DHT11、DHT22、BMP280等外部传感器
    """

    def __init__(self, event_bus):
        import machine

        self.event_bus = event_bus
        self.object_pool = get_object_pool_manager()
        self.external_sensors = {}
        self.i2c = None
        self.spi = None
        self.machine = machine

        # 数据变化检测和频率限制
        self.last_published_data = {}  # 存储上次发布的数据
        self.last_publish_time = {}  # 存储上次发布时间

        # 初始化logger
        # 移除logger实例, 直接使用全局日志函数

    def init_i2c(self, scl_pin, sda_pin, freq=400000):
        """初始化I2C总线"""
        try:
            self.i2c = self.machine.I2C(
                0,
                scl=self.machine.Pin(scl_pin),
                sda=self.machine.Pin(sda_pin),
                freq=freq,
            )
            info("I2C已初始化: SCL={}, SDA={}", scl_pin, sda_pin, module="Sensor")
            return True
        except Exception as e:
            error("I2C初始化失败: {}", e, module="Sensor")
            return False

    def init_spi(self, sck_pin, mosi_pin, miso_pin, cs_pin, freq=1000000):
        """初始化SPI总线"""
        try:
            self.spi = self.machine.SPI(
                0,
                sck=self.machine.Pin(sck_pin),
                mosi=self.machine.Pin(mosi_pin),
                miso=self.machine.Pin(miso_pin),
                freq=freq,
            )
            self.cs_pin = self.machine.Pin(cs_pin, self.machine.Pin.OUT)
            self.cs_pin.value(1)  # CS默认高电平
            info(
                "SPI已初始化: SCK={}, MOSI={}, MISO={}, CS={}",
                sck_pin,
                mosi_pin,
                miso_pin,
                cs_pin,
                module="Sensor",
            )
            return True
        except Exception as e:
            error("SPI初始化失败: {}", e, module="Sensor")
            return False

    def add_dht_sensor(self, sensor_id, pin, sensor_type="DHT11"):
        """
        添加DHT系列传感器
        需要安装dht库
        """
        try:
            import dht

            if sensor_type == "DHT11":
                sensor = dht.DHT11(self.machine.Pin(pin))
            elif sensor_type == "DHT22":
                sensor = dht.DHT22(self.machine.Pin(pin))
            else:
                raise ValueError("不支持的DHT传感器类型: {}".format(sensor_type))

            self.external_sensors[sensor_id] = {
                "type": "DHT",
                "sensor": sensor,
                "read_func": self._read_dht_sensor,
            }

            info("DHT{}传感器已添加到引脚{}", sensor_type, pin, module="Sensor")
            return True
        except ImportError:
            warning("DHT库不可用", module="Sensor")
            return False
        except Exception as e:
            error("添加DHT传感器失败: {}", e, module="Sensor")
            return False

    def _read_dht_sensor(self, sensor):
        """读取DHT传感器"""
        try:
            sensor.measure()
            temperature = sensor.temperature()
            humidity = sensor.humidity()

            return {"temperature": temperature, "humidity": humidity}
        except Exception as e:
            error("DHT读取错误: {}", e, module="Sensor")
            return None

    def add_bmp280_sensor(self, sensor_id, i2c_addr=0x76):
        """
        添加BMP280气压传感器
        需要安装bmp280库
        """
        if not self.i2c:
            warning("I2C未初始化", module="Sensor")
            return False

        try:
            import bmp280

            sensor = bmp280.BMP280(self.i2c, addr=i2c_addr)

            self.external_sensors[sensor_id] = {
                "type": "BMP280",
                "sensor": sensor,
                "read_func": self._read_bmp280_sensor,
            }

            info("BMP280传感器已添加到地址0x{:02x}", i2c_addr, module="Sensor")
            return True
        except ImportError:
            warning("BMP280库不可用", module="Sensor")
            return False
        except Exception as e:
            error("添加BMP280传感器失败: {}", e, module="Sensor")
            return False

    def _read_bmp280_sensor(self, sensor):
        """读取BMP280传感器"""
        try:
            temperature = sensor.temperature
            pressure = sensor.pressure

            return {
                "temperature": temperature,
                "pressure": pressure,
                "altitude": self._calculate_altitude(pressure),
            }
        except Exception as e:
            error("BMP280读取错误: {}", e, module="Sensor")
            return None

    def _calculate_altitude(self, pressure):
        """计算海拔高度"""
        try:
            # 标准大气压1013.25 hPa
            sea_level_pressure = 1013.25
            altitude = 44330 * (1 - (pressure / sea_level_pressure) ** 0.1903)
            return round(altitude, 1)
        except Exception:
            return None

    def read_external_sensor(self, sensor_id):
        """读取外部传感器"""
        if sensor_id not in self.external_sensors:
            return None

        sensor_info = self.external_sensors[sensor_id]
        try:
            data = sensor_info["read_func"](sensor_info["sensor"])

            if data is not None:
                # 保持事件签名一致
                # 检查是否应该发布(数据变化检测和频率限制)
                if self._should_publish_sensor_data(sensor_id, data):
                    self.event_bus.publish(EVENTS["SENSOR_DATA"], sensor_id, data)
                    # 更新发布记录
                    self.last_published_data[sensor_id] = data
                    self.last_publish_time[sensor_id] = time.ticks_ms()
                else:
                    # 数据无显著变化或发布频率过高, 跳过发布
                    debug(
                        "外部传感器{}数据无显著变化, 跳过发布",
                        sensor_id,
                        module="Sensor",
                    )

            return data
        except Exception as e:
            error("读取外部传感器{}失败: {}", sensor_id, e, module="Sensor")
            return None

    def get_external_sensors(self):
        """获取所有外部传感器列表"""
        return list(self.external_sensors.keys())

    def _has_data_changed_significantly(self, sensor_id, new_data):
        """检查数据是否发生显著变化"""
        if sensor_id not in self.last_published_data:
            return True  # 首次发布

        old_data = self.last_published_data[sensor_id]

        # 处理不同类型的数据
        if isinstance(new_data, (int, float)) and isinstance(old_data, (int, float)):
            # 数值类型数据, 检查相对变化
            if old_data == 0:
                return new_data != 0  # 避免除零
            relative_change = abs(new_data - old_data) / abs(old_data)
            return relative_change > 0.1  # 10%变化阈值
        elif isinstance(new_data, dict) and isinstance(old_data, dict):
            # 字典类型数据, 检查关键字段的变化
            for key in new_data:
                if key in old_data:
                    if isinstance(new_data[key], (int, float)) and isinstance(
                        old_data[key], (int, float)
                    ):
                        if old_data[key] == 0:
                            if new_data[key] != 0:
                                return True
                        else:
                            relative_change = abs(new_data[key] - old_data[key]) / abs(
                                old_data[key]
                            )
                            if relative_change > 0.1:  # 10%变化阈值
                                return True
                else:
                    return True  # 新字段
            return False
        else:
            # 其他类型, 直接比较
            return new_data != old_data

    def _should_publish_sensor_data(self, sensor_id, data):
        """检查是否应该发布传感器数据"""
        now = time.ticks_ms()

        # 检查发布频率限制
        if sensor_id in self.last_publish_time:
            if (
                time.ticks_diff(now, self.last_publish_time[sensor_id]) < 2000
            ):  # 2秒间隔
                return False

        # 检查数据变化
        if not self._has_data_changed_significantly(sensor_id, data):
            return False

        return True


# Sensor module loaded
