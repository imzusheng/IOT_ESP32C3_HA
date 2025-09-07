# Repository Guidelines

## 项目结构与模块组织
- `app/` — 源码根目录：`net/`（Wi‑Fi、MQTT、NTP）、`hw/`（传感器、LED）、`utils/`（计时与JSON工具）、`lib/`（日志、异步、事件总线）；入口为 `boot.py` 与 `main.py`。
- `docs/` — 文档与修复记录（如 `docs/mqtt_subscription_fix/`）。
- `dist/` — 构建产物目录，由构建脚本生成并上传到设备根目录 `/`。
- `app/tests/` — 设备侧测试（可选，使用 `-t` 构建时包含）。
- 根目录工具：`build.py`（主构建/部署）、`buildc.py`（历史脚本）、`README.md`。

## 构建、测试与开发命令
- `python build.py` — 编译 `app/` 至 `dist/` 并智能同步到 ESP32‑C3。
- `python build.py -cu` — 明确编译并上传，适合重复/CI 场景。
- `python build.py -C` — 仅清空设备文件。
- `python build.py -m` — 监控设备 REPL 输出。
- `python build.py -d` — 连接与内存诊断。
- `python build.py -p COM3` — 指定串口。
- 运行测试：先 `python build.py -tcu -p COM3`，再 `mpremote connect COM3 run :/tests/<test_file>.py`。

## 编码风格与命名规范
- MicroPython 兼容，UTF‑8，4 空格缩进。
- 命名：模块/函数用 `snake_case`，类用 `PascalCase`，常量用 `UPPER_SNAKE`。
- 保持非阻塞：优先使用 `uasyncio`、硬件/软件定时器与事件总线（见 `lib/event_bus_lock.py`）。
- 日志统一走 `lib/logger.py`（如 `info/debug/error(module="...")`）。
- 网络放 `app/net/`，硬件放 `app/hw/`，通用放 `app/utils/`。

## 测试指南
- 测试文件置于 `app/tests/`，命名 `test_*.py`。
- 测试需小而稳（内存友好、硬件可用时才依赖硬件），能模拟则模拟。
- 上传后用 `mpremote` 在设备上运行并观察输出。

## 提交与合并请求
- 建议采用 Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`、`chore:`。
- 使用域作范围：如 `feat(net): cap reconnect backoff`。
- PR 请包含：变更目的/摘要、关键改动、测试说明（含 mpremote/控制台输出）、相关截图或日志（如 `run.log`），并关联问题单。

## 安全与配置提示
- 不要提交任何密钥/口令。默认值在 `app/config.py`；运行时覆盖保存在设备 `:/config.json`（overlay）。
- 推荐以覆盖方式下发：`mpremote connect COM3 fs put config.json :/config.json`，避免修改版本库中的凭据。
- 现场部署前台架验证 Wi‑Fi/MQTT；结合 `-d` 与 `-m` 检视行为。

## Home Assistant 集成（`app/ha.py`）
- 作用：封装 MQTT Discovery、可用性与状态上报，以及只读诊断实体发布。
- 主题约定：
  - 可用性 `device/<id>/availability`
  - 状态 `device/<id>/state/<sub>`（如 `temperature`、`humidity`、`metrics`、`config_snapshot`）
  - 命令 `cmnd/<id>/<sub>`（按钮/选择器等）
  - 发现前缀取自 `config.ha.discovery_prefix`（如 `homeassistant`）。
- 主要配置字段（`config.ha.*`）：`device_name`、`manufacturer`、`model`、`sw_version`、`temp_name`、`hum_name`、`buttons`（默认仅允许 `reboot` 按钮）。若 `ble.security.auth == "token"`，将把 `token` 加入按钮 `payload_press`。
- 常用调用：
  - 创建：`ha = HomeAssistantHelper(cfg, get_device_id, mqtt_publish)`
  - 发现与可用性：`ha.publish_discovery(); ha.publish_availability(True)`
  - 状态：`ha.publish_state(temperature=..., humidity=..., retain=True)`；诊断：`ha.publish_metrics({...})`
  - 配置快照：自动发布到 `state/config_snapshot` 并通过 Discovery 暴露为诊断实体。
