


          

        
            
toolName: search_by_regex
            
status: success
          
query: process_led_updates|compat|compatibility|legacy|deprecated|fallback|shim|polyfill|backward|process_.*update|migrate
          

        
            
toolName: search_by_regex
            
status: success
          
query: watchdog|Watchdog|WDT|wdt|feed|wdog|kick
          

        
            
toolName: search_by_regex
            
status: success
          
query: Timer|machine\.Timer|utime|time\.sleep|sleep_ms|loop|while True|main loop|run\(\)|update\(
          

        
            
toolName: search_codebase
            
status: success
          
query: Find any code that indicates transitional or compatibility logic, such as multiple code paths for different environments or feature-detection-based branches within the app folder.
          

        
            
toolName: search_by_regex
            
status: success
          
query: create_network_manager|get_network_manager|create_global_network_manager|create_state_machine|get_state_machine|create_global_state_machine|process_led_updates
          

        
            
toolName: view_files
            
status: success
          
            
filePath: c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py
          

        
            
toolName: view_files
            
status: success
          
            
filePath: c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py
          

        
            
toolName: search_by_regex
            
status: success
          
query: set_led_mode\(|init_led\(|cleanup_led\(|cleanup\(|play\(
          

        
            
toolName: view_files
            
status: success
          
            
filePath: c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\config.py
          

        
            
toolName: view_files
            
status: success
          
            
filePath: c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py
          

        
            
toolName: todo_write
            
status: success
          
Todos updated: 7 items
          
好的，我先帮你全面梳理项目中的“兼容性/过渡性”代码点，并给出“最小改动、可逐步移除”的计划；随后给出看门狗放置在硬件定时器或主循环的对比与结论。

一、兼容性/过渡性代码清单（含定位）
- 主循环对 LED 的手动更新（已弃用，现为空操作）
  - 位置：在异步主循环中仍导入并调用 process_led_updates()，用于向后兼容早期“LED需主循环驱动”的实现
  - 参考：
    - <mcfile name="main.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py"></mcfile>
    - <mcsymbol name="_main_loop_async" filename="main.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py" startline="124" type="function"></mcsymbol>
    - <mcsymbol name="process_led_updates" filename="led.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py" startline="237" type="function"></mcsymbol>
  - 现状：LED 模块已由硬件定时器驱动，process_led_updates() 明确为空操作，保留仅用于兼容

- LED 模块的兼容接口
  - init_led()：用于“显式初始化”，但当前设计为延迟初始化，首次使用即自动完成
    - <mcsymbol name="init_led" filename="led.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py" startline="252" type="function"></mcsymbol>
  - set_led_mode(mode)：play 的别名，保留向后兼容
    - <mcsymbol name="set_led_mode" filename="led.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py" startline="269" type="function"></mcsymbol>
  - main 中尝试 import cleanup_led 再调用（try/except 包裹），而 LED 模块提供的是 cleanup()，cleanup_led 实际并不存在
    - <mcfile name="main.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py"></mcfile>

- NetworkManager 兼容工厂和全局单例接口（未被使用）
  - create_network_manager / get_network_manager / create_global_network_manager
  - 参考：
    - <mcfile name="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py"></mcfile>
    - <mcsymbol name="create_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="528" type="function"></mcsymbol>
    - <mcsymbol name="get_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="536" type="function"></mcsymbol>
    - <mcsymbol name="create_global_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="540" type="function"></mcsymbol>
  - 现状：Main 直接实例化 NetworkManager，不依赖这些兼容工厂

- FSM 兼容工厂和全局单例接口（未被使用）
  - create_state_machine / get_state_machine / create_global_state_machine
  - 参考：
    - <mcfile name="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py"></mcfile>
    - <mcsymbol name="create_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="340" type="function"></mcsymbol>
    - <mcsymbol name="get_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="348" type="function"></mcsymbol>
    - <mcsymbol name="create_global_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="352" type="function"></mcsymbol>
  - fsm/__init__.py 还在导出上述接口，属于二次兼容导出
    - <mcfile name="__init__.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\__init__.py"></mcfile>

- 需要“保留”的跨环境兼容点（不建议移除）
  - logger：utime/time 的回退导入
    - <mcfile name="logger.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\lib\logger.py"></mcfile>
  - ntp：ntptime 可选导入
    - <mcfile name="ntp.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\ntp.py"></mcfile>

二、移除（或收敛）计划（最小改动、逐步下线）
为避免一次性改动过多导致回归风险，建议两步走：

阶段A：安全收敛（最小代码改动，保持功能不变）
- 从主循环删除 process_led_updates 的导入与调用
  - 仅删除 <mcsymbol name="_main_loop_async" filename="main.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py" startline="124" type="function"></mcsymbol> 中相关两行，其他不动
- 将 main 中的 cleanup_led 改为 cleanup（避免 try/import 不存在符号）
  - 把 “from hw.led import cleanup_led; cleanup_led()” 改为 “from hw.led import cleanup; cleanup()”
- 保留 init_led（虽为兼容接口，但当前使用简单、风险低），待阶段B再处理
- 不改动 set_led_mode（别名），先维持现状，避免涉及 FSM 的联动

阶段B：彻底移除兼容层（在A稳定后）
- 删除 LED 模块中的 process_led_updates 函数与注释；若A已完成且无引用，可直接删除
  - <mcsymbol name="process_led_updates" filename="led.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\hw\led.py" startline="237" type="function"></mcsymbol>
- 将 FSM 内部 set_led_mode(...) 全量替换为 play(...)
  - 然后删除 LED 模块中的 set_led_mode(...) 兼容别名
  - 参考调用点在 FSM：<mcfile name="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py"></mcfile>
- 评估后删除 init_led（如希望完全依赖“延迟初始化 + 首次 play”）
- 删除 net/network_manager.py 末尾 create_* / get_* 兼容工厂与全局单例，并同步从 fsm/__init__.py 中移除导出
  - <mcsymbol name="create_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="528" type="function"></mcsymbol>
  - <mcsymbol name="get_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="536" type="function"></mcsymbol>
  - <mcsymbol name="create_global_network_manager" filename="network_manager.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\net\network_manager.py" startline="540" type="function"></mcsymbol>
  - <mcsymbol name="create_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="340" type="function"></mcsymbol>
  - <mcsymbol name="get_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="348" type="function"></mcsymbol>
  - <mcsymbol name="create_global_state_machine" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="352" type="function"></mcsymbol>
- 每一步都仅需确保 /build.py -c 通过即可，无需运行 app 下文件

三、看门狗应该放在硬件定时器还是主循环？
结论（推荐）：
- 继续放在主循环/调度点调用喂狗，更安全、语义更正确，不建议放在硬件定时器 ISR 中定时喂狗
- 在主循环喂狗前，做轻量“健康检查”（如主循环实际周期是否超限、关键任务是否卡死）再喂狗，能避免掩盖死锁

理由：
- WDT 的目的就是当系统“卡住”时重启。若用硬件定时器（尤其是中断回调）固定喂狗，即使主循环彻底卡住，仍会不断喂狗，等于“屏蔽了”死锁，丧失自愈能力
- 中断回调上下文下调用某些 API 可能受限（包括日志/复杂逻辑），难以做“健康检查”；主循环则能综合系统状态后再决定是否 feed
- 当前实现已在主循环统一调用喂狗：
  - <mcsymbol name="_main_loop_async" filename="main.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\main.py" startline="124" type="function"></mcsymbol> 内调用 self.state_machine.feed_watchdog()
  - <mcsymbol name="feed_watchdog" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="321" type="function"></mcsymbol>
- 进一步增强建议（不改变架构）：
  - 在主循环计算“真实循环周期”与阈值比较，超限则暂停 feed，让 WDT 触发重启
  - 关键异步任务（如网络管理）可周期更新“心跳时间戳”，主循环汇总判断是否喂狗

补充：配置与实现的“潜在不一致”（供后续一并优化）
- 配置中 WDT 开关与超时位于 daemon 段的平级键：
  - <mcfile name="config.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\config.py"></mcfile>
- 但 FSM 中读取了 daemon.watchdog 子字典，并未使用 wdt_enabled
  - <mcsymbol name="_init_watchdog" filename="core.py" path="c:\Users\Zusheng\Desktop\IOT_ESP32C3_HA\app\fsm\core.py" startline="76" type="function"></mcsymbol>
- 现状导致：wdt_enabled 实际未生效，timeout 也常退回默认值。后续可在不破坏兼容的前提下修正为：
  - 先尝试读取 daemon.watchdog（新结构），否则回退读取 daemon.wdt_enabled / daemon.wdt_timeout（现结构）

如果你同意，我可以按上述“阶段A（最小改动）”一次性提交代码调整，并确保 /build.py -c 编译通过；之后再推进阶段B的彻底清理。需要我现在就动手吗？
        