# HA 混合配置方案实施计划 Hybrid: MQTT 控件 + config.json 原子持久化

本计划在不改变现有主流程的前提下, 落地混合方案: 通过 HA 暴露少量高价值的 MQTT 控件即时生效, 仅在用戶顯式保存時將變更以原子寫入方式落盤至 config.json 覆蓋層, 並按需觸發安全重啟。優先級: 交互可用 > 最小改動 > 安全可靠。

一、目標與範圍
- 採用雙層配置: 內置默認層 app/config.py + 運行時覆蓋層 /config.json。
- 為 HA 暴露 MVP 控件: ble.enabled, ble.adv.interval_ms, mqtt.enable_log_forward, Save to flash, Safe reboot。
- 新增通用配置通道: cmnd/<device_id>/config/set|save|reboot, 狀態回執 stat/<device_id>/config。
- 原子持久化: 使用臨時文件 + rename 保證落盤安全, 失敗自動回退舊配置。

二、架構與數據流
- 啟動時: 加載 app/config.py 默認配置 -> 嘗試讀取 /config.json 覆蓋層並深度合併 -> 得到運行時配置。
- 運行態調整: HA 控件下發 set 指令 -> 設備在內存應用並回執 -> 用戶點擊 Save 才將變更寫入 /config.json。
- 需要重啟的項: 用戶顯式點擊 Safe reboot 後生效, 避免無意義重啟。

三、原子寫策略
- 使用 app/utils/json_utils.atomic_write_json 實現: 先寫 tmp 再 rename 覆蓋, 兼容 replace 回退。
- 持久化路徑: 優先使用 ble.config_service.persistence_path, 缺省為 /config.json, 僅允許白名單鍵寫入。
- 故障回退: 解析失敗時忽略覆蓋層, 以默認層啟動並上報告警。

四、MQTT 主题與權限
- 下發: cmnd/<device_id>/config/set, payload: {"path":"ble.enabled","value":true}
- 保存: cmnd/<device_id>/config/save, payload: {"paths":["ble.enabled","ble.adv.interval_ms"]}
- 重啟: cmnd/<device_id>/reboot, payload: {"delay_ms":2000}
- 回執: stat/<device_id>/config, 統一格式 {"ok":true|false,"msg":"...","applied":{...}}
- 安全: 復用 config.ble.security.auth=="token" 時要求 header 或 payload.token 匹配, 未授權拒絕並記錄。

五、HA 實體與 MVP
- switch.ble_enabled -> set path: ble.enabled。
- number.ble_adv_interval_ms -> set path: ble.adv.interval_ms, 範圍 50..2000 step 25。
- switch.mqtt_log_forward -> set path: mqtt.enable_log_forward。
- button.save_to_flash -> 發送 save。
- button.safe_reboot -> 發送 reboot。

六、代碼改動清單(最小改動)
- app/config.py: 新增覆蓋層讀寫與深度合併工具, 提供 apply_overlay(dict) 與 save_overlay(paths or subset)。
- app/utils/json_utils.py: 已有 atomic_write_json, 直接復用。
- app/net/network_manager.py: 在 MQTT 連上後訂閱配置通道, 解析 set/save/reboot, 調用 config.apply/save, 並回執。
- app/ha.py: 暫保留現有溫濕度發現; 之後補充 5 個 Discovery 實體對應 MVP 控件。
- 安全: 臨時復用 ble.security.token。後續再抽象 mqtt.security。

七、驗收標準
- /build.py -c 編譯通過。
- 啟動時無 /config.json 亦可正常運行, 有覆蓋層時能正確合併。
- HA 端調整 ble.enabled 即時生效, Save 後斷電重啟仍保持。
- set/save/reboot 全量回執, 錯誤可觀測, 未授權被拒絕。

八、風險與回滾
- 閃存磨損: 僅在 Save 時落盤, 並限制保存頻率。
- 配置損壞: 原子寫 + 失敗回退, 開機忽略壞文件。
- 安全: 默認 auth="none" 僅限開發環境; 上線切到 token 並按 topic ACL 限制寫入。

九、里程碑
- M1 覆蓋層框架: app/config.py 支持 load/apply/save, 單元驗證。
- M2 MQTT 配置通道: set/save/reboot + 回執, 白名單校驗。
- M3 HA Discovery MVP 5 個控件與交互驗證。

十、当前进展
- 代码已实现 MQTT 配置通道订阅与回调:
  - 订阅: cmnd/<device_id>/config/set, cmnd/<device_id>/config/save, cmnd/<device_id>/config/reboot, cmnd/<device_id>/reboot
  - 回调: _on_mqtt_message 中解析 JSON, 分发 set/save/reboot, 调用 apply_overlay/save_overlay, 并通过 stat/<device_id>/config 回执
  - 辅助: _json_loads, _publish_config_stat, _schedule_reboot
- 安全与权限:
  - 鉴权: 复用 ble.security.auth == "token", 验证 payload.token; auth == "none" 时免鉴权
  - 重启开关: 受 ble.config_service.allow_reboot 控制, 默认 true
- 兼容性: 复用 MqttController 的订阅恢复机制, 断线重连后自动恢复订阅
- 构建验证: python build.py -c 通过
- 依赖与改动: 未引入新依赖, 遵循最小改动

后续工作
- HA Discovery: 补充 5 个控制实体, 与配置通道联动
- 写入白名单: 限定可写路径集合, 降低误写风险
- 文档: 在 README 增补配置通道使用示例 set/save/reboot 与鉴权示例
- 可观测性: 鉴权失败与非法 payload 统一打点或上报事件总线

十一、配置指南

1) 启用鉴权与重启权限
- 在默认配置或覆盖层中设置 ble.security 与 ble.config_service
- 文件位置: <mcfile name="config.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\config.py"></mcfile>
- 推荐示例:
```
ble: {
  security: { auth: "token", token: "your-strong-token" },
  config_service: { allow_reboot: true }
}
```
- 开发期可使用 auth: "none" 免鉴权; 量产建议切换为 "token" 并通过 Broker ACL 限制写权限

2) 主题约定
- 下发: cmnd/<device_id>/config/set | cmnd/<device_id>/config/save | cmnd/<device_id>/config/reboot | cmnd/<device_id>/reboot
- 回执: stat/<device_id>/config
- device_id 由设备端发布 announce 与 availability 时保持一致

3) 命令示例
- 即时设置单项
```
Topic: cmnd/<device_id>/config/set
Payload: { "path": "ble.enabled", "value": true, "token": "your-strong-token" }
```
- 批量设置多项
```
Topic: cmnd/<device_id>/config/set
Payload: {
  "update": { "ble": { "enabled": true, "adv": { "interval_ms": 200 } } },
  "token": "your-strong-token"
}
```
- 保存变更到持久化文件
```
Topic: cmnd/<device_id>/config/save
Payload: { "paths": ["ble.enabled", "ble.adv.interval_ms"], "token": "your-strong-token" }
```
- 全量保存(省略 paths)
```
Topic: cmnd/<device_id>/config/save
Payload: { "token": "your-strong-token" }
```
- 安全重启(支持 config/reboot 与 reboot 两个主题)
```
Topic: cmnd/<device_id>/reboot
Payload: { "delay_ms": 2000, "token": "your-strong-token" }
```

4) 回执示例
- 成功
```
Topic: stat/<device_id>/config
Payload: { "ok": true, "msg": "applied", "applied": { "path": "ble.enabled", "value": true } }
```
- 未授权
```
Payload: { "ok": false, "msg": "unauthorized" }
```
- 拒绝重启
```
Payload: { "ok": false, "msg": "reboot not allowed" }
```

5) Broker ACL 建议
- 限制仅受信客户端可发布到 cmnd/<device_id>/**
- 禁止外部客户端发布到 stat/**, 避免伪造回执
- 建议使用设备级凭据或客户端证书区分写入方

6) 故障排查
- 未收到回执: 确认已订阅 stat/<device_id>/config, 检查 Broker ACL 与网络
- 授权失败: 检查 ble.security.auth 与 payload.token 是否匹配
- 重启被拒: 检查 ble.config_service.allow_reboot 是否为 true
- 保存无效: 确认 paths 列表正确或改用全量保存, 并查看设备日志

---

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