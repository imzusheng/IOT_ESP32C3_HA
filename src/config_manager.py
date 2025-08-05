# -*- coding: utf-8 -*-
"""
配置验证和管理模块

为ESP32C3设备提供增强的配置验证和管理功能：
- 配置完整性检查
- 配置参数验证
- 配置热重载支持
- 配置默认值管理
- 配置错误恢复

配置验证说明：
- 启动时完整验证
- 运行时动态验证
- 配置错误自动修复
- 配置优化建议
"""

import time
import gc
import ujson
import object_pool

# =============================================================================
# 配置验证规则
# =============================================================================

class ConfigRules:
    """配置验证规则"""
    
    # MQTT配置规则
    MQTT_CONFIG_RULES = {
        'broker': {
            'type': str,
            'required': True,
            'default': '192.168.1.2',
            'validator': lambda x: len(x) > 0 and isinstance(x, str)
        },
        'port': {
            'type': int,
            'required': True,
            'default': 1883,
            'validator': lambda x: isinstance(x, int) and 1 <= x <= 65535
        },
        'topic': {
            'type': str,
            'required': True,
            'default': 'lzs/esp32c3',
            'validator': lambda x: len(x) > 0 and isinstance(x, str)
        },
        'keepalive': {
            'type': int,
            'required': False,
            'default': 60,
            'validator': lambda x: isinstance(x, int) and 10 <= x <= 300
        }
    }
    
    # WiFi配置规则
    WIFI_CONFIG_RULES = {
        'networks': {
            'type': list,
            'required': True,
            'default': [],
            'validator': lambda x: isinstance(x, list) and len(x) > 0
        },
        'config': {
            'type': dict,
            'required': False,
            'default': {
                'timeout': 15,
                'scan_interval': 30,
                'retry_delay': 2,
                'max_attempts': 3
            },
            'validator': lambda x: isinstance(x, dict)
        }
    }
    
    # 守护进程配置规则
    DAEMON_CONFIG_RULES = {
        'config': {
            'type': dict,
            'required': False,
            'default': {
                'led_pins': [12, 13],
                'timer_id': 0,
                'monitor_interval': 5000,
                'temp_threshold': 65,
                'temp_hysteresis': 5,
                'memory_threshold': 80,
                'memory_hysteresis': 10,
                'max_error_count': 10,
                'safe_mode_cooldown': 60000
            },
            'validator': lambda x: isinstance(x, dict)
        },
        'wdt_enabled': {
            'type': bool,
            'required': False,
            'default': False,
            'validator': lambda x: isinstance(x, bool)
        },
        'wdt_timeout': {
            'type': int,
            'required': False,
            'default': 120000,
            'validator': lambda x: isinstance(x, int) and x > 0
        },
        'gc_force_threshold': {
            'type': int,
            'required': False,
            'default': 95,
            'validator': lambda x: isinstance(x, int) and 80 <= x <= 99
        }
    }
    
    # 系统配置规则
    SYSTEM_CONFIG_RULES = {
        'debug_mode': {
            'type': bool,
            'required': False,
            'default': False,
            'validator': lambda x: isinstance(x, bool)
        },
        'log_level': {
            'type': str,
            'required': False,
            'default': 'INFO',
            'validator': lambda x: x in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        },
        'main_loop_delay': {
            'type': int,
            'required': False,
            'default': 300,
            'validator': lambda x: isinstance(x, int) and 100 <= x <= 5000
        },
        'status_report_interval': {
            'type': int,
            'required': False,
            'default': 30,
            'validator': lambda x: isinstance(x, int) and 10 <= x <= 300
        },
        'auto_restart_enabled': {
            'type': bool,
            'required': False,
            'default': False,
            'validator': lambda x: isinstance(x, bool)
        }
    }
    
    # 设备配置规则
    DEVICE_CONFIG_RULES = {
        'name': {
            'type': str,
            'required': False,
            'default': 'ESP32C3-IOT',
            'validator': lambda x: isinstance(x, str) and len(x) > 0
        },
        'location': {
            'type': str,
            'required': False,
            'default': '未知位置',
            'validator': lambda x: isinstance(x, str)
        },
        'firmware_version': {
            'type': str,
            'required': False,
            'default': '1.0.0',
            'validator': lambda x: isinstance(x, str) and len(x) > 0
        }
    }
    
    # 完整配置规则
    FULL_CONFIG_RULES = {
        'mqtt': MQTT_CONFIG_RULES,
        'wifi': WIFI_CONFIG_RULES,
        'daemon': DAEMON_CONFIG_RULES,
        'system': SYSTEM_CONFIG_RULES,
        'device': DEVICE_CONFIG_RULES
    }

# =============================================================================
# 配置验证器类
# =============================================================================

class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        """初始化配置验证器"""
        self.rules = ConfigRules.FULL_CONFIG_RULES
        self.validation_history = []
        self.max_history = 10
        self.last_validation_time = 0
        self.validation_cache = object_pool.get_dict()
        
        print("[ConfigValidator] 配置验证器初始化完成")
    
    def validate_config(self, config: dict, section: str = None) -> dict:
        """验证配置"""
        try:
            current_time = time.time()
            
            # 使用缓存提高性能
            cache_key = f"{section}_{hash(str(config))}" if section else hash(str(config))
            if cache_key in self.validation_cache:
                cached_result = self.validation_cache[cache_key]
                if current_time - cached_result['timestamp'] < 60:  # 1分钟缓存
                    return cached_result['result']
            
            # 执行验证
            if section:
                result = self._validate_section(config, section)
            else:
                result = self._validate_full_config(config)
            
            # 缓存结果
            self.validation_cache[cache_key] = {
                'result': result,
                'timestamp': current_time
            }
            
            # 记录验证历史
            self._record_validation(section, result)
            
            return result
            
        except Exception as e:
            print(f"[ConfigValidator] 配置验证异常: {e}")
            return {'valid': False, 'errors': [f'验证异常: {e}'], 'warnings': []}
    
    def _validate_section(self, config: dict, section: str) -> dict:
        """验证配置段"""
        if section not in self.rules:
            return {'valid': False, 'errors': [f'未知配置段: {section}'], 'warnings': []}
        
        section_config = config.get(section, {})
        section_rules = self.rules[section]
        
        errors = []
        warnings = []
        validated_config = {}
        
        for key, rule in section_rules.items():
            validation_result = self._validate_field(key, section_config.get(key), rule)
            
            if validation_result['valid']:
                validated_config[key] = validation_result['value']
            else:
                errors.extend(validation_result['errors'])
                warnings.extend(validation_result['warnings'])
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'config': validated_config
        }
    
    def _validate_full_config(self, config: dict) -> dict:
        """验证完整配置"""
        errors = []
        warnings = []
        validated_config = {}
        
        for section, section_rules in self.rules.items():
            section_result = self._validate_section(config, section)
            
            validated_config[section] = section_result['config']
            errors.extend(section_result['errors'])
            warnings.extend(section_result['warnings'])
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'config': validated_config
        }
    
    def _validate_field(self, field_name: str, field_value, rule: dict) -> dict:
        """验证单个字段"""
        errors = []
        warnings = []
        
        # 检查必填字段
        if rule['required'] and field_value is None:
            errors.append(f'必填字段缺失: {field_name}')
            # 使用默认值
            field_value = rule['default']
        
        # 检查字段类型
        if field_value is not None and not isinstance(field_value, rule['type']):
            errors.append(f'字段类型错误: {field_name} 期望 {rule["type"].__name__}, 实际 {type(field_value).__name__}')
            # 尝试类型转换
            try:
                if rule['type'] == int:
                    field_value = int(field_value)
                elif rule['type'] == bool:
                    field_value = bool(field_value)
                elif rule['type'] == str:
                    field_value = str(field_value)
                elif rule['type'] == list:
                    field_value = list(field_value)
                elif rule['type'] == dict:
                    field_value = dict(field_value)
            except:
                field_value = rule['default']
        
        # 应用默认值
        if field_value is None:
            field_value = rule['default']
            warnings.append(f'使用默认值: {field_name} = {field_value}')
        
        # 验证字段值
        if field_value is not None and 'validator' in rule:
            try:
                if not rule['validator'](field_value):
                    errors.append(f'字段值无效: {field_name} = {field_value}')
                    field_value = rule['default']
            except Exception as e:
                errors.append(f'字段验证异常: {field_name} - {e}')
                field_value = rule['default']
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'value': field_value
        }
    
    def _record_validation(self, section: str, result: dict):
        """记录验证历史"""
        validation_record = {
            'section': section,
            'valid': result['valid'],
            'error_count': len(result['errors']),
            'warning_count': len(result['warnings']),
            'timestamp': time.time()
        }
        
        self.validation_history.append(validation_record)
        
        # 保持历史记录大小
        if len(self.validation_history) > self.max_history:
            self.validation_history.pop(0)
        
        self.last_validation_time = time.time()
    
    def get_validation_stats(self) -> dict:
        """获取验证统计"""
        total_validations = len(self.validation_history)
        successful_validations = sum(1 for v in self.validation_history if v['valid'])
        
        return {
            'total_validations': total_validations,
            'successful_validations': successful_validations,
            'success_rate': successful_validations / total_validations if total_validations > 0 else 0,
            'recent_history': self.validation_history[-5:],
            'cache_size': len(self.validation_cache)
        }
    
    def clear_cache(self):
        """清空验证缓存"""
        self.validation_cache.clear()
        gc.collect()

# =============================================================================
# 配置管理器类
# =============================================================================

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = 'config.json'):
        """初始化配置管理器"""
        self.config_path = config_path
        self.validator = ConfigValidator()
        self.current_config = None
        self.last_load_time = 0
        self.watch_interval = 30000  # 30秒检查一次配置变化
        self.auto_reload = True
        
        print(f"[ConfigManager] 配置管理器初始化完成，配置文件: {config_path}")
    
    def load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                config = ujson.load(f)
            
            self.last_load_time = time.time()
            
            # 验证配置
            validation_result = self.validator.validate_config(config)
            
            if validation_result['valid']:
                self.current_config = validation_result['config']
                print("[ConfigManager] 配置加载并验证成功")
                
                # 显示警告
                if validation_result['warnings']:
                    print("[ConfigManager] 配置警告:")
                    for warning in validation_result['warnings']:
                        print(f"  - {warning}")
                
                return self.current_config
            else:
                print("[ConfigManager] 配置验证失败:")
                for error in validation_result['errors']:
                    print(f"  - {error}")
                
                # 尝试修复配置
                return self._repair_config(config, validation_result)
                
        except FileNotFoundError:
            print(f"[ConfigManager] 配置文件不存在: {self.config_path}")
            return self._create_default_config()
        except Exception as e:
            print(f"[ConfigManager] 配置加载失败: {e}")
            return self._create_default_config()
    
    def _repair_config(self, config: dict, validation_result: dict) -> dict:
        """修复配置"""
        print("[ConfigManager] 尝试修复配置...")
        
        # 使用验证后的配置
        repaired_config = validation_result['config']
        
        # 保存修复后的配置
        try:
            with open(self.config_path, 'w') as f:
                ujson.dump(repaired_config, f, indent=2)
            print("[ConfigManager] 配置修复完成并保存")
        except Exception as e:
            print(f"[ConfigManager] 配置保存失败: {e}")
        
        self.current_config = repaired_config
        return repaired_config
    
    def _create_default_config(self) -> dict:
        """创建默认配置"""
        print("[ConfigManager] 创建默认配置...")
        
        default_config = {}
        
        # 为每个配置段创建默认配置
        for section, section_rules in self.validator.rules.items():
            section_config = {}
            for field, rule in section_rules.items():
                section_config[field] = rule['default']
            default_config[section] = section_config
        
        # 保存默认配置
        try:
            with open(self.config_path, 'w') as f:
                ujson.dump(default_config, f, indent=2)
            print("[ConfigManager] 默认配置已保存")
        except Exception as e:
            print(f"[ConfigManager] 默认配置保存失败: {e}")
        
        self.current_config = default_config
        return default_config
    
    def reload_config(self) -> bool:
        """重新加载配置"""
        print("[ConfigManager] 重新加载配置...")
        
        old_config = self.current_config
        new_config = self.load_config()
        
        if new_config != old_config:
            print("[ConfigManager] 配置已更新")
            return True
        else:
            print("[ConfigManager] 配置未变化")
            return False
    
    def get_config(self, section: str = None, key: str = None, default=None):
        """获取配置值"""
        if self.current_config is None:
            self.current_config = self.load_config()
        
        if section is None:
            return self.current_config
        
        section_config = self.current_config.get(section, {})
        
        if key is None:
            return section_config
        
        return section_config.get(key, default)
    
    def set_config(self, section: str, key: str, value):
        """设置配置值"""
        if self.current_config is None:
            self.current_config = self.load_config()
        
        if section not in self.current_config:
            self.current_config[section] = {}
        
        self.current_config[section][key] = value
        
        # 验证新值
        validation_result = self.validator.validate_config(self.current_config, section)
        
        if validation_result['valid']:
            print(f"[ConfigManager] 配置更新成功: {section}.{key} = {value}")
            return True
        else:
            print(f"[ConfigManager] 配置更新失败: {validation_result['errors']}")
            return False
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        if self.current_config is None:
            return False
        
        try:
            with open(self.config_path, 'w') as f:
                ujson.dump(self.current_config, f, indent=2)
            print("[ConfigManager] 配置保存成功")
            return True
        except Exception as e:
            print(f"[ConfigManager] 配置保存失败: {e}")
            return False
    
    def watch_config_changes(self) -> bool:
        """检查配置变化"""
        if not self.auto_reload:
            return False
        
        try:
            file_time = time.time()
            # 这里应该检查文件修改时间，但MicroPython可能不支持
            # 简化实现：定期重新加载
            if file_time - self.last_load_time > self.watch_interval / 1000:
                return self.reload_config()
        except:
            pass
        
        return False
    
    def get_config_stats(self) -> dict:
        """获取配置统计"""
        return {
            'config_path': self.config_path,
            'last_load_time': self.last_load_time,
            'has_config': self.current_config is not None,
            'validation_stats': self.validator.get_validation_stats()
        }

# =============================================================================
# 全局配置管理器实例
# =============================================================================

# 创建全局配置管理器实例
_config_manager = ConfigManager()

def get_config_manager():
    """获取全局配置管理器实例"""
    return _config_manager

def load_config():
    """加载配置的便捷函数"""
    return _config_manager.load_config()

def get_config(section: str = None, key: str = None, default=None):
    """获取配置的便捷函数"""
    return _config_manager.get_config(section, key, default)

def set_config(section: str, key: str, value):
    """设置配置的便捷函数"""
    return _config_manager.set_config(section, key, value)

def save_config():
    """保存配置的便捷函数"""
    return _config_manager.save_config()

def reload_config():
    """重新加载配置的便捷函数"""
    return _config_manager.reload_config()

def get_config_stats():
    """获取配置统计的便捷函数"""
    return _config_manager.get_config_stats()

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()

print("[ConfigManager] 配置验证和管理模块加载完成")