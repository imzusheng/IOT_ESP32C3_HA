# BLE 设置与 OTA 方案实施计划（优先完成：BLE 设置）

本文档阐述在当前项目中引入“蓝牙设置（在 app/config.py 中可配置）”的完整思路与落地步骤，并给出可执行的 TodoList。目标是：不改动现有主流程的同时，为 BLE 行为提供统一、可持久化、可在线（Web Bluetooth）调整的配置入口，并为后续 OTA 与更多服务扩展打基础。

---

一、目标与范围
- 在配置模块中新增 BLE 配置段，统一控制：开关、名称、广播间隔、是否启用 HID、标准服务开关（Battery、Device Info、Environmental Sensing）与自定义服务（UART/配置服务、OTA）。
- 将“电量模拟”纳入配置：是否启用、初始值/步长/周期、定时器策略（硬件/软件）、定时器编号（避免号冲突）。
- 预留安全策略（本地配置写入鉴权：固定 token/PIN），为后续通过 H5 页面修改设置做准备。
- 不在本阶段变更主循环与 EventBus 架构，保持低风险增量集成。

---

二、配置结构设计（app/config.py 新增建议）
为减少侵入性，采用与现有 CONFIG 结构一致的风格。建议新增 ble 段：

- ble.enabled: 是否启用 BLE（默认 True）
- ble.use_hid: 是否使用 HID 模式（默认 False，以兼容 Web Bluetooth）
- ble.device_name: GAP 名称（默认 "ESP32-C3"）
- ble.adv.interval_ms: 广播间隔（默认 150ms）
- ble.services: 标准与自定义服务的开关
  - battery: True/False（电池服务与通知）
  - device_info: True/False（设备信息）
  - env_sensing: True/False（温湿度等）
  - uart: True/False（自定义 UART/配置通道）
  - ota: True/False（OTA 服务占位，后续实现）
- ble.security: 配置写入的鉴权策略
  - auth: "none" | "token"（默认 none，开发期；后续建议切到 token）
  - token: "changeme"（仅示例，生产不入库/不硬编码）
  - allowlist: []（可选：允许的中心设备地址列表）
- ble.simulation.battery: 电量模拟参数
  - enabled: True/False（默认 True）
  - start: 初始电量（默认 100）
  - step: 每次变化步长（默认 -1）
  - min: 触底回卷阈值（默认 0）
  - period_ms: 触发周期（默认 10000）
  - strategy: "hardware" | "software"（默认 hardware）
  - timer_id: 0（默认 0，结合设备兼容性可调）
- ble.config_service: 配置服务开关与持久化位置
  - enabled: True/False（默认 True）
  - persistence_path: "/config.json"（JSON 持久化文件）
  - allow_reboot: True（允许命令触发安全重启）

备注：
- 所有敏感字段（如 token）仅示例，生产请通过安全渠道下发或一次性临时 PIN，避免硬编码。
- /config.json 作为运行时“覆写层”，与 app/config.py 的“默认层”叠加，优先级：运行时文件 > 内置默认。

---

三、BLE 管理器消费配置的接口契约（后续实现）
- 从配置读取：名称、模式（HID/基础）、广播参数、服务开关。
- 根据开关注册服务并持有各特征句柄；根据 simulation.battery 启停电量模拟并应用定时器策略。
- 通过统一方法支持运行时调整：
  - apply_settings(partial_config): 动态应用 BLE 相关配置（名称、广播、模拟参数等）。
  - persist_settings(): 将修改后的配置以 JSON 写入 persistence_path，原子落盘（临时文件 + rename）。
- 预留与 EventBus 的对接接口（非本阶段硬依赖），便于后续跨模块解耦。

---

四、Web Bluetooth 配置通道（设计先行，后做实现）
- 采用 UART/NUS 风格的 1 写 1 通知自定义服务，用 JSON Line 协议交互：
  - GET {"path":"ble"}
  - SET {"path":"ble.simulation.battery","value":{"enabled":true,"period_ms":5000}}
  - SAVE {}
  - REBOOT {}
- 安全：若 ble.security.auth=="token"，客户端需先发送 AUTH {"token":"..."} 成功后才允许 SET/SAVE/REBOOT。

---

五、OTA 简要设计（本阶段仅预留配置与服务开关）
- 自定义 OTA 服务：BEGIN/DATA/END/COMMIT/ABORT 分片传输与校验；支持 .py/.mpy 应用级 OTA，严格限制可写路径。
- 失败回滚：下载到临时区，校验通过后再替换；保留上一个版本以便回退。

---

六、安全与可靠性
- 鉴权：默认开发期放开，量产建议启用 token/PIN；对敏感指令（SAVE/REBOOT/OTA）进行二次确认或冷却时间。
- 资源：控制广播与通知频率，避免长时间大数据量导致内存压力。
- 定时器：timer_id 可配；必要时降级为软件定时器以避免硬件冲突。
- 持久化：原子写入（tmp -> rename），失败回滚，不破坏默认配置。

---

七、里程碑与验收
- M1：在 app/config.py 增加 ble 配置段；蓝牙测试脚本能从配置读取名称/广播/模拟参数并生效。
- M2：实现配置服务（GET/SET），可通过 H5 页面读写 ble.*（不含 SAVE）。
- M3：实现 SAVE 与原子持久化；断电重启后配置保持。
- M4：H5 UI 完成参数表单与交互验证；安全策略接入。
- M5：OTA 服务最小版本与防误操作机制。

---

八、TodoList（分解到文件与动作）
1) 配置层
- 在 app/config.py 中新增 ble 段（字段见上文）；默认 use_hid=False，simulation.battery.enabled=True。
- 在 app/utils/json_utils.py 增加原子写工具（若已有则复用）。

2) BLE 管理器与现有脚本
- 抽象 app/hw/ble.py：封装注册服务、广播、模拟电量、通知等；从配置读入并应用。
- 在 bluetooth_test_working.py 增加从配置读取与覆盖逻辑（作为过渡验证）。

3) 配置服务（UART/NUS）
- 定义自定义 GATT：RX(Write/WriteNR)、TX(Notify)。
- 实现命令解析：AUTH/GET/SET/SAVE/REBOOT；应用到 BLE 管理器。
- 接入安全策略（token）与基础防抖（限频/冷却）。

4) 持久化
- 叠加配置层：/config.json（运行时层）+ app/config.py（默认层）。
- SAVE：临时文件写入 -> 校验 -> rename 原子替换。

5) 前端 H5（ble.html）
- 增加“配置”面板：展示/编辑 ble.* 关键参数；发送 GET/SET/SAVE；显示鉴权状态与错误。

6) 验收与回归
- Web Bluetooth + REPL 双通道验证：连接、读写、重启、断电恢复。
- 连接多个中心设备的行为验证；Timer 号冲突回退验证。

---

九、后续扩展（非当前里程碑）
- MQTT/HA 桥接 BLE 事件与指标；
- Environmental Sensing 与 Device Info 标准化填充；
- OTA 细化与差分/签名校验；
- HID 模式切换的安全与兼容策略。

---

文件关联
- 配置文件：app/config.py（新增 ble 段）
- BLE 管理器：app/hw/ble.py（新增）
- 测试/演示：bluetooth_test_working.py（临时读取配置验证）
- 前端：ble.html（新增“配置”面板与指令）
- 工具：app/utils/json_utils.py（原子写）