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

# 装饰器：安全日志记录
def safe_log(level='error'):
    """装饰器：包装目标函数，自动捕获并安全记录异常"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _log(level, "函数{}异常: {}", func.__name__, str(e))
                return None
        return wrapper
    return decorator

# 安全日志记录函数
def _log(level, msg, *args, **kwargs):
    """安全日志记录，避免日志异常影响主逻辑"""
    try:
        logger = get_global_logger()
        if hasattr(logger, level):
            getattr(logger, level)(msg, *args, **kwargs)
        else:
            logger.info(msg, *args, **kwargs)
    except:
        # 降级到print输出
        try:
            formatted_msg = msg.format(*args) if args else msg
            print(f"[Logger] {formatted_msg}")
        except:
            print(f"[Logger] {msg}")

class Logger:
    """
    基于 ulogging 的日志系统
    
    使用方法:
    1. 创建 Logger 实例: logger = Logger(level=LOG_LEVELS.INFO)
    2. 直接使用日志方法: logger.info("消息", module="模块名")
    """
    
    # 类型定义
    LogLevel = int
    ModuleName = str
    LogMessage = str
    LogConfig = dict
    
    # ANSI颜色代码
    _COLORS = {
        'FSM': '\033[1;36m',     # 青色加粗
        'NET': '\033[1;34m',     # 蓝色加粗
        'WiFi': '\033[1;32m',    # 绿色加粗
        'MQTT': '\033[1;33m',    # 黄色加粗
        'Main': '\033[1;35m',    # 紫色加粗
        'Cache': '\033[1;34m',   # 蓝色加粗
        'EventBus': '\033[1;31m',# 红色加粗
        'Timer': '\033[1;33m',   # 黄色加粗
        'Sensor': '\033[1;32m',  # 绿色加粗
        'LED': '\033[1;35m',     # 紫色加粗
        'Utils': '\033[1;37m',   # 白色加粗
        'RESET': '\033[0m',      # 重置颜色
        # 日志级别颜色
        'ERROR': '\033[1;31m',   # 红色加粗
        'WARN': '\033[1;33m',    # 黄色加粗（橙黄色）
        'WARNING': '\033[1;33m'  # 黄色加粗（橙黄色）
    }
    
    # 模块名称映射
    _MODULE_MAP = {
        'fsm': 'FSM',
        'net': 'NET',
        'network': 'NET',
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
    
    def __init__(self, level: LogLevel = LOG_LEVELS.INFO, config: LogConfig = None) -> None:
        """
        初始化 Logger 实例
        
        Args:
            level: 日志级别，默认为 INFO
            config: 日志配置字典，包含以下选项:
                - enable_colors: 是否启用颜色 (默认: True)
                - show_milliseconds: 是否显示毫秒 (默认: True) 
                - auto_module_detection: 是否自动检测模块 (默认: True)
                - enable_alignment: 是否启用对齐 (默认: True)
        """
        # ulogging 级别映射
        self._ulogging_level_map = {
            LOG_LEVELS.DEBUG: ulogging.DEBUG,
            LOG_LEVELS.INFO: ulogging.INFO,
            LOG_LEVELS.WARN: ulogging.WARNING,
            LOG_LEVELS.ERROR: ulogging.ERROR,
        }

        # 创建 ulogging 实例
        self._logger = ulogging.getLogger("")
        
        # 设置日志级别
        ulogging_level = self._ulogging_level_map.get(level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 设置日志级别
        self._level = level
        
        # 配置日志格式
        self._setup_logger_format()
        
        # 配置参数
        self._config = config or {}
        self._enable_colors = self._config.get('enable_colors', True)
        self._show_milliseconds = self._config.get('show_milliseconds', True)
        self._auto_module_detection = self._config.get('auto_module_detection', True)
        self._enable_alignment = self._config.get('enable_alignment', True)
        
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

    def set_level(self, new_level: LogLevel) -> None:
        """
        设置新的日志记录级别。
        
        Args:
            new_level: 新的日志级别 (LOG_LEVELS.DEBUG/INFO/WARN/ERROR)
        """
        # 设置日志级别
        self._level = new_level
        
        # 设置 ulogging 级别
        ulogging_level = self._ulogging_level_map.get(new_level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 记录级别变更（如果可用）
        try:
            self._logger.info(f"日志级别已更改为: {new_level}")
        except:
            pass  # 如果 ulogging 不可用，忽略

    def _get_formatted_timestamp(self) -> str:
        """
        获取格式化的时间戳，兼容 MicroPython 优先使用 RTC 本地时间
        
        Returns:
            格式化的时间字符串，如 "14:25:36.123"
        """
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
    
    def _get_level_name(self, event_name: LogLevel) -> str:
        """
        获取日志级别名称，支持固定宽度对齐和颜色
        
        Args:
            event_name: 日志级别常量
            
        Returns:
            格式化的级别名称字符串
        """
        level_map = {
            LOG_LEVELS.DEBUG: 'DEBUG',
            LOG_LEVELS.INFO: 'INFO',
            LOG_LEVELS.WARN: 'WARN',
            LOG_LEVELS.ERROR: 'ERROR'
        }
        level_name = level_map.get(event_name, 'INFO')
        
        # 如果启用了对齐，使用固定宽度格式
        if self._enable_alignment:
            formatted_level = f"{level_name:<5}"  # 左对齐，宽度5字符
        else:
            formatted_level = level_name
        
        # 如果启用了颜色，为特定级别添加颜色
        if self._enable_colors:
            if level_name == 'ERROR':
                color_code = self._COLORS.get('ERROR', '')
                reset_code = self._COLORS.get('RESET', '')
                return f"{color_code}{formatted_level}{reset_code}"
            elif level_name in ['WARN', 'WARNING']:
                color_code = self._COLORS.get('WARN', '')
                reset_code = self._COLORS.get('RESET', '')
                return f"{color_code}{formatted_level}{reset_code}"
        
        return formatted_level
    
    def _normalize_module_name(self, module_name: ModuleName) -> ModuleName:
        """
        标准化模块名称
        
        Args:
            module_name: 原始模块名称
            
        Returns:
            标准化后的模块名称，如 "FSM", "WiFi", "MQTT"
        """
        if not module_name:
            return None
        
        # 转换为小写进行映射
        normalized = module_name.lower()
        return self._MODULE_MAP.get(normalized, module_name.upper())
    
        
    def _handle_log(self, event_name: LogLevel, msg: LogMessage = None, *args, **kwargs) -> None:
        """
        处理接收到的日志事件。
        直接输出日志，避免双重前缀。
        支持模块来源标注和防抖机制。
        
        Args:
            event_name: 日志级别
            msg: 日志消息模板
            *args: 消息格式化参数
            **kwargs: 额外参数，支持:
                - module: 模块名称
                - error_context: 错误上下文字典
        """
        # 从旧格式兼容：如果 msg 是第一个位置参数
        if msg is None and args:
            msg = args[0]
            args = args[1:]
        
        if event_name < self._level:
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

          
    # 直接日志方法 - 提供更直接的日志记录接口，支持模块标注
    def debug(self, msg: LogMessage, *args, module: ModuleName = None) -> None:
        """
        直接记录调试日志
        
        Args:
            msg: 日志消息模板
            *args: 消息格式化参数
            module: 模块名称，如 "FSM", "WiFi", "MQTT"
            
        Example:
            logger.debug("连接状态: {}", status, module="WiFi")
        """
        self._handle_log(LOG_LEVELS.DEBUG, msg, *args, module=module)
        
    def info(self, msg: LogMessage, *args, module: ModuleName = None) -> None:
        """
        直接记录信息日志
        
        Args:
            msg: 日志消息模板
            *args: 消息格式化参数
            module: 模块名称，如 "FSM", "WiFi", "MQTT"
            
        Example:
            logger.info("系统已启动", module="Main")
        """
        self._handle_log(LOG_LEVELS.INFO, msg, *args, module=module)
        
    def warning(self, msg: LogMessage, *args, module: ModuleName = None) -> None:
        """
        直接记录警告日志
        
        Args:
            msg: 日志消息模板
            *args: 消息格式化参数
            module: 模块名称，如 "FSM", "WiFi", "MQTT"
            
        Example:
            logger.warning("内存使用率过高: {}%", usage, module="System")
        """
        self._handle_log(LOG_LEVELS.WARN, msg, *args, module=module)
        
    def error(self, msg: LogMessage, *args, module: ModuleName = None) -> None:
        """
        直接记录错误日志
        
        Args:
            msg: 日志消息模板
            *args: 消息格式化参数
            module: 模块名称，如 "FSM", "WiFi", "MQTT"
            
        Example:
            logger.error("连接失败: {}", error_msg, module="MQTT")
        """
        self._handle_log(LOG_LEVELS.ERROR, msg, *args, module=module)
        
    def critical(self, msg: LogMessage, *args, module: ModuleName = None) -> None:
        """
        直接记录严重错误日志
        
        Args:
            msg: 日志消息模板
            *args: 消息格式化参数
            module: 模块名称，如 "FSM", "WiFi", "MQTT"
            
        Example:
            logger.critical("系统严重错误，即将重启", module="System")
        """
        self._handle_log(LOG_LEVELS.ERROR, msg, *args, module=module)
  
# Logger 现在独立工作，不再依赖 EventBus
# 所有日志记录都通过直接方法调用完成，无需事件总线
    
# 全局日志实例 - 提供便捷的全局日志记录功能
_global_logger = None

def get_global_logger() -> Logger:
    """
    获取全局日志实例
    
    Returns:
        全局 Logger 实例，如果不存在则创建新的
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger()
    return _global_logger

def set_global_logger(logger: Logger) -> None:
    """
    设置全局日志实例
    
    Args:
        logger: 要设置为全局的 Logger 实例
    """
    global _global_logger
    _global_logger = logger
    
# 便捷的全局日志函数，支持模块标注
def debug(msg: LogMessage, *args, module: ModuleName = None) -> None:
    """
    全局调试日志函数
    
    Args:
        msg: 日志消息模板
        *args: 消息格式化参数
        module: 模块名称
        
    Example:
        debug("调试信息: {}", value, module="Utils")
    """
    logger = get_global_logger()
    logger.debug(msg, *args, module=module)
    
def info(msg: LogMessage, *args, module: ModuleName = None) -> None:
    """
    全局信息日志函数
    
    Args:
        msg: 日志消息模板
        *args: 消息格式化参数
        module: 模块名称
        
    Example:
        info("系统信息", module="Main")
    """
    logger = get_global_logger()
    logger.info(msg, *args, module=module)
    
def warning(msg: LogMessage, *args, module: ModuleName = None) -> None:
    """
    全局警告日志函数
    
    Args:
        msg: 日志消息模板
        *args: 消息格式化参数
        module: 模块名称
        
    Example:
        warning("警告信息", module="System")
    """
    logger = get_global_logger()
    logger.warning(msg, *args, module=module)
    
def error(msg: LogMessage, *args, module: ModuleName = None) -> None:
    """
    全局错误日志函数
    
    Args:
        msg: 日志消息模板
        *args: 消息格式化参数
        module: 模块名称
        
    Example:
        error("错误信息", module="MQTT")
    """
    logger = get_global_logger()
    logger.error(msg, *args, module=module)
    
def critical(msg: LogMessage, *args, module: ModuleName = None) -> None:
    """
    全局严重错误日志函数
    
    Args:
        msg: 日志消息模板
        *args: 消息格式化参数
        module: 模块名称
        
    Example:
        critical("严重错误", module="System")
    """
    logger = get_global_logger()
    logger.critical(msg, *args, module=module)