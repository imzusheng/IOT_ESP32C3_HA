### **重构与优化计划**

这个计划分为三个部分：

1.  **项目结构重构**：创建一个更清晰、更符合MicroPython社区实践的目录结构。
2.  **核心模块重构**：对现有模块进行拆分和功能重组，实现高内聚、低耦合。
3.  **代码与性能优化建议**：在重构的基础上，提出可以进一步提升系统性能和稳定性的建议。

-----

#### **第一部分：项目结构重构**

当前所有源码都平铺在`micropython_src/`目录下，随着功能增加，会变得难以管理。您的想法——“目录中只保留 main.py和boot.py，其他都放在一个文件夹中”——非常正确。

我建议创建一个`lib`目录，这是MicroPython中存放库模块的标准实践。

**重构前结构：**

```
micropython_src/
├── boot.py
├── main.py
├── config.py
├── core.py
├── daemon.py
├── led.py
├── logger.py
└── utils.py
```

**重构后结构 (建议):**

```
micropython_src/
├── boot.py
├── main.py
└── lib/
    ├── config.py           # 配置管理 (保持不变)
    ├── core.py             # 核心模块 (重构为纯粹的事件总线)
    ├── daemon.py           # 守护进程 (依赖项更新)
    ├── led.py              # LED控制 (功能增强，吸收所有LED逻辑)
    ├── logger.py           # 日志系统 (保持不变)
    ├── wifi.py             # 【新】WiFi管理模块 (从utils.py分离)
    ├── ntp.py              # 【新】NTP同步模块 (从utils.py分离)
    └── temp_optimizer.py   # 【新】温度优化策略模块 (从main.py分离)
```

**变化说明:**

1.  **创建 `lib` 目录**: 所有系统模块（非入口文件）全部移入`lib`目录。
2.  **分解 `utils.py`**: `utils.py` 是一个典型的“工具箱”模块，功能混杂，不利于维护和移植。我们将其彻底分解为 `wifi.py` 和 `ntp.py`。原有的 `utils.py` 文件可以被删除，或只保留真正通用的辅助函数（如此次重构后，它可能不再需要）。
3.  **创建 `temp_optimizer.py`**: 将 `main.py` 中的温度优化逻辑（如温度阈值、配置表、检查函数）分离出来，使`main.py`更专注于业务流程的编排。

-----

#### **第二部分：核心模块重构**

这是本次重构的核心，目标是实现功能完全独立。

**1. `utils.py` -\> `wifi.py`, `ntp.py`, `led.py` (彻底分解)**

  * **现状**: `utils.py` 包含了WiFi、NTP和LED的全部逻辑，耦合度非常高。
  * **重构方案**:
      * **创建 `lib/wifi.py`**:

          * 将 `utils.py` 中所有与WiFi相关的代码移入此文件，包括：
              * `WifiState` 枚举类。
              * `scan_available_networks`, `connect_wifi_attempt`, `connect_wifi`, `wifi_task` 等所有WiFi函数。
              * `_wifi_connected` 等WiFi状态变量。
          * 此模块将依赖 `core` (事件总线) 来发布WiFi状态事件 (如 `EV_WIFI_CONNECTED`)，并订阅 `config` 更新事件来响应温度优化（调整检查间隔）。

      * **创建 `lib/ntp.py`**:

          * 将 `utils.py` 中所有与NTP相关的代码移入此文件，包括：
              * `get_local_time`, `format_time`, `sync_ntp_time`, `ntp_task`。
              * `_ntp_synced` 等NTP状态变量。
          * 此模块将订阅WiFi连接成功的事件，来触发NTP同步。

      * **将LED逻辑并入 `lib/led.py`**:

          * 将 `utils.py` 中所有与LED相关的代码（包括异步任务 `led_effect_task` 和所有闪烁效果的实现）全部移入 `lib/led.py`。
          * 删除 `utils.py` 中的 `init_leds`, `deinit_leds`, `set_effect` 等函数。
          * **特别注意**: `wifi_connecting_blink` 这个函数，虽然由WiFi连接过程触发，但其本质是控制LED，也应移入`led.py`。`wifi.py`可以通过发布一个特定的事件（如 `EV_WIFI_CONNECTING_BLINK`）来触发这个效果。

**2. `led.py` (功能增强与统一)**

  * **现状**: `led.py` 是一个简单的面向对象的LED控制器，而 `utils.py` 中有更丰富的异步灯效实现。
  * **重构方案**:
      * 以 `utils.py` 中的LED逻辑为基础，将其与 `led.py` 的类结构结合。
      * 新的 `lib/led.py` 将包含一个 `LEDManager` 类，负责：
          * 硬件初始化 (`init`, `deinit`)。
          * 一个核心的异步任务 `led_task` (来自`utils.py`的`led_effect_task`) 来处理所有动态效果。
          * 提供清晰的外部接口，如 ` set_effect(effect_name, **params)  `。
          * 订阅`config`更新事件，以动态调整PWM频率和最大亮度，实现温度优化。

**3. `main.py` (职责单一化)**

  * **现状**: `main.py` 包含了业务逻辑、任务协调，甚至还有温度优化策略的具体定义，职责过重。
  * **重构方案**:
      * **创建 `lib/temp_optimizer.py`**:
          * 将 `main.py` 文件顶部的 `TEMP_THRESHOLDS`, `TEMP_LEVEL_CONFIGS` 字典以及 `get_temperature_level`, `get_optimized_config_for_temp`, `check_and_optimize` 函数全部移入此文件。
      * **简化 `system_coordinator_task`**:
          * `main.py` 中的 `system_coordinator_task` 不再包含具体的优化逻辑，而是导入 `temp_optimizer.py` 并调用其函数来获取优化配置，然后通过事件总线发布配置更新事件。
      * **更新模块导入**:
          * 所有 `import` 语句都需要更新，以反映 `lib/` 目录结构。例如 `import core` 将变为 `from lib import core`。

**4. `core.py` (回归核心)**

  * **现状**: `core.py` 除了事件总线，还包含了很多日志和LED的接口函数，像一个代理模块。
  * **重构方案**:
      * 移除 `log_critical`, `log_info` 等日志代理函数。需要记日志的模块应该直接 `from lib import logger`。
      * 移除 `init_led`, `set_led_effect` 等LED代理函数。需要控制LED的模块应该直接 `from lib import led`。
      * `core.py` 将只包含 `EventBus` 类和全局的 `subscribe`/`publish` 函数。这将使`core.py`成为一个纯粹、稳定、依赖最少的事件总线模块。

-----

#### **第三部分：代码与性能优化建议**

在完成上述重构后，您的代码已经非常清晰和健壮了。以下是一些可以锦上添花的优化点：

1.  **配置热重载优化**:

      * 在`config.py`的`reload_config`函数中，当检测到配置变更时，它会发布一个通用的`EV_CONFIG_UPDATE`事件，还会针对led、wifi、log等发布特定事件。
      * **建议**: 可以简化这个逻辑。只发布一个`EV_CONFIG_UPDATE`事件，并在事件的载荷(`payload`)中明确指出哪些部分 (`'led'`, `'wifi'`) 发生了变化。各个模块自己订阅这个通用事件，并检查载荷中是否有与自己相关的变更，再决定是否更新。这样`config`模块就不需要知道其他模块的具体事件名称了。

2.  **降低模块间耦合**:

      * `daemon.py` 中为了获取温度配置，导入了`main.py`。重构后它将导入`temp_optimizer.py`，这已经是一个进步。
      * **更进一步**: `daemon.py`可以不关心具体的优化策略。它只负责通过事件总线定期发布带有温度信息的`EV_PERFORMANCE_REPORT`事件。而`main.py`中的`system_coordinator_task`（或`temp_optimizer`模块）订阅这个事件，并决定如何响应。这样`daemon`就完全与优化策略解耦了。

3.  **内存使用**:

      * 您已经使用了`micropython.const`和`.mpy`文件编译，这是非常好的实践，请继续保持。
      * 在`config.py`中，许多全局常量（如`WIFI_CONFIGS`）在模块导入时就通过调用`get_wifi_configs()`来初始化。可以考虑在系统启动时，由`main.py`统一加载一次配置，并将配置字典通过依赖注入或一个全局单例的方式传递给需要的模块，而不是在每个模块导入时都去获取。但这会增加代码的复杂性，需要权衡。当前的方式对于ESP32C3的内存来说通常是可以接受的。

-----

### **总结**

执行以上重构计划后，您的项目将获得以下优势：

  * **高度模块化**: 每个`.py`文件都只做一件事，职责清晰。
  * **易于移植**: 想在别的项目中使用您的LED模块？只需拷贝`lib/led.py`和`lib/core.py`即可（因为它们通过事件解耦）。
  * **易于维护**: 修改WiFi逻辑时，您只需要关心`lib/wifi.py`，不会影响到其他部分。
  * **可扩展性强**: 添加新功能（如传感器、显示屏），只需在`lib/`下创建新模块，并将其挂接到事件总线上即可。