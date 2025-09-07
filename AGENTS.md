# Repository Guidelines

## 项目结构与模块组织

- `app/` — 源码根目录：`net/`(Wi‑Fi、MQTT、NTP)、`hw/`(传感器、LED)、`utils/`(计时与 JSON 工具)、`lib/`(日志、异步、事件总线)；入口为 `boot.py` 与 `main.py`。
- `docs/` — 文档与修复记录(如 `docs/mqtt_subscription_fix/`)。
- `dist/` — 构建产物目录,由构建脚本生成并上传到设备根目录 `/`。
- `app/tests/` — 设备侧测试(可选,使用 `-t` 构建时包含)。
- 根目录工具：`build.py`(主构建/部署)、`buildc.py`(历史脚本)、`README.md`。

## 构建、测试与开发命令

- `python build.py` — 编译 `app/` 至 `dist/` 并智能同步到 ESP32‑C3。
- `python build.py -cu` — 明确编译并上传,适合重复/CI 场景。
- `python build.py -C` — 仅清空设备文件。
- `python build.py -m` — 监控设备 REPL 输出。
- `python build.py -d` — 连接与内存诊断。
- `python build.py -p COM3` — 指定串口。
- 运行测试：先 `python build.py -tcu -p COM3`,再 `mpremote connect COM3 run :/tests/<test_file>.py`。

## 编码风格与命名规范

- MicroPython 兼容,UTF‑8,4 空格缩进。
- 命名：模块/函数用 `snake_case`,类用 `PascalCase`,常量用 `UPPER_SNAKE`。
- 保持非阻塞：优先使用 `uasyncio`、硬件/软件定时器与事件总线(见 `lib/event_bus_lock.py`)。
- 日志统一走 `lib/logger.py`(如 `info/debug/error(module="...")`)。
- 网络放 `app/net/`,硬件放 `app/hw/`,通用放 `app/utils/`。

## 测试指南

- 测试文件置于 `app/tests/`,命名 `test_*.py`。
- 测试需小而稳(内存友好、硬件可用时才依赖硬件),能模拟则模拟。
- 上传后用 `mpremote` 在设备上运行并观察输出。

## 提交与合并请求

- 建议采用 Conventional Commits：`feat:`、`fix:`、`refactor:`、`docs:`、`test:`、`chore:`。
- 使用域作范围：如 `feat(net): cap reconnect backoff`。
- PR 请包含：变更目的/摘要、关键改动、测试说明(含 mpremote/控制台输出)、相关截图或日志(如 `run.log`),并关联问题单。

## 安全与配置提示

- 不要提交任何密钥/口令。默认值在 `app/config.py`；运行时覆盖保存在设备 `:/config.json`(overlay)。
- 推荐以覆盖方式下发：`mpremote connect COM3 fs put config.json :/config.json`,避免修改版本库中的凭据。
- 现场部署前台架验证 Wi‑Fi/MQTT；结合 `-d` 与 `-m` 检视行为。

## Home Assistant 集成(`app/ha.py`)

- 作用：封装 MQTT Discovery、可用性与状态上报,以及只读诊断实体发布。
- 主题约定：
  - 可用性 `device/<id>/availability`
  - 状态 `device/<id>/state/<sub>`(如 `temperature`、`humidity`、`metrics`、`config_snapshot`)
  - 命令 `cmnd/<id>/<sub>`(按钮/选择器等)
  - 发现前缀取自 `config.ha.discovery_prefix`(如 `homeassistant`)。
- 主要配置字段(`config.ha.*`)：`device_name`、`manufacturer`、`model`、`sw_version`、`temp_name`、`hum_name`、`buttons`(默认仅允许 `reboot` 按钮)。若 `ble.security.auth == "token"`,将把 `token` 加入按钮 `payload_press`。
- 常用调用：
  - 创建：`ha = HomeAssistantHelper(cfg, get_device_id, mqtt_publish)`
  - 发现与可用性：`ha.publish_discovery(); ha.publish_availability(True)`
  - 状态：`ha.publish_state(temperature=..., humidity=..., retain=True)`；诊断：`ha.publish_metrics({...})`
  - 配置快照：自动发布到 `state/config_snapshot` 并通过 Discovery 暴露为诊断实体。

## 编码与终端规则(防止中文乱码)

为避免中文在 Windows/PowerShell 环境下出现“状 �?/超 �?”等乱码,开发与自动化工具需统一以下约定：

1. 文件与仓库

- 源码与文档一律使用 UTF-8(无 BOM)。
- 行尾统一为 LF(\n),避免 CRLF 转换导致差异与乱码。
- Python 文件首行建议保留编码声明：`# -*- coding: utf-8 -*-`(兼容部分工具)。
- Git 建议：
  - `git config core.autocrlf input`
  - `git config i18n.commitEncoding utf-8`
  - `git config i18n.logOutputEncoding utf-8`

2. PowerShell/终端输出

- 使用 UTF-8 代码页与输出编码：
  - 在当前会话运行：
    - `chcp 65001`(切换为 UTF-8 代码页)
    - `$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)`
  - 读取文件时显式声明编码：
    - `Get-Content -Encoding UTF8 -Raw app/xxx.py`
- ripgrep/grep 指定编码：`rg -n --encoding utf-8 PATTERN`。
- 避免用不带编码参数的 shell 过滤/重定向修改文件；统一通过 `apply_patch` 修改文件。

3. 编辑器与保存

- 编辑器文件编码固定为 UTF-8(无 BOM),行尾 LF。
- 若需统一,可添加 `.editorconfig`(不强制提交)：
  - `charset = utf-8`
  - `end_of_line = lf`
  - `insert_final_newline = true`

4. 程序内与 JSON

- JSON 序列化统一使用 `utils.json_utils.json_dumps`(确保 `ensure_ascii=False`),避免把中文转义为 `\uXXXX`。
- MQTT/HA 主题键名尽量使用 ASCII；实体名称/文本内容可用中文。

5. 常见问题与应对

- 终端显示“状 �?/超 �?”：多因代码页/输出编码不为 UTF-8；按 2) 的步骤切换到 UTF-8。
- 文件内已有乱码：多数为历史以非 UTF-8 保存或经工具转码产生；后续改动按照 1)–3) 规范保存为 UTF-8,并逐步清理。
- PowerShell 正则/转义报错：优先用单引号包裹正则/字符串,或使用 `-Raw` 读取再在内存中处理,避免双层转义。

以上规范适用于：源代码、构建脚本、HA 发现配置与任意带中文注释/字符串的文件。

## ASCII 标点约束(避免全角符号)

- 统一使用英文半角标点：() [] {} <> ' " , . : ; ! ? - \_ 等。
- 严禁在源码与文档中使用中文全角标点：()【】《》“”‘’,。；：？！—— 等。
- 变量名、键名、主题名、路径名一律使用 ASCII；仅显示给用户的名称/文本可为中文,但标点仍使用 ASCII。
- 快速检查(UTF-8 环境下执行)：
  - `rg -n --encoding utf-8 "[(),。；：？！【】《》“”‘’——]"`
  - Windows PowerShell 建议先执行 `chcp 65001`,并将 `$OutputEncoding` 设为 UTF-8(见上节)。
- 约束理由：
  - 避免因不同输入法/编辑器导致的不可见差异与难以定位的比较问题。
  - 保证 MQTT 主题、文件名、代码审阅与正则匹配的可移植性与可读性。

