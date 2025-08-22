


          
以下为项目当前架构概要及基于硬件定时器的守护程序设计分析。

## 1. 现有核心架构
1. 事件总线 EventBus：模块间通信枢纽，位于 <mcfile name="event_bus.py" path="app/lib/lock/event_bus.py"></mcfile>。
2. 主循环 MainController：在 <mcfile name="main.py" path="app/main.py"></mcfile> 中以 50 ms 软定时周期调度 FSM、网络循环、喂看门狗并做周期维护。
3. 状态机 FSM：负责系统状态演进与容错策略，文件 <mcfile name="core.py" path="app/fsm/core.py"></mcfile>，当前不再集成温度监控(已移除 SHT40 相关逻辑)。
4. 看门狗 Watchdog：在 FSM 启动阶段 _init_watchdog 方法中通过 machine.WDT 初始化 <mcsymbol name="_init_watchdog" filename="core.py" path="app/fsm/core.py" startline="76" type="function"></mcsymbol>。
5. 配置中心：<mcfile name="config.py" path="app/config.py"></mcfile> 提供 main_loop_delay、wdt_timeout 等可调参数。

### 温度监控调整
- 已移除 FSM 内的 `_check_temperature()` 及其基于 SHT40 的环境温度保护逻辑。
- 若需过热保护，应基于 MCU 温度 的硬件定时器守护实现；SHT40 仅用于环境数据采集/统计与上报(非保护路径)。

## 2. 守护程序设计目标
1. **最高优先级**：独立于主循环运行，使用硬件定时器确保定期执行。
2. **不被阻塞**：Timer 回调应极简、短执行，避免阻塞中断上下文。
3. **温度阈值检测**：采用 esp32.mcu_temperature()(无需 I2C)直接读取 MCU 温度，减少外设依赖。
4. **与看门狗协作**：
   - 定时器回调在检测到过热后设置全局标志并立即触发 machine.reset() 或发布高优事件，由主循环/看门狗进入安全模式。
   - 若系统运行正常则定期喂狗；若温度过高则停止喂狗以触发 WDT 重启进入 SAFE_MODE。
   - 看门狗的初始化和喂狗统一由 MainController 负责，确保单一职责。

## 3. 建议实现方案
1. **新增 GuardianTimer 模块**
   - 位置：`app/utils/guardian.py`(仅分析，不创建)。
   - 初始化：在 `boot.py` 或 `main.py` 启动早期创建 `machine.Timer(id=1, mode=Timer.PERIODIC, period=5000, callback=_guardian_cb)`。
2. **_guardian_cb 关键逻辑**
   - 读取 MCU 温度(无需 SHT40)。
   - 若温度 ≥ 阈值：
     1. 通过 EventBus 发布 `SYSTEM_ERROR`(非阻塞)。
     2. 停止喂狗或直接调用 `machine.reset()` 进入 Boot → SAFE_MODE。
   - 若温度正常：调用 `machine.WDT.feed()`(WDT 实例由 MainController 统一管理和暴露)。
   - **注意**：回调逻辑务必 < ~50 µs，避免长时间占用中断。温度读取与事件发布若过长，可仅置位全局标志，由主循环异步处理。
3. **配置扩展**
   - 在 `CONFIG['daemon']` 下新增 `guardian_interval_ms` 与 `guardian_enabled`，保持灵活可配置。
4. **与环境数据采集并存**
- GuardianTimer 监控 MCU 温度；SHT40 仅用于环境数据采集/上报(非保护路径)。

## 4. 风险与约束
- ESP32-C3 仅剩 1 个硬件定时器(LED 控制占用 0 号)，需保证不与用户自定义冲突。
- Timer 回调不可使用阻塞 I/O(如 I2C)；选择 MCU 内置温度接口是关键。
- 看门狗超时需适当放宽(> 定时器间隔×2)以避免误触发。
- 记忆体限制：定时器本身占用极少，可忽略。

## 5. 结论
当前架构已具备看门狗；温度监控保护逻辑尚未启用。通过新增基于硬件定时器的 GuardianTimer，可在系统任何状态下以最高优先级监控 MCU 温度并与 WDT 协同，确保过热时立即进入安全模式，满足用户对实时性与可靠性的要求。

### 1. machine.reset() 是否导致无限重启？能否直接进入 SAFE_MODE？
1. **machine.reset() 的行为**
   - 触发一次 **硬复位**，等价于重新上电。
   - 复位后再次执行 `boot.py → main.py`，如果温度仍高于阈值、逻辑再次调用 `machine.reset()`，就会出现 **重启循环**。
2. **避免无限重启的两种思路**
   1. **启动早期温度判断：** 在 `boot.py` 或硬件定时器守护回调中写入某个 **RTC 存储标志**(或 NVS/RTC memory 位)，如果因温度过高而复位，则在下一次启动的 **最早阶段**先读取该标志，若仍高温则停留在极简循环(喂狗禁用)，不加载业务代码，直到温度恢复。
   2. **手动 SAFE_MODE：** 不用复位，而是：
      - 设置全局 `system_mode = "SAFE_MODE"`；
      - 立即 **停止主循环与外设**(事件总线、网络、LED 等)；
      - 关闭喂狗或延长 WDT 超时；
      - 保持极简低功耗循环，仅定时读取 MCU 温度，当温度 < 阈值 - 滞后值时，自动恢复 INIT → RUNNING 流程。
   - 这样可避免硬复位带来的循环重启，也更平滑。

> 结论：直接 `machine.reset()` 简单但有重启风险；推荐通过 *SAFE_MODE 标志 + 最小循环* 方式在单次上电周期内完成保护与恢复。

### 2. _check_temperature() 使用 SHT40 环境温度的逻辑问题
- 当前 FSM 已移除 `_check_temperature()` 和基于 SHT40 的温度保护逻辑；对于 **过热保护** 应以 **MCU 温度** 为准。
- 后续如需温度保护，将由 GuardianTimer 使用 `esp32.mcu_temperature()` 实现；SHT40 仅用于环境统计与上报。
        