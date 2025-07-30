# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文回答我

## Project Overview

This is a MicroPython-based IoT system for ESP32-C3 microcontrollers with a focus on temperature-adaptive optimization and modular architecture. The system features event-driven communication, dependency injection patterns, and robust hardware management.

## Common Development Commands

### Building and Deployment
```bash
# Deploy to device (compiles .py to .mpy and uploads)
python deploy.py

# Deploy without compilation (upload source files directly)
python deploy.py --no-compile

# The deploy script handles:
# - Compilation with mpy-cross
# - Automatic device detection
# - File upload via serial
# - Device restart
```

### Testing and Validation
```bash
# No formal test framework is used in this MicroPython project
# Validation is done through:
# - Serial monitoring during deployment
# - LED status indicators
# - System performance reports via daemon
# - Configuration validation at startup
```

## System Architecture

### Core Design Principles
- **Event-Driven Architecture**: All modules communicate through a lightweight event bus (`lib/core.py`)
- **Dependency Injection**: Modules receive dependencies (event_bus, config_getter) rather than importing them directly
- **Temperature-Adaptive Optimization**: System parameters dynamically adjust based on MCU temperature
- **Error Isolation**: Single module failures don't affect overall system stability
- **Configuration-Driven**: All system parameters loaded from JSON configuration file

### Key Modules and Responsibilities

#### `lib/core.py` - Event Bus Core
- Provides lightweight event publishing/subscription system
- Supports both synchronous and asynchronous event handling
- Automatic error recovery and callback cleanup
- Memory-optimized for MicroPython environment

#### `lib/config.py` - Configuration Management
- Centralized configuration system with JSON file support
- Event constants and logging level definitions
- Configuration validation and hot-reload capability
- Backward compatibility with legacy constant access patterns

#### `lib/daemon.py` - System Guardian
- Hardware watchdog management with configurable timeout
- Temperature monitoring and emergency safety mode
- Unified scheduler with dynamic interval adjustment
- Performance reporting and error management
- Restart loop protection to prevent infinite boot cycles

#### `lib/wifi.py` - WiFi Management
- State machine-based WiFi connection management
- Multi-network configuration with automatic failover
- Event-driven status notifications
- Temperature-adaptive retry intervals

#### `lib/ntp.py` - Time Synchronization
- Network time protocol synchronization
- Timezone offset handling
- Periodic sync with WiFi dependency
- Event-driven sync status reporting

#### `lib/led.py` - LED Control System
- PWM-based LED brightness control
- Multiple lighting effects (fast blink, slow blink, heartbeat, etc.)
- Asynchronous LED task management
- Temperature-adaptive brightness optimization

#### `lib/temp_optimizer.py` - Temperature Optimization
- MCU temperature monitoring and level classification
- Dynamic system parameter adjustment based on temperature
- Configuration optimization recommendations
- Event-based system coordination

#### `lib/logger.py` - Logging System
- Event-driven logging with configurable levels
- In-memory queue with periodic flushing
- Critical error handling and persistence

### System Flow and Data Models

#### Startup Sequence
1. `boot.py` - Initializes garbage collection
2. `main.py` - System coordinator:
   - Starts critical daemon (watchdog, monitoring)
   - Initializes event bus and configuration
   - Launches asynchronous tasks (WiFi, NTP, LED, business logic)
   - Coordinates temperature optimization

#### Event Communication
- All modules communicate through typed events with integer constants
- Events carry structured data via keyword arguments
- Automatic error isolation prevents callback failures from affecting publishers
- Performance-optimized with batch processing and memory management

#### Configuration System
- Single JSON file (`config.json`) contains all system parameters
- Structured configuration sections: wifi, led, daemon, safety, logging, general
- Runtime validation with meaningful error messages
- Hot-reload capability with change detection

#### Temperature Optimization Strategy
- **Normal** (< 40°C): Standard performance mode
- **Warm** (40-45°C): Light optimization (reduced PWM frequency)
- **Overheating** (45-50°C): Moderate optimization (brightness limits, longer intervals)
- **Danger** (> 50°C): Aggressive optimization (minimal functionality)

## Development Guidelines

### Module Development
- Use dependency injection pattern for all new modules
- Subscribe to relevant events rather than calling other modules directly
- Implement configuration validation for new parameters
- Add temperature optimization support for performance-critical features
- Use the event bus for all inter-module communication

### Event System Usage
```python
# Subscribe to events
def on_system_event(**kwargs):
    temperature = kwargs.get('temperature')
    # Handle event

core.subscribe('system_heartbeat', on_system_event)

# Publish events
core.publish('custom_event', data='value', status='active')
```

### Configuration Management
- Always use `config.get_config_value(section, key)` for configuration access
- Validate configuration at module initialization
- Subscribe to `config_update` events for runtime configuration changes
- Provide sensible defaults for all configuration parameters

### Error Handling
- Use try/catch blocks around all hardware operations
- Implement graceful degradation when non-critical features fail
- Log critical errors but avoid excessive logging in normal operation
- Use the event bus to notify other modules of error conditions

### Memory Optimization
- Use `micropython.const` for compile-time constants
- Implement periodic garbage collection in long-running tasks
- Avoid creating unnecessary objects in hot paths
- Use generators and iterators instead of lists where possible

## Hardware Considerations

### ESP32-C3 Specifics
- RISC-V architecture with limited memory (~400KB RAM)
- Single-core processor requiring careful task scheduling
- Built-in temperature sensor for monitoring
- Hardware watchdog for crash recovery

### Pin Configuration
- LED pins configured in `config.json` (default: pins 12 and 13)
- PWM frequency affects both power consumption and LED smoothness
- Temperature optimization automatically adjusts performance parameters

## Troubleshooting

### Common Issues
- **Deployment failures**: Check mpy-cross installation and serial port permissions
- **WiFi connection issues**: Verify network configuration and signal strength
- **System instability**: Monitor temperature and memory usage via daemon reports
- **Configuration errors**: Validate JSON syntax and required sections in config.json

### Debug Mode
- Enable `DEBUG = True` in `lib/config.py` for detailed logging
- Monitor serial output for system status and error information
- Use daemon performance reports for system health assessment