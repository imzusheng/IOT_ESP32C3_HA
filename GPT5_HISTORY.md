结论先答

- 是“设计如此”：我们前面已移除了 FSM 在 INIT/CONNECTING 的全局 60 秒超时, 避免与 NetworkManager 的退避/超时冲突；因此仅仅因为 MQTT 连接失败(间歇重试)并不会自动进入 ERROR 模式。
- 是否应该进入 ERROR：取决于你的策略。如果 ERROR 意味着“系统需要停下/等待人工/或重启”, 那在可恢复的网络波动下频繁进入 ERROR 反而不利；如果你希望“连续失败达到一定阈值后进入 ERROR 并做更强提示或重启”, 我们可以增加条件阈值。
- 你提出“如果不能进入 ERROR 至少 LED 进入 SOS 闪烁”：我已经实现了这一点, 保证在连接阶段出现 WiFi/MQTT 断开事件时, LED 将切换为 SOS。编译已通过。
当前行为说明

- FSM 不再施加全局 60 秒网络超时；NetworkManager 内部的 WiFi/MQTT 各自 10 秒连接超时 + 退避负责节奏。
- 在 INIT/CONNECTING 阶段, 如果收到网络断开事件(来自 NetworkManager 的 EVENTS["WIFI_STATE_CHANGE"]/EVENTS["MQTT_STATE_CHANGE"], state="disconnected"), 我新增了“只变更 LED 提示”的轻量逻辑：
  - 不改变状态机当前状态(维持 INIT/CONNECTING), 保证不会干扰网络模块自身的重试节奏；
  - 立即 set_led_mode('sos'), 实现你希望的“至少 LED 进入 SOS 闪烁(预设)”；
  - 一旦连接成功, 已有的状态迁移会触发 _update_led, 恢复为对应模式(如 RUNNING -> 'cruise')。
这样做的好处

- 最小改动, 不改变既定的“由 NetworkManager 统一退避/重试”的策略；
- 避免频繁切换到 ERROR 模式导致系统“自我中断”；
- 在用户体验上提供了明确的“连接受阻”的视觉反馈(SOS), 满足你的期望。
如果你更倾向进入 ERROR 的两个可选策略

- 连续失败阈值进入 ERROR(推荐)
  - 例如“在 INIT/CONNECTING 阶段, 连续 N 次(如 3 次)MQTT 连接失败, 进入 ERROR”, 并保留 ERROR 10 秒后回 INIT 的逻辑。
  - 优点：可恢复问题不至于立刻 ERROR, 真正持续异常时才进入 ERROR, 有明确指示并可触发自动恢复。
- 固定窗口失败率进入 ERROR(复杂度略高)
  - 在 T 秒窗口内失败次数超过阈值再进入 ERROR, 更平滑但实现稍复杂。
已完成的代码改动(简述)

- 在 app/fsm/core.py：
  - 当处于 INIT 或 CONNECTING 时, 若收到 WiFi/MQTT 的 state='disconnected' 事件, 不改变状态, 只调用 set_led_mode('sos'), 让 LED 进入 SOS 模式；连接成功后恢复原有 LED 模式映射。
- 在 app/net/mqtt.py：
  - 修复了 AttributeError(误用 self.mqtt_client 等), 统一复用 init 中的 self.client, 保持 10 秒 socket 超时, 日志统一为 module="MQTT"。
编译状态

- 已执行 python .\build.py -c, 编译通过。
请你验证

- 观察 run.log, 当 MQTT 失败(例如 ECONNABORTED/ETIMEDOUT)时, LED 是否切换到 SOS 闪烁；
- 一旦连接成功, LED 是否恢复为 cruise(RUNNING)；
- 确认不再出现 'MqttController' object has no attribute 'mqtt_client'；
需要你拍板的选择

- 是否要增加“连续失败阈值进入 ERROR”的策略？例如：在 CONNECTING 阶段, 连续 3 次 MQTT 失败进入 ERROR(10 秒后 FSM 自动回到 INIT 重试)。如果你同意, 我会以最小改动补上该计数逻辑, 并复用现有 ERROR->INIT 的回路