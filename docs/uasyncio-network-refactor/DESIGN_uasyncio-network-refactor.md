# DESIGN_uasyncio-network-refactor

目标: 以 uasyncio 为核心, 将 WiFi,NTP,MQTT 的同步编排迁移为协程化任务, 保持与 FSM 与 EventBus 的解耦, 不保留旧同步逻辑与注释。

## 架构概览
```mermaid
graph TD
  A[MainController] --> B[AsyncRuntime]
  B --> C[AsyncEventLoop(uasyncio)]
  C --> D[Task: WiFiScan]
  C --> E[Task: WiFiConnect]
  C --> F[Task: NTP]
  C --> G[Task: MQTTConnect]
  C --> H[Task: MQTTKeepalive]
  C --> I[Task: MQTTCheckMsg]
  C --> J[Task: FSMUpdate]
  C --> K[Task: LEDUpdate]
  C --> L[Task: Watchdog]
  B --> M[EventBus Adapter]
  M <--> N[FSM]
  M <--> O[NetworkManager(AsyncFacade)]
```

- AsyncRuntime: 提供启动, 停止与任务注册接口, 持有 uasyncio loop。
- NetworkManager(AsyncFacade): 提供异步的 connect_wifi(), connect_mqtt(), sync_ntp() 协程方法与 start() 注册任务方法, 对外保留原有状态查询接口。
- EventBus Adapter: 以非阻塞方式周期性 flush 事件队列, 或使用异步队列适配。

## 模块职责与接口
- MainController
  - 新增 run_async() 入口, 改为协程主循环, 删除同步 run 的网络驱动逻辑。
- NetworkManager
  - 新增异步方法
    - async scan_wifi()
    - async connect_wifi()
    - async connect_mqtt()
    - async sync_ntp()
  - 新增 start_tasks() 注册内部任务, 包含 WiFi,NTP,MQTT 的周期性任务。
  - 保留 get_status(), force_reconnect()。
- MQTT 层
  - 在现有 umqtt 上增加协作式封装, 将 connect() 分解为若干短超时步骤, 每步之间 await asyncio.sleep_ms(0~50) 让出执行权。
  - 保持 check_msg() 非阻塞, 独立周期任务驱动。
- FSM
  - 保持同步 API, 通过 Task:J(FSMUpdate) 定期调用 update(), feed_watchdog()。

## 协程任务清单与频率建议
- WiFiScan: 冷启动触发一次, 失败退避 5s~30s 指数回退。
- WiFiConnect: 以 100ms 切片推进连接状态, 总超时 60s 可配置。
- NTP: 成功连接 WiFi 后触发一次, 失败快速返回, 30min 周期重试。
- MQTTConnect: 以 100~200ms 切片推进, 单步 socket 超时 500~1000ms, 总超时与退避由配置控制。
- MQTTKeepalive: 每 keepalive/2 发送 ping, 使用短超时等待 PINGRESP。
- MQTTCheckMsg: 每 50~100ms 调用 check_msg()。
- FSMUpdate: 每 50~100ms。
- LEDUpdate: 每 50~100ms。
- Watchdog: 每 100~200ms。

## 数据契约与接口变化
- 新增配置项
  - network.async.intervals: {wifi_connect_slice_ms, mqtt_connect_slice_ms, check_msg_ms, keepalive_ms}
  - network.async.backoff: {wifi, mqtt} 初始/最大/倍数
- NetworkManager.loop()
  - 删除同步驱动, 迁移为异步任务注册。
- 事件总线
  - 保持现有同步发布/订阅接口, 通过 Adapter 在协程中定期 process_events()。

## 渐进式迁移路径
- 阶段 A: 框架搭建
  1) 新增 AsyncRuntime 与 run_async()。
  2) 添加 EventBus Adapter 与 FSMUpdate, LEDUpdate, Watchdog 三个基础任务。
  3) /build.py -c 通过。
- 阶段 B: WiFi 协程化
  1) 将扫描与连接改为可重入协程, 连接切片推进与短超时。
  2) 加入指数退避策略与最大重试。
  3) /build.py -c 通过。
- 阶段 C: MQTT 协程化
  1) 对 umqtt connect() 做协作式封装, 分步 DNS, socket 连接, CONNECT/CONNACK 等待。
  2) 建立 MQTTConnect 与 MQTTKeepalive 与 MQTTCheckMsg 任务。
  3) /build.py -c 通过。
- 阶段 D: 清理与收敛
  1) 删除同步路径与相关注释。
  2) 完善参数与日志。
  3) /build.py -c 通过。

## 关键实现要点
- 小步推进
  - 任何可能阻塞的网络 IO 都需设置短超时并在失败后 yield, 将重试交给上层退避。
- 超时与取消
  - 使用软超时计数与任务取消, 确保卡死时可回收。
- 可观测性
  - 为每个任务增加开始, 成功, 失败, 取消与退避日志, 统一 module 标识。

## 测试与验证
- 正常路径
  - 冷启动至 MQTT 连接成功时序正确, 日志无异常。
- 异常路径
  - WiFi 不可达, 观察任务退避与 LED 不中断。
  - MQTT Broker 不可达, 指数退避生效, 主任务不阻塞。
- 回归
  - /build.py -c 通过, 关键功能不回退。