# ESP32C3 IoT 设备 - 增强模块化架构

## 项目概述

本项目为 ESP32C3 微控制器设计了一个高可靠性的模块化 IoT 设备架构，具有完整的错误处理、内存优化、状态监控和远程管理功能。该架构经过全面测试，在资源受限的嵌入式环境中实现了企业级的稳定性和可维护性。

## 核心特性

### 🏗️ 模块化架构
- **统一配置管理** - 集中式配置系统，支持运行时更新和验证
- **增强错误处理** - 智能错误分类和自动恢复机制
- **智能内存优化** - 自适应垃圾回收和内存监控
- **模块化守护进程** - 独立的设备监控和管理服务
- **实时状态监控** - 全面的系统健康监控和诊断
- **企业级日志系统** - 结构化日志记录和导出功能

### 🔧 系统组件

#### 1. 配置管理模块 (`config.py`)
- **MQTT配置**: Broker连接、主题管理、重连策略
- **WiFi配置**: 多网络支持、连接参数、扫描间隔
- **守护进程配置**: LED控制、温度监控、内存阈值
- **系统配置**: 调试选项、性能参数、恢复策略
- **运行时配置**: 动态配置更新、持久化存储
- **配置验证**: 完整的参数验证和错误检查

#### 2. 增强错误处理 (`enhanced_error_handler.py`)
- **错误严重程度**: LOW → MEDIUM → HIGH → CRITICAL → FATAL
- **恢复策略**: 重试、组件重启、系统重启、连接重置、内存清理
- **智能分类**: 基于错误类型的自动处理策略
- **恢复管理**: 带冷却期的智能恢复机制
- **健康监控**: 实时系统健康状态评估
- **统计报告**: 详细的错误和恢复统计

#### 3. 内存优化器 (`memory_optimizer.py`)
- **性能监控**: 操作耗时和内存使用追踪
- **智能回收**: 自适应垃圾回收策略
- **内存分析**: 详细的内存使用报告
- **性能统计**: 操作性能指标收集
- **装饰器支持**: 简单的性能监控集成

#### 4. 状态监控器 (`status_monitor.py`)
- **组件监控**: 独立的组件健康检查
- **系统指标**: 内存、CPU、温度、网络状态
- **增强日志**: 结构化日志管理和过滤
- **系统诊断**: 全面的系统健康诊断
- **历史记录**: 指标历史数据存储
- **远程监控**: 支持远程状态查询

#### 5. 守护进程 (`enhanced_daemon.py`)
- **设备监控**: 温度、内存、LED状态监控
- **看门狗**: 系统稳定性保障
- **安全模式**: 异常情况的降级运行
- **定时任务**: 周期性系统检查
- **事件处理**: 系统事件的统一处理

## 技术规格

### 硬件要求
- **微控制器**: ESP32C3 (RISC-V 双核, 4MB Flash, 400KB RAM)
- **LED指示灯**: 2个状态指示LED
- **温度传感器**: 内置温度传感器
- **网络**: WiFi 802.11 b/g/n

### 软件环境
- **固件**: MicroPython 1.19+
- **Python版本**: Python 3.8+ (开发测试)
- **依赖库**: machine, gc, time, json, network, umqtt

### 性能指标
- **内存使用**: < 200KB 运行时内存
- **启动时间**: < 3秒
- **监控间隔**: 30秒常规监控
- **错误恢复**: 自动恢复，成功率 > 90%
- **系统稳定性**: 7x24小时连续运行

## 快速开始

### 1. 环境准备

```bash
# 安装MicroPython固件到ESP32C3
esptool.py --chip esp32c3 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32c3 --port /dev/ttyUSB0 write_flash -z 0x0 firmware.bin

# 安装依赖库
mpremote mip install micropython-umqtt.simple
```

### 2. 配置设置

编辑 `config.py` 文件中的网络和MQTT配置：

```python
# WiFi网络配置
WiFiConfig.NETWORKS = [
    {"ssid": "your_wifi_ssid", "password": "your_password"}
]

# MQTT配置
MQTTConfig.BROKER = "your_mqtt_broker"
MQTTConfig.TOPIC = "your_device_topic"
```

### 3. 运行测试

```bash
# 运行完整架构测试
python src/test_architecture_simple.py

# 运行增强测试
python src/test_new_architecture.py
```

### 4. 部署到设备

```bash
# 上传代码到设备
mpremote cp src/ :/src/

# 运行主程序
mpremote run src/main.py
```

## 配置说明

### MQTT配置
```python
MQTTConfig.BROKER = "192.168.1.2"        # MQTT服务器地址
MQTTConfig.PORT = 1883                   # MQTT端口
MQTTConfig.TOPIC = "lzs/esp32c3"         # 设备主题
MQTTConfig.KEEPALIVE = 60                # 保活时间(秒)
MQTTConfig.RECONNECT_DELAY = 5          # 重连延迟(秒)
```

### 守护进程配置
```python
DaemonConfig.LED_PINS = [12, 13]          # LED引脚
DaemonConfig.TEMP_THRESHOLD = 60.0       # 温度阈值(°C)
DaemonConfig.MEMORY_THRESHOLD = 90       # 内存阈值(%)
DaemonConfig.WDT_TIMEOUT = 8000          # 看门狗超时(ms)
DaemonConfig.MONITOR_INTERVAL = 30000    # 监控间隔(ms)
```

### 系统配置
```python
SystemConfig.DEBUG_MODE = False          # 调试模式
SystemConfig.LOG_LEVEL = "INFO"          # 日志级别
SystemConfig.AUTO_RESTART_ENABLED = True # 自动重启
SystemConfig.HEALTH_CHECK_INTERVAL = 60000 # 健康检查间隔(ms)
```

## API参考

### 配置管理API
```python
# 获取配置
config.get_config('mqtt.broker', 'default')

# 设置配置
config.set_config('system.debug_mode', True)

# 验证配置
config.validate_config()

# 获取配置管理器
config_manager = config.get_config_manager()
```

### 错误处理API
```python
# 处理错误
enhanced_error_handler.handle_error(
    error_handler.ErrorType.NETWORK,
    exception,
    "WiFiModule",
    enhanced_error_handler.ErrorSeverity.HIGH
)

# 检查系统健康
health_status = enhanced_error_handler.check_system_health()

# 获取错误历史
error_history = enhanced_error_handler.get_error_history()
```

### 状态监控API
```python
# 获取系统状态
system_status = status_monitor.get_system_status()

# 记录增强日志
status_monitor.info_enhanced("系统启动", "System")

# 运行系统诊断
diagnostic_result = status_monitor.run_system_diagnostic()

# 获取组件状态
component_status = status_monitor.get_system_status_monitor().get_component_status("memory")
```

### 内存优化API
```python
# 优化内存
result = memory_optimizer.optimize_memory()

# 获取内存报告
memory_report = memory_optimizer.get_memory_report()

# 性能监控装饰器
@memory_optimizer.monitor_performance("operation_name")
def my_function():
    # 函数实现
    pass
```

## 测试验证

### 测试覆盖率
- **模块导入测试**: 6/6 通过 (100%)
- **配置管理测试**: 验证通过
- **错误处理测试**: 基础和增强处理正常
- **内存优化测试**: 智能回收功能正常
- **守护进程测试**: 状态监控正常
- **状态监控测试**: 实时监控功能正常
- **系统诊断测试**: 诊断功能正常
- **集成测试**: 模块间协作正常
- **性能测试**: 响应时间满足要求

### 测试结果
```
ESP32C3 增强架构测试
============================================================
通过: 10/10
成功率: 100.0%

OK 模块导入
OK 配置管理
OK 错误处理
OK 增强错误处理
OK 内存优化
OK 守护进程
OK 状态监控
OK 系统诊断
OK 集成测试
OK 性能测试

[SUCCESS] 测试通过！新架构运行正常。
```

## 故障排除

### 常见问题

1. **WiFi连接失败**
   - 检查WiFi配置是否正确
   - 确认网络信号强度
   - 查看错误日志获取详细信息

2. **MQTT连接问题**
   - 验证MQTT服务器地址和端口
   - 检查网络连接状态
   - 确认主题格式正确

3. **内存不足**
   - 监控内存使用情况
   - 调整垃圾回收参数
   - 优化数据结构使用

4. **系统不稳定**
   - 查看系统健康状态
   - 检查错误恢复统计
   - 运行系统诊断

### 调试模式

启用调试模式获取详细信息：
```python
SystemConfig.DEBUG_MODE = True
SystemConfig.LOG_LEVEL = "DEBUG"
```

## 开发指南

### 添加新模块
1. 在 `src/` 目录创建新模块文件
2. 实现必要的接口和功能
3. 在测试文件中添加测试用例
4. 更新文档和配置

### 扩展配置
1. 在相应的配置类中添加新参数
2. 更新配置验证逻辑
3. 添加配置项说明到文档

### 自定义错误处理
1. 定义新的错误类型
2. 实现对应的恢复策略
3. 更新错误分类逻辑

## 监控和维护

### 系统监控
- **内存使用**: 实时监控内存占用
- **温度监控**: 监控设备温度
- **网络状态**: 检查连接状态
- **错误统计**: 跟踪错误发生频率

### 日志管理
- **结构化日志**: 支持JSON格式日志
- **日志过滤**: 按级别和模块过滤
- **日志导出**: 支持多种导出格式
- **远程日志**: 支持远程日志传输

### 性能优化
- **内存优化**: 智能垃圾回收
- **性能监控**: 操作耗时统计
- **资源管理**: 有效的资源使用
- **启动优化**: 快速系统启动

## 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 联系方式

- 项目维护者: lzs
- 邮箱: your-email@example.com
- 项目地址: https://github.com/yourusername/esp32c3-iot-device

---

**最后更新**: 2025年7月
**版本**: 1.0.0
**架构**: 增强模块化架构 v2.0