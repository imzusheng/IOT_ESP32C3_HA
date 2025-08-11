# app/lib/logger.py
try:
    import ulogging
except ImportError:
    from lib.lock import ulogging

# 日志级别常量定义
class LOG_LEVELS:
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3

class Logger:
    """
    基于 ulogging 的独立日志系统 (重构版本)
    
    使用 MicroPython 的 ulogging 模块作为底层日志记录器，
    独立工作，不再依赖外部事件系统。提供更高效的日志处理
    和更好的内存管理。
    
    特性:
    - 基于 ulogging 的高效日志记录
    - 独立日志记录，无需事件总线
    - 支持模块名称标注
    - 多级别日志支持 (DEBUG, INFO, WARN, ERROR, CRITICAL)
    - 内存优化设计
    - 时间戳格式化
    - 统一的接口
    - 错误隔离处理
    - 模块颜色强调支持
    - 标准化日志格式
    
    使用方法:
    1. 创建 Logger 实例：logger = Logger(level=EVENTS.LOG_INFO)
    2. 直接使用日志方法：logger.info("消息", module="模块名")
    """
    
    # ANSI颜色代码
    _COLORS = {
        'FSM': '\033[1;36m',     # 青色加粗
        'WiFi': '\033[1;32m',    # 绿色加粗
        'MQTT': '\033[1;33m',    # 黄色加粗
        'Main': '\033[1;35m',    # 紫色加粗
        'Cache': '\033[1;34m',   # 蓝色加粗
        'EventBus': '\033[1;31m', # 红色加粗
        'Timer': '\033[1;33m',   # 黄色加粗
        'Sensor': '\033[1;32m',  # 绿色加粗
        'LED': '\033[1;35m',     # 紫色加粗
        'Utils': '\033[1;37m',   # 白色加粗
        'RESET': '\033[0m'       # 重置颜色
    }
    
    # 模块名称映射
    _MODULE_MAP = {
        'fsm': 'FSM',
        'wifi': 'WiFi',
        'mqtt': 'MQTT',
        'main': 'Main',
        'cache': 'Cache',
        'eventbus': 'EventBus',
        'timer': 'Timer',
        'sensor': 'Sensor',
        'led': 'LED',
        'utils': 'Utils',
        'config': 'Config'
    }
    
    def __init__(self, level=LOG_LEVELS.INFO, config=None):
        # ulogging 级别映射
        self._ulogging_level_map = {
            LOG_LEVELS.DEBUG: ulogging.DEBUG,
            LOG_LEVELS.INFO: ulogging.INFO,
            LOG_LEVELS.WARN: ulogging.WARNING,
            LOG_LEVELS.ERROR: ulogging.ERROR,
        }
        
        # 兼容原有的级别映射
        self._level_map = {
            LOG_LEVELS.DEBUG: 0,
            LOG_LEVELS.INFO: 1,
            LOG_LEVELS.WARN: 2,
            LOG_LEVELS.ERROR: 3,
        }
        
        # 创建 ulogging 实例
        self._logger = ulogging.getLogger("")
        
        # 设置日志级别
        ulogging_level = self._ulogging_level_map.get(level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 设置兼容的级别
        self._level = self._level_map.get(level, 1)
        
        # 配置日志格式
        self._setup_logger_format()
        
        # 保留默认处理器引用用于后续判断回调是否被外部替换，
        # 若被替换则在直接日志方法中采用兼容调用，避免传递未知关键字参数
        self._default_handle_log = self._handle_log
        
        # 配置参数
        self._config = config or {}
        self._enable_colors = self._config.get('enable_colors', True)
        self._show_milliseconds = self._config.get('show_milliseconds', True)
        self._auto_module_detection = self._config.get('auto_module_detection', True)
        
    def _setup_logger_format(self):
        """配置自定义的日志输出格式，避免双重前缀"""
        # 清除所有现有的处理器
        self._logger.handlers = []
        
        # 创建自定义处理器
        class CustomHandler:
            def __init__(self, logger_instance):
                self.logger_instance = logger_instance
                
            def write(self, msg):
                # 直接输出消息，不添加任何前缀
                print(msg, end='')
                
            def flush(self):
                pass  # 不需要实现
        
        # 添加自定义处理器
        custom_handler = CustomHandler(self)
        self._logger.handlers = [custom_handler]
        
        # 设置基本配置
        if hasattr(ulogging, 'basicConfig'):
            ulogging.basicConfig(level=ulogging.INFO)


    # setup 方法已移除 - Logger 现在独立工作，不再依赖 EventBus

    def set_level(self, new_level):
        """
        设置新的日志记录级别。
        :param new_level: 来自 EVENTS 的日志级别常量
        """
        # 设置兼容的级别
        self._level = self._level_map.get(new_level, 1)
        
        # 设置 ulogging 级别
        ulogging_level = self._ulogging_level_map.get(new_level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 记录级别变更（如果可用）
        try:
            self._logger.info(f"日志级别已更改为: {new_level}")
        except:
            pass  # 如果 ulogging 不可用，忽略

    def _get_formatted_timestamp(self):
        """获取格式化的时间戳，兼容 MicroPython 优先使用 RTC 本地时间"""
        try:
            import utime as time
            # 判断是否有可靠的 RTC 时间（例如通过 NTP 同步）
            t = time.localtime()
            year = t[0]
            has_rtc = year >= 2020
            milliseconds = time.ticks_ms() % 1000

            if has_rtc:
                # 添加UTC+8时区偏移
                timestamp = time.mktime(t) + 8 * 3600  # 加8小时
                t = time.localtime(timestamp)
                # 使用 RTC 的本地时间
                time_str = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
            else:
                # 使用开机累计时间（不依赖 RTC）
                total_seconds = (time.ticks_ms() // 1000) % (24 * 3600)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                secs = total_seconds % 60
                time_str = "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)

            if self._show_milliseconds:
                return "{}.{:03d}".format(time_str, milliseconds)
            else:
                return time_str
        except:
            # 最后的备用方案：回退到开机累计时间
            try:
                import utime as time
                total_seconds = (time.ticks_ms() // 1000) % (24 * 3600)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                secs = total_seconds % 60
                return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)
            except:
                return "00:00:00"
    
    def _get_level_name(self, event_name):
        """获取日志级别名称"""
        level_map = {
            LOG_LEVELS.DEBUG: 'DEBUG',
            LOG_LEVELS.INFO: 'INFO',
            LOG_LEVELS.WARN: 'WARN',
            LOG_LEVELS.ERROR: 'ERROR'
        }
        return level_map.get(event_name, 'INFO')
    
    def _normalize_module_name(self, module_name):
        """标准化模块名称"""
        if not module_name:
            return None
        
        # 转换为小写进行映射
        normalized = module_name.lower()
        return self._MODULE_MAP.get(normalized, module_name.upper())
    
        
    def _handle_log(self, event_name, msg=None, *args, **kwargs):
        """
        处理接收到的日志事件。
        直接输出日志，避免双重前缀。
        支持模块来源标注和防抖机制。
        """
        # 从旧格式兼容：如果 msg 是第一个位置参数
        if msg is None and args:
            msg = args[0]
            args = args[1:]
        
        log_level = self._level_map.get(event_name)
        if log_level is None or log_level < self._level:
            return

        # 格式化消息
        try:
            formatted_msg = msg.format(*args)
        except:
            formatted_msg = msg
        
        # 添加模块来源标注
        module_name = kwargs.get('module', None)
        error_context = kwargs.get('error_context', None)
        
        # 如果有错误上下文，提取模块信息
        if error_context and isinstance(error_context, dict):
            if 'callback_name' in error_context:
                # 从回调名提取模块信息
                callback_name = error_context.get('callback_name', '')
                if '.' in callback_name:
                    parts = callback_name.split('.')
                    if len(parts) >= 2:
                        module_name = module_name or parts[0].upper()
                
            # 如果有源事件信息，也可以从中推断模块
            source_event = error_context.get('event', '')
            if source_event and not module_name:
                if source_event.startswith('wifi.'):
                    module_name = 'WiFi'
                elif source_event.startswith('mqtt.'):
                    module_name = 'MQTT'
                elif source_event.startswith('system.'):
                    module_name = 'System'
                elif source_event.startswith('led.'):
                    module_name = 'LED'
                elif source_event.startswith('sensor.'):
                    module_name = 'Sensor'
        
        # 标准化模块名称
        module_name = self._normalize_module_name(module_name)
        
        # 构建标准化的日志格式
        timestamp = self._get_formatted_timestamp()
        level_name = self._get_level_name(event_name)
        
        # 构建消息前缀
        if module_name:
            if self._enable_colors:
                color_code = self._COLORS.get(module_name, '')
                reset_code = self._COLORS.get('RESET', '')
                prefix = f"{timestamp} [{level_name}] {color_code}[{module_name}]{reset_code}"
            else:
                prefix = f"{timestamp} [{level_name}] [{module_name}]"
        else:
            prefix = f"{timestamp} [{level_name}]"
        
        full_msg = f"{prefix} {formatted_msg}"

        # 直接输出日志，避免通过 ulogging 添加额外前缀
        print(full_msg)

    def _invoke_handler_compat(self, handler, event_name, msg, args, module):
        """
        安全调用（可能被外部替换的）_handle_log 回调，
        逐步放宽参数，避免因未知关键字参数导致的 TypeError。
        优先尝试保留 event_name 以及格式化参数。
        """
        try:
            # 优先尝试包含 module 关键字（如果外部实现支持）
            if module is not None:
                return handler(event_name, msg, *args, module=module)
            else:
                return handler(event_name, msg, *args)
        except TypeError:
            pass
        try:
            # 去掉关键字参数，仅位置参数
            return handler(event_name, msg, *args)
        except TypeError:
            pass
        try:
            # 退化为仅 event_name 与原始消息
            return handler(event_name, msg)
        except TypeError:
            pass
        try:
            # 最后尝试仅传入消息（极端兼容）
            return handler(msg)
        except TypeError:
            # 放弃调用，避免影响主流程
            return
        
    # 直接日志方法 - 提供更直接的日志记录接口，支持模块标注
    def debug(self, msg, *args, module=None):
        """直接记录调试日志"""
        handler = self._handle_log
        if handler is self._default_handle_log:
            handler(LOG_LEVELS.DEBUG, msg, *args, module=module)
        else:
            self._invoke_handler_compat(handler, LOG_LEVELS.DEBUG, msg, args, module)
        
    def info(self, msg, *args, module=None):
        """直接记录信息日志"""
        handler = self._handle_log
        if handler is self._default_handle_log:
            handler(LOG_LEVELS.INFO, msg, *args, module=module)
        else:
            self._invoke_handler_compat(handler, LOG_LEVELS.INFO, msg, args, module)
        
    def warning(self, msg, *args, module=None):
        """直接记录警告日志"""
        handler = self._handle_log
        if handler is self._default_handle_log:
            handler(LOG_LEVELS.WARN, msg, *args, module=module)
        else:
            self._invoke_handler_compat(handler, LOG_LEVELS.WARN, msg, args, module)
        
    def error(self, msg, *args, module=None):
        """直接记录错误日志"""
        handler = self._handle_log
        if handler is self._default_handle_log:
            handler(LOG_LEVELS.ERROR, msg, *args, module=module)
        else:
            self._invoke_handler_compat(handler, LOG_LEVELS.ERROR, msg, args, module)
        
    def critical(self, msg, *args, module=None):
        """直接记录严重错误日志"""
        try:
            full_msg = msg.format(*args)
        except:
            full_msg = msg
        
        if module:
            full_msg = f"[{module}] CRITICAL: {full_msg}"
        else:
            full_msg = f"严重错误: {full_msg}"
            
        self._logger.error(full_msg)
  
# Logger 现在独立工作，不再依赖 EventBus
# 所有日志记录都通过直接方法调用完成，无需事件总线
    
# 全局日志实例 - 提供便捷的全局日志记录功能
_global_logger = None

def get_global_logger():
    """获取全局日志实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger()
    return _global_logger

def set_global_logger(logger):
    """设置全局日志实例"""
    global _global_logger
    _global_logger = logger
    
# 便捷的全局日志函数，支持模块标注
def debug(msg, *args, module=None):
    """全局调试日志函数"""
    logger = get_global_logger()
    logger.debug(msg, *args, module=module)
    
def info(msg, *args, module=None):
    """全局信息日志函数"""
    logger = get_global_logger()
    logger.info(msg, *args, module=module)
    
def warning(msg, *args, module=None):
    """全局警告日志函数"""
    logger = get_global_logger()
    logger.warning(msg, *args, module=module)
    
def error(msg, *args, module=None):
    """全局错误日志函数"""
    logger = get_global_logger()
    logger.error(msg, *args, module=module)
    
def critical(msg, *args, module=None):
    """全局严重错误日志函数"""
    logger = get_global_logger()
    logger.critical(msg, *args, module=module)