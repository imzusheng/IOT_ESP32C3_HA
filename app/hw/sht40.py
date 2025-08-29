# -*- coding: utf-8 -*-
"""
SHT40 温湿度传感器辅助模块(独立模块)

设计目标:
- 延迟初始化: I2C 总线在首次使用时创建
- 简单 API: read() 返回温度与相对湿度
- 最小依赖: 仅依赖 machine 与 utime, 日志使用 lib.logger
- 无定时器: 按需进行单次测量

默认接线(ESP32-C3):
- SDA -> GPIO 4
- SCL -> GPIO 5
- VCC/+ -> 3.3V, GND/- -> GND

参考: Sensirion SHT4x 单次测量指令
- 高精度测量: 0xFD
- 中精度测量: 0xF6
- 低精度测量: 0xE0
- 软复位: 0x94

地址: 0x44(部分器件可能响应 0x45)
"""

import utime as time
import machine
from lib.logger import info, warning, error

# =============================================================================
# 常量定义
# =============================================================================
# 配置说明: 推荐通过 configure() 传入 sda, scl, freq 进行运行时配置, 无需直接修改常量
MODULE_NAME = "SHT40"  # 模块名称, 用于日志标识
DEFAULT_SDA_PIN = 4      # 默认 SDA 引脚(ESP32-C3), 可在 configure() 中覆盖
DEFAULT_SCL_PIN = 5      # 默认 SCL 引脚(ESP32-C3), 可在 configure() 中覆盖
DEFAULT_FREQ = 100_000   # I2C 频率 Hz, 建议 100k ~ 400k, 线长较长或干扰较大时使用 100k

SHT4X_ADDR_PRIMARY = 0x44     # 常见地址 0x44, 大多数 SHT40 模组使用该地址
SHT4X_ADDR_SECONDARY = 0x45    # 备用地址 0x45, 某些型号或焊接选项可能使用

CMD_MEASURE_HIGH = b"\xFD"  # 高精度
CMD_MEASURE_MED = b"\xF6"   # 中精度
CMD_MEASURE_LOW = b"\xE0"   # 低精度
CMD_SOFT_RESET = b"\x94"    # 软复位指令

# 各精度对应的最小测量等待时间(ms), 从下发指令到数据可读
MEASURE_DELAY_MS = {
    CMD_MEASURE_HIGH: 10,  # 高精度耗时更长, 但噪声更低
    CMD_MEASURE_MED: 7,    # 中精度在速度与精度之间折中
    CMD_MEASURE_LOW: 5,    # 低精度速度最快, 适合功耗或实时性更高场景
}


class _SHT40:
    def __init__(self, sda: int = DEFAULT_SDA_PIN, scl: int = DEFAULT_SCL_PIN, freq: int = DEFAULT_FREQ):
        self.sda_pin = sda
        self.scl_pin = scl
        self.freq = freq
        self.i2c = None
        self.address = None

    # ---------------------- 底层辅助方法 ----------------------
    def _ensure_i2c(self):
        if self.i2c is None:
            try:
                self.i2c = machine.I2C(0, sda=machine.Pin(self.sda_pin), scl=machine.Pin(self.scl_pin), freq=self.freq)
            except Exception as e:
                error(f"I2C init failed: {e}", module=MODULE_NAME)
                self.i2c = None
                return False
        return True

    def _detect_address(self):
        if not self._ensure_i2c():
            return False
        if self.address is not None:
            return True
        try:
            devices = self.i2c.scan()
            if SHT4X_ADDR_PRIMARY in devices:
                self.address = SHT4X_ADDR_PRIMARY
            elif SHT4X_ADDR_SECONDARY in devices:
                self.address = SHT4X_ADDR_SECONDARY
            else:
                warning("SHT40 not found on I2C bus", module=MODULE_NAME)
                return False
            info(f"SHT40 detected at 0x{self.address:02X}", module=MODULE_NAME)
            return True
        except Exception as e:
            error(f"I2C scan failed: {e}", module=MODULE_NAME)
            return False

    def _crc8(self, data: bytes) -> int:
        # Sensirion CRC-8 多项式 0x31, 初始值 0xFF
        polynomial = 0x31
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ polynomial) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def _convert_temperature(self, raw: int) -> float:
        # 温度转换公式: T(C) = -45 + 175 * raw / 65535
        return round(-45.0 + 175.0 * (raw / 65535.0), 1)

    def _convert_humidity(self, raw: int) -> float:
        # 相对湿度转换公式: RH(%) = -6 + 125 * raw / 65535
        rh = -6.0 + 125.0 * (raw / 65535.0)
        if rh < 0:
            rh = 0.0
        if rh > 100:
            rh = 100.0
        return round(rh, 1)

    # ---------------------- 公共API ----------------------
    def exists(self) -> bool:
        return self._detect_address()

    def soft_reset(self) -> bool:
        if not self._detect_address():
            return False
        try:
            self.i2c.writeto(self.address, CMD_SOFT_RESET)
            time.sleep_ms(2)
            return True
        except Exception as e:
            error(f"Soft reset failed: {e}", module=MODULE_NAME)
            return False

    def read(self, precision: bytes = CMD_MEASURE_HIGH):
        """
        进行一次测量并返回温度与湿度。
        precision: 可选 CMD_MEASURE_HIGH, CMD_MEASURE_MED, CMD_MEASURE_LOW
        返回: {"temperature": float 或 None, "humidity": float 或 None}
        """
        if precision not in (CMD_MEASURE_HIGH, CMD_MEASURE_MED, CMD_MEASURE_LOW):
            precision = CMD_MEASURE_HIGH
        if not self._detect_address():
            return {"temperature": None, "humidity": None}

        try:
            # 触发测量
            self.i2c.writeto(self.address, precision)
            time.sleep_ms(MEASURE_DELAY_MS.get(precision, 10))

            # 读取6字节: 温度高字节(T_msb), 温度低字节(T_lsb), 温度CRC(T_crc), 湿度高字节(RH_msb), 湿度低字节(RH_lsb), 湿度CRC(RH_crc)
            data = self.i2c.readfrom(self.address, 6)
            if len(data) != 6:
                warning("Invalid data length from SHT40", module=MODULE_NAME)
                return {"temperature": None, "humidity": None}

            t_raw = (data[0] << 8) | data[1]
            t_crc = data[2]
            rh_raw = (data[3] << 8) | data[4]
            rh_crc = data[5]

            if self._crc8(data[0:2]) != t_crc or self._crc8(data[3:5]) != rh_crc:
                warning("CRC check failed for SHT40 data", module=MODULE_NAME)
                return {"temperature": None, "humidity": None}

            temp_c = self._convert_temperature(t_raw)
            rh = self._convert_humidity(rh_raw)
            return {"temperature": temp_c, "humidity": rh}
        except Exception as e:
            error(f"Read failed: {e}", module=MODULE_NAME)
            return {"temperature": None, "humidity": None}

    def cleanup(self):
        try:
            self.i2c = None
            self.address = None
        except Exception:
            pass


# =============================================================================
# 模块级单例与公共辅助方法
# =============================================================================
_instance = None


def _get_instance():
    global _instance
    if _instance is None:
        _instance = _SHT40()
    return _instance


def read(precision: str = "high"):
    """
    通过模块级单例读取一次数据。
    precision: "high", "med", 或 "low"
    返回字典: {"temperature": float 或 None, "humidity": float 或 None}
    """
    inst = _get_instance()
    cmd = CMD_MEASURE_HIGH if precision == "high" else (CMD_MEASURE_MED if precision == "med" else CMD_MEASURE_LOW)
    return inst.read(cmd)


def exists() -> bool:
    inst = _get_instance()
    return inst.exists()


def soft_reset() -> bool:
    inst = _get_instance()
    return inst.soft_reset()


def configure(sda: int = DEFAULT_SDA_PIN, scl: int = DEFAULT_SCL_PIN, freq: int = DEFAULT_FREQ):
    """
    重新配置 I2C 引脚或频率。
    调用后会重置内部 I2C 句柄, 下次访问将自动重新检测设备。
    """
    global _instance
    _instance = _SHT40(sda=sda, scl=scl, freq=freq)


def cleanup():
    global _instance
    if _instance:
        _instance.cleanup()
        _instance = None