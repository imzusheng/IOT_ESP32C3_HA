# ESP32-C3 IoT事件驱动架构图

## 1. 核心架构图

```mermaid
graph TB
    subgraph "核心服务层"
        EB[EventBus<br/>事件总线<br/>异步非阻塞]
        OP[ObjectPool<br/>对象池管理器<br/>内存优化]
        SC[StaticCache<br/>静态缓存<br/>持久化存储]
        LG[Logger<br/>日志系统<br/>事件驱动]
    end
    
    subgraph "硬件抽象层"
        WM[WifiManager<br/>WiFi管理器<br/>多网络支持]
        MC[MqttController<br/>MQTT控制器<br/>指数退避重连]
        LED[LEDPatternController<br/>LED模式控制<br/>状态可视化]
        SM[SensorManager<br/>传感器管理<br/>数据采集]
    end
    
    subgraph "系统控制层"
        FSM[SystemFSM<br/>状态机<br/>9状态管理]
        MAIN[MainController<br/>主控制器<br/>依赖注入]
        CFG[Config<br/>配置管理<br/>集中式配置]
    end
    
    subgraph "外部库"
        subgraph "lib/lock"
            MQTT[umqtt.py<br/>轻量级MQTT客户端]
            LOG[ulogging.py<br/>轻量级日志库]
        end
    end
    
    %% 核心连接关系
    EB --> WM
    EB --> MC
    EB --> LED
    EB --> SM
    EB --> FSM
    EB --> LG
    
    OP --> MC
    OP --> SM
    
    SC --> FSM
    
    LG --> EB
    
    MAIN --> EB
    MAIN --> OP
    MAIN --> SC
    MAIN --> LG
    MAIN --> WM
    MAIN --> MC
    MAIN --> LED
    MAIN --> SM
    MAIN --> FSM
    MAIN --> CFG
    
    FSM --> WM
    FSM --> MC
    FSM --> LED
    
    MC --> MQTT
    LG --> LOG
    
    %% 样式
    classDef core fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef hardware fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef control fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px
    
    class EB,OP,SC,LG core
    class WM,MC,LED,SM hardware
    class FSM,MAIN,CFG control
    class MQTT,LOG external
```

## 2. 事件流程图

```mermaid
graph LR
    subgraph "事件源"
        BOOT[系统启动<br/>SYSTEM_BOOT]
        WIFI[WiFi事件<br/>WIFI_CONNECTED]
        MQTT[MQTT事件<br/>MQTT_CONNECTED]
        ERROR[系统错误<br/>SYSTEM_ERROR]
        SENSOR[传感器数据<br/>SENSOR_DATA]
    end
    
    subgraph "EventBus处理"
        EB[EventBus<br/>事件总线]
        SUB[订阅者列表]
        SCHED[异步调度<br/>micropython.schedule]
        LIMIT[频率限制<br/>防抖处理]
    end
    
    subgraph "事件消费者"
        FSM[状态机<br/>状态转换]
        LOG[日志系统<br/>记录日志]
        LED[LED控制器<br/>状态显示]
        CACHE[静态缓存<br/>持久化]
    end
    
    BOOT --> EB
    WIFI --> EB
    MQTT --> EB
    ERROR --> EB
    SENSOR --> EB
    
    EB --> SUB
    EB --> LIMIT
    EB --> SCHED
    
    SUB --> FSM
    SUB --> LOG
    SUB --> LED
    SUB --> CACHE
    
    SCHED --> FSM
    SCHED --> LOG
    SCHED --> LED
    SCHED --> CACHE
    
    %% 样式
    classDef source fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef process fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef consumer fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    
    class BOOT,WIFI,MQTT,ERROR,SENSOR source
    class EB,SUB,SCHED,LIMIT process
    class FSM,LOG,LED,CACHE consumer
```

## 3. 状态机转换图

```mermaid
stateDiagram-v2
    [*] --> BOOT
    BOOT --> INIT: SYSTEM_BOOT
    INIT --> NETWORKING: SYSTEM_INIT
    INIT --> ERROR: SYSTEM_ERROR
    
    NETWORKING --> RUNNING: WIFI_CONNECTED
    NETWORKING --> WARNING: WIFI_DISCONNECTED
    NETWORKING --> ERROR: SYSTEM_ERROR
    
    RUNNING --> NETWORKING: WIFI_DISCONNECTED
    RUNNING --> WARNING: MQTT_DISCONNECTED
    RUNNING --> WARNING: SYSTEM_WARNING
    RUNNING --> ERROR: SYSTEM_ERROR
    RUNNING --> SAFE_MODE: MEMORY_CRITICAL
    
    WARNING --> RUNNING: WIFI_CONNECTED
    WARNING --> RUNNING: MQTT_CONNECTED
    WARNING --> RUNNING: RECOVERY_SUCCESS
    WARNING --> ERROR: SYSTEM_ERROR
    WARNING --> SAFE_MODE: MEMORY_CRITICAL
    
    ERROR --> WARNING: RECOVERY_SUCCESS
    ERROR --> SAFE_MODE: RECOVERY_FAILED
    ERROR --> SAFE_MODE: MEMORY_CRITICAL
    ERROR --> SHUTDOWN: SYSTEM_SHUTDOWN
    
    SAFE_MODE --> WARNING: RECOVERY_SUCCESS
    SAFE_MODE --> SHUTDOWN: SYSTEM_SHUTDOWN
    
    RECOVERY --> RUNNING: RECOVERY_SUCCESS
    RECOVERY --> SAFE_MODE: RECOVERY_FAILED
    RECOVERY --> ERROR: SYSTEM_ERROR
    RECOVERY --> SAFE_MODE: MEMORY_CRITICAL
    
    SHUTDOWN --> [*]
    
    note right of RUNNING: 正常运行状态<br/>所有服务正常
    note right of WARNING: 警告状态<br/>部分服务异常
    note right of ERROR: 错误状态<br/>尝试自动恢复
    note right of SAFE_MODE: 安全模式<br/>最小化服务
    note right of SHUTDOWN: 关机状态<br/>系统停止
```

## 4. 模块依赖关系图

```mermaid
graph TB
    subgraph "入口点"
        MAIN[main.py<br/>系统入口]
    end
    
    subgraph "核心服务"
        EB[lib/event_bus.py]
        OP[lib/object_pool.py]
        SC[lib/static_cache.py]
        LG[lib/logger.py]
    end
    
    subgraph "网络层"
        WIFI[net/wifi.py]
        MQTT[net/mqtt.py]
    end
    
    subgraph "硬件层"
        LED[hw/led.py]
        SENSOR[hw/sensor.py]
    end
    
    subgraph "系统层"
        FSM[fsm.py]
        CFG[config.py]
        EVT[event_const.py]
    end
    
    subgraph "工具层"
        HELPERS[utils/helpers.py]
        TIMERS[utils/timers.py]
    end
    
    subgraph "外部库"
        UMQTT[lib/lock/umqtt.py]
        ULOG[lib/lock/ulogging.py]
    end
    
    %% 依赖关系
    MAIN --> CFG
    MAIN --> EB
    MAIN --> OP
    MAIN --> SC
    MAIN --> LG
    MAIN --> FSM
    MAIN --> WIFI
    MAIN --> MQTT
    MAIN --> LED
    MAIN --> SENSOR
    
    FSM --> EB
    FSM --> OP
    FSM --> SC
    FSM --> CFG
    FSM --> EVT
    
    WIFI --> EB
    WIFI --> EVT
    
    MQTT --> EB
    MQTT --> OP
    MQTT --> EVT
    MQTT --> UMQTT
    
    LED --> EVT
    
    SENSOR --> EB
    SENSOR --> OP
    SENSOR --> EVT
    
    LG --> EB
    LG --> EVT
    LG --> ULOG
    
    HELPERS --> CFG
    TIMERS --> CFG
    
    %% 样式
    classDef entry fill:#ffecb3,stroke:#ff6f00,stroke-width:2px
    classDef core fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef network fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef hardware fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef system fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef utils fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef external fill:#efebe9,stroke:#3e2723,stroke-width:2px
    
    class MAIN entry
    class EB,OP,SC,LG core
    class WIFI,MQTT network
    class LED,SENSOR hardware
    class FSM,CFG,EVT system
    class HELPERS,TIMERS utils
    class UMQTT,ULOG external
```

## 5. 事件类型层次图

```mermaid
graph TD
    subgraph "系统事件"
        SYS_BOOT[SYSTEM_BOOT<br/>系统启动]
        SYS_INIT[SYSTEM_INIT<br/>系统初始化]
        SYS_READY[SYSTEM_READY<br/>系统就绪]
        SYS_ERROR[SYSTEM_ERROR<br/>系统错误]
        SYS_WARN[SYSTEM_WARNING<br/>系统警告]
        SYS_SHUTDOWN[SYSTEM_SHUTDOWN<br/>系统关机]
        MEMORY[MEMORY_CRITICAL<br/>内存告急]
        HEARTBEAT[SYSTEM_HEARTBEAT<br/>系统心跳]
    end
    
    subgraph "网络事件"
        WIFI_CONNECT[WIFI_CONNECTING<br/>WiFi连接中]
        WIFI_CONN[WIFI_CONNECTED<br/>WiFi已连接]
        WIFI_DIS[WIFI_DISCONNECTED<br/>WiFi断开]
        WIFI_SCAN[WIFI_SCAN_DONE<br/>WiFi扫描完成]
        MQTT_CONN[MQTT_CONNECTED<br/>MQTT已连接]
        MQTT_DIS[MQTT_DISCONNECTED<br/>MQTT断开]
        MQTT_MSG[MQTT_MESSAGE<br/>MQTT消息]
    end
    
    subgraph "时间事件"
        NTP_START[NTP_SYNC_STARTED<br/>NTP同步开始]
        NTP_SUCCESS[NTP_SYNC_SUCCESS<br/>NTP同步成功]
        NTP_FAIL[NTP_SYNC_FAILED<br/>NTP同步失败]
        TIME_UPDATE[TIME_UPDATED<br/>时间更新]
    end
    
    subgraph "硬件事件"
        BUTTON[BUTTON_PRESSED<br/>按钮按下]
        SENSOR_DATA[SENSOR_DATA<br/>传感器数据]
    end
    
    subgraph "日志事件"
        LOG_INFO[LOG_INFO<br/>信息日志]
        LOG_WARN[LOG_WARN<br/>警告日志]
        LOG_ERROR[LOG_ERROR<br/>错误日志]
        LOG_DEBUG[LOG_DEBUG<br/>调试日志]
    end
    
    subgraph "恢复事件"
        RECOVERY_OK[RECOVERY_SUCCESS<br/>恢复成功]
        RECOVERY_FAIL[RECOVERY_FAILED<br/>恢复失败]
    end
    
    %% 样式
    classDef system fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    classDef network fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef time fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    classDef hardware fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef log fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef recovery fill:#e0f2f1,stroke:#00695c,stroke-width:2px
    
    class SYS_BOOT,SYS_INIT,SYS_READY,SYS_ERROR,SYS_WARN,SYS_SHUTDOWN,MEMORY,HEARTBEAT system
    class WIFI_CONNECT,WIFI_CONN,WIFI_DIS,WIFI_SCAN,MQTT_CONN,MQTT_DIS,MQTT_MSG network
    class NTP_START,NTP_SUCCESS,NTP_FAIL,TIME_UPDATE time
    class BUTTON,SENSOR_DATA hardware
    class LOG_INFO,LOG_WARN,LOG_ERROR,LOG_DEBUG log
    class RECOVERY_OK,RECOVERY_FAIL recovery
```

## 6. 内存管理架构图

```mermaid
graph TB
    subgraph "内存优化策略"
        GC[垃圾回收<br/>Garbage Collection]
        POOL[对象池<br/>Object Pool]
        CACHE[静态缓存<br/>Static Cache]
        WDT[看门狗<br/>Watchdog]
    end
    
    subgraph "对象池系统"
        OP[ObjectPoolManager]
        MQTT_POOL[mqtt_messages<br/>10个对象]
        SENSOR_POOL[sensor_data<br/>5个对象]
        LOG_POOL[log_messages<br/>20个对象]
        EVENT_POOL[system_events<br/>15个对象]
    end
    
    subgraph "缓存系统"
        SC[StaticCache]
        CONFIG[配置缓存<br/>防抖写入]
        STATE[状态缓存<br/>自动保存]
        RECOVERY[恢复缓存<br/>错误恢复]
    end
    
    subgraph "监控机制"
        MEM_CHECK[内存检查<br/>阈值监控]
        TEMP_CHECK[温度检查<br/>过热保护]
        HEALTH_CHECK[健康检查<br/>系统状态]
    end
    
    OP --> MQTT_POOL
    OP --> SENSOR_POOL
    OP --> LOG_POOL
    OP --> EVENT_POOL
    
    SC --> CONFIG
    SC --> STATE
    SC --> RECOVERY
    
    MEM_CHECK --> GC
    TEMP_CHECK --> GC
    HEALTH_CHECK --> GC
    
    %% 样式
    classDef strategy fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef pool fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef cache fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef monitor fill:#fff3e0,stroke:#ef6c00,stroke-width:2px
    
    class GC,POOL,CACHE,WDT strategy
    class OP,MQTT_POOL,SENSOR_POOL,LOG_POOL,EVENT_POOL pool
    class SC,CONFIG,STATE,RECOVERY cache
    class MEM_CHECK,TEMP_CHECK,HEALTH_CHECK monitor
```

## 架构特点总结

1. **事件驱动**: 以EventBus为核心的松耦合架构
2. **异步处理**: 使用micropython.schedule实现非阻塞事件处理
3. **状态管理**: 9个系统状态，支持自动错误恢复
4. **内存优化**: 对象池、静态缓存、智能垃圾回收
5. **错误隔离**: 频率限制、错误递归保护、降级处理
6. **模块化设计**: 清晰的层次结构，易于维护和扩展