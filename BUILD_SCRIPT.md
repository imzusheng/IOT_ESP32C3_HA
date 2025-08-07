# MicroPython 项目构建和部署脚本详细文档

## 概述

本文档详细描述了 `build.py` 脚本的实现原理和功能特性，该脚本是一个专为 ESP32-C3 MicroPython 项目设计的高性能构建和部署工具。

## 架构设计

### 整体架构
```
build.py
├── 配置常量定义
├── 辅助函数模块
├── 核心功能模块
│   ├── 设备检测模块
│   ├── 编译模块
│   ├── 上传模块
│   └── 监控模块
└── 命令行接口模块
```

### 设计原则
1. **模块化设计**: 功能模块独立，便于维护和扩展
2. **容错机制**: 多重错误处理和恢复策略
3. **性能优化**: 缓存机制和智能同步
4. **用户体验**: 彩色日志和详细反馈
5. **跨平台支持**: Windows 和 Unix 系统兼容

## 配置常量详解

### 目录和文件配置
```python
# 源代码和目标目录
SRC_DIR = "src"                    # 源代码目录
DIST_DIR = "dist"                  # 编译输出目录

# 工具可执行文件
MPY_CROSS_EXECUTABLE = "mpy-cross"  # MicroPython 编译器
MPREMOTE_EXECUTABLE = "mpremote"   # MicroPython 远程工具

# 编译排除文件
NO_COMPILE_FILES = ['boot.py', 'main.py']  # 不编译的文件列表
DEFAULT_EXCLUDE_DIRS = ['tests']           # 默认排除的目录
```

### 缓存系统配置
```python
# 缓存文件
PORT_CACHE_FILE = ".port_cache"            # 端口缓存文件
UPLOAD_CACHE_FILE = ".upload_cache.json"   # 上传缓存文件

# 排除模式
EXCLUDE_PATTERNS = [
    "__pycache__",     # Python 缓存目录
    "*.pyc",          # Python 字节码文件
    "*.pyo",          # Python 优化文件
    ".DS_Store",      # macOS 系统文件
    "Thumbs.db",      # Windows 缩略图文件
    PORT_CACHE_FILE,  # 端口缓存文件
    UPLOAD_CACHE_FILE # 上传缓存文件
]
```

### 设备识别配置
```python
# ESP32 设备 VID/PID 模式
ESP32_VID_PID_PATTERNS = [
    (0x303A, 0x1001),  # Espressif 官方芯片
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH343
    (0x0403, 0x6001),  # FTDI 芯片
]

# 设备关键词
ESP32_KEYWORDS = [
    'esp32', 'cp210', 'ch340', 'ch343', 
    'usb to uart', 'serial'
]
```

## 核心功能实现

### 1. 日志系统

#### print_message 函数
```python
def print_message(message, msg_type="INFO"):
    """格式化打印消息
    
    参数:
        message: 消息内容
        msg_type: 消息类型 (INFO, SUCCESS, WARNING, ERROR, HEADER)
    
    功能:
        - 时间戳格式化 (HH:MM:SS)
        - 彩色输出 (ANSI 颜色代码)
        - 消息类型标准化
    """
```

**颜色映射表**:
- INFO: 蓝色 (93m)
- SUCCESS: 绿色 (92m)
- WARNING: 黄色 (93m)
- ERROR: 红色 (91m)
- HEADER: 紫色 (95m)
- RESET: 重置 (0m)

### 2. 缓存管理系统

#### MD5 哈希计算
```python
def get_file_md5(file_path):
    """计算文件的MD5哈希值
    
    实现细节:
        - 使用 hashlib.md5()
        - 分块读取 (4KB chunks)
        - 支持大文件处理
        - 返回十六进制字符串
    """
```

#### 缓存文件操作
```python
def load_cache(cache_file):
    """加载JSON缓存文件
    
    功能:
        - 文件存在性检查
        - JSON 解析
        - 错误处理 (损坏文件)
        - 返回空字典作为默认值
    """

def save_cache(cache_data, cache_file):
    """保存数据到JSON缓存文件
    
    功能:
        - JSON 格式化输出 (indent=4)
        - UTF-8 编码
        - IO 错误处理
    """
```

### 3. 设备检测系统

#### detect_esp32_port 函数
```python
def detect_esp32_port():
    """自动检测ESP32设备端口
    
    流程:
        1. 检查端口缓存
        2. 验证缓存的端口
        3. 扫描所有可用串口
        4. 基于 VID/PID 和关键词过滤
        5. 单设备自动选择，多设备交互选择
        6. 更新端口缓存
    
    返回:
        str: 设备端口路径 或 None
    """
```

**设备识别算法**:
1. **VID/PID 匹配**: 遍历预定义的 (VID, PID) 元组
2. **关键词匹配**: 在设备描述中搜索关键词
3. **优先级**: VID/PID 匹配 > 关键词匹配

**端口验证机制**:
```python
# 使用 pyserial 验证端口可访问性
with serial.Serial(cached_port) as ser:
    # 端口可用性测试
    pass
```

### 4. 工具检查系统

#### check_tool 函数
```python
def check_tool(executable):
    """检查工具是否可用
    
    参数:
        executable: 工具名称
    
    实现:
        - mpy-cross: --version 参数
        - mpremote: version 参数
        - 超时处理 (5秒)
        - 错误提示和安装建议
    """
```

### 5. 命令执行系统

#### execute_mpremote_command 函数
```python
def execute_mpremote_command(port, *cmd_args, timeout=60):
    """执行 mpremote 命令并返回结果
    
    参数:
        port: 设备端口
        cmd_args: 命令参数
        timeout: 超时时间
    
    返回:
        tuple: (returncode, stdout, stderr)
    
    功能:
        - 命令构建和执行
        - 输出捕获 (stdout/stderr)
        - 超时处理
        - 错误处理
    """
```

**命令构建模式**:
```python
command = [MPREMOTE_EXECUTABLE, 'connect', port, *cmd_args]
# 示例: ['mpremote', 'connect', 'COM3', 'fs', 'ls']
```

### 6. 编译系统

#### compile_project 函数
```python
def compile_project(verbose=False, exclude_dirs=None):
    """编译项目文件
    
    流程:
        1. 验证源目录存在
        2. 清理和创建目标目录
        3. 递归遍历源目录
        4. 过滤排除文件和目录
        5. 编译 .py 文件为 .mpy
        6. 复制不编译的文件
        7. 统计和报告
    
    返回:
        bool: 编译成功/失败
    """
```

**文件处理逻辑**:
```python
for file in files:
    if file.endswith('.py') and file not in NO_COMPILE_FILES:
        # 编译为 .mpy
        subprocess.run([MPY_CROSS_EXECUTABLE, "-o", target_file, src_file])
    else:
        # 直接复制
        shutil.copy2(src_file, target_file)
```

### 7. 设备准备系统

#### prepare_device 函数
```python
def prepare_device(port, verbose=False):
    """通过发送 resume 命令来准备设备
    
    机制:
        1. 发送 resume 命令 (Ctrl+B + Ctrl+C)
        2. 中断正在运行的脚本
        3. 验证设备响应
        4. 重试机制 (最多2次)
    
    返回:
        bool: 准备成功/失败
    """
```

**设备恢复策略**:
```python
# 第一次尝试: resume 命令
execute_mpremote_command(port, "resume")

# 第二次尝试: exec pass 命令
execute_mpremote_command(port, "exec", "pass")
```

### 8. 设备清理系统

#### clean_device 函数
```python
def clean_device(port):
    """清空设备上的所有文件和文件夹
    
    实现:
        1. 执行清理脚本
        2. 递归删除所有文件和目录
        3. 异常处理 (跳过无法删除的文件)
        4. 超时处理 (120秒)
    
    清理脚本:
        - 使用 MicroPython 的 os 模块
        - 递归遍历文件系统
        - 删除文件和目录
    """
```

**清理脚本实现**:
```python
CLEAN_SCRIPT = """
import os
def clean(path='/'):
    for item in os.listdir(path):
        item_path = f"{path}/{item}" if path != '/' else f"/{item}"
        try:
            is_dir = os.stat(item_path)[0] & 0x4000
            if is_dir:
                clean(item_path)
                os.rmdir(item_path)
            else:
                os.remove(item_path)
        except Exception:
            pass
clean()
"""
```

### 9. 文件上传系统

#### upload_file 函数
```python
def upload_file(port, local_path, remote_path):
    """上传单个文件并验证
    
    流程:
        1. 执行上传命令
        2. 验证文件存在
        3. 返回结果状态
    
    验证机制:
        - 使用 os.path.exists() 而非 ls
        - 避免 OSError: 20 错误
        - 脚本返回码验证
    """
```

**验证脚本**:
```python
verify_script = f"import os, sys; sys.exit(0) if os.path.exists('{remote_path.lstrip('/')}') else sys.exit(1)"
```

#### upload_directory 函数
```python
def upload_directory(port, dist_dir, verbose=False, force_full_upload=False):
    """上传目录，支持智能同步
    
    功能:
        1. MD5 哈希比较
        2. 智能文件同步
        3. 目录结构创建
        4. 上传状态跟踪
    
    智能同步算法:
        - 加载上传缓存
        - 计算文件 MD5
        - 比较缓存哈希值
        - 仅上传变更文件
        - 更新缓存
    """
```

**目录创建逻辑**:
```python
# 按层级排序创建目录
sorted_dirs = sorted(list(dirs_to_create), key=lambda p: len(p.parts))
for d in sorted_dirs:
    remote_dir_target = d.as_posix()
    execute_mpremote_command(port, "fs", "mkdir", remote_dir_target)
    # 忽略 "File exists" 错误
```

### 10. 设备控制系统

#### reset_device 函数
```python
def reset_device(port):
    """重置设备
    
    实现:
        - 发送 reset 命令
        - 等待设备重启 (2秒)
        - 错误处理
    """
```

#### start_interactive_repl 函数
```python
def start_interactive_repl(port):
    """启动独立的交互式REPL会话
    
    功能:
        - 启动 mpremote repl
        - 处理键盘中断
        - 错误处理
    """
```

#### monitor_device 函数
```python
def monitor_device(port):
    """启动设备输出监控
    
    功能:
        - 启动 mpremote monitor
        - 处理键盘中断
        - 错误处理
    """
```

## 命令行接口

### 参数解析器配置
```python
parser = argparse.ArgumentParser(
    description="MicroPython 高性能构建和部署脚本 (v4.5 - mpremote)",
    formatter_class=argparse.RawTextHelpFormatter,
    epilog="""使用示例:
  python %(prog)s                # 默认: 编译, 上传, 然后监控设备
  python %(prog)s -c             # 仅编译
  python %(prog)s -u             # 仅上传 (智能同步)
  python %(prog)s -u --clean     # 清理设备后，再进行智能同步上传
  python %(prog)s --clean --full-upload # 清理设备后，再进行强制全量上传
  python %(prog)s -r             # 仅连接并进入交互式REPL
  python %(prog)s -m             # 仅连接并监控设备输出
  python %(prog)s -p COM3        # 指定端口
"""
)
```

### 参数定义
```python
# 互斥参数组
group = parser.add_mutually_exclusive_group()
group.add_argument("-c", "--compile", action="store_true", help="仅编译 src 目录到 dist")
group.add_argument("-u", "--upload", action="store_true", help="仅上传 dist 目录到设备")
group.add_argument("-r", "--repl", action="store_true", help="仅连接并进入交互式REPL")
group.add_argument("-m", "--monitor", action="store_true", help="仅连接并监控设备输出")

# 通用参数
parser.add_argument("-p", "--port", type=str, help="指定设备端口")
parser.add_argument("-v", "--verbose", action="store_true", help="显示详细的调试输出")
parser.add_argument("--no-reset", action="store_true", help="上传后不重置设备")
parser.add_argument("--clean", action="store_true", help="上传前清空设备上的所有文件")
parser.add_argument("--full-upload", action="store_true", help="强制全量上传，忽略缓存")
```

### 流程控制逻辑

#### 编译流程
```python
if args.compile:
    print_message("--- 开始编译 ---", "HEADER")
    if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
    if not compile_project(args.verbose): sys.exit(1)
    print_message("编译完成。", "SUCCESS")
    return
```

#### 设备操作判断
```python
is_device_action = args.upload or args.repl or args.monitor or args.clean or \
                   (not args.compile and not args.repl and not args.monitor)
if not is_device_action:
    parser.print_help()
    return
```

#### 上传流程
```python
if is_upload_action:
    # 默认流程需要先编译
    if not args.upload:
        print_message("--- 开始编译 ---", "HEADER")
        if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
        if not compile_project(args.verbose): sys.exit(1)

    print_message("--- 开始部署 ---", "HEADER")
    if not os.path.isdir(DIST_DIR) or not os.listdir(DIST_DIR):
        print_message(f"'{DIST_DIR}' 目录不存在或为空。请先运行编译。", "ERROR")
        sys.exit(1)
    
    # 设备准备
    if not prepare_device(device_port, args.verbose):
        print_message("无法准备设备，部署中止。", "ERROR")
        sys.exit(1)

    # 设备清理
    if args.clean:
        if not clean_device(device_port):
            print_message("设备清理失败，部署中止。", "ERROR")
            sys.exit(1)
            
    # 文件上传
    if not upload_directory(device_port, DIST_DIR, args.verbose, args.full_upload):
        print_message("部署因文件上传失败而中止。", "ERROR")
        sys.exit(1)
    
    # 设备重置
    if not args.no_reset:
        reset_device(device_port)
    
    # 默认流程上传后进入监控模式
    if not args.upload and not args.clean:
        monitor_device(device_port)
```

## 错误处理机制

### 1. 工具检查错误
```python
try:
    subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=5)
except FileNotFoundError:
    print_message(f"命令未找到: {executable}", "ERROR")
    # 提供安装建议
except subprocess.CalledProcessError:
    print_message(f"命令执行失败: {executable}", "ERROR")
except subprocess.TimeoutExpired:
    print_message(f"命令超时: {executable}", "ERROR")
```

### 2. 设备连接错误
```python
except serial.SerialException:
    print_message("串口连接失败", "ERROR")
    # 端口可能被占用或不存在
```

### 3. 文件操作错误
```python
except IOError as e:
    print_message(f"文件操作错误: {e}", "ERROR")
    # 磁盘空间不足或权限问题
```

### 4. 缓存错误
```python
except json.JSONDecodeError:
    print_message("缓存文件损坏，将重新创建", "WARNING")
    # 损坏的缓存文件
```

## 性能优化策略

### 1. 缓存机制
- **端口缓存**: 记录成功连接的端口，避免重复扫描
- **上传缓存**: 基于 MD5 哈希的文件变更检测
- **智能同步**: 仅上传变更的文件

### 2. 并行处理
- **批量文件操作**: 同时处理多个文件
- **异步命令执行**: 非阻塞的设备命令

### 3. 内存优化
- **分块文件读取**: 大文件分块处理，避免内存溢出
- **流式处理**: 实时处理命令输出

## 跨平台兼容性

### 1. Windows 特殊处理
```python
if sys.platform == "win32":
    try:
        os.system("chcp 65001 > nul")  # 设置 UTF-8 代码页
    except Exception as e:
        print_message(f"设置Windows代码页失败: {e}", "WARNING")
```

### 2. 路径处理
- **路径分隔符**: 使用 `os.path.join()` 处理路径
- **绝对路径**: 支持相对路径和绝对路径
- **路径标准化**: 统一路径格式

### 3. 串口处理
- **端口名称**: Windows (COMx) vs Unix (/dev/tty*)
- **权限处理**: Unix 系统的设备权限

## 使用示例

### 1. 开发工作流
```bash
# 1. 编译项目
python build.py -c

# 2. 上传到设备
python build.py -u

# 3. 监控设备
python build.py -m
```

### 2. 完整部署
```bash
# 1. 清理设备并全量上传
python build.py --clean --full-upload

# 2. 标准部署流程
python build.py

# 3. 指定端口部署
python build.py -p COM3
```

### 3. 调试工作流
```bash
# 1. 进入 REPL 调试
python build.py -r

# 2. 详细输出模式
python build.py --verbose

# 3. 仅编译测试
python build.py -c --verbose
```

## 扩展性设计

### 1. 配置扩展
- **环境变量**: 支持通过环境变量覆盖配置
- **配置文件**: 支持外部配置文件
- **命令行参数**: 灵活的参数组合

### 2. 功能扩展
- **插件系统**: 支持自定义插件
- **钩子函数**: 预处理和后处理钩子
- **模块化**: 功能模块可独立扩展

### 3. 平台扩展
- **新芯片支持**: 添加新的 VID/PID 模式
- **新工具支持**: 集成其他 MicroPython 工具
- **新协议支持**: 支持其他通信协议

## 故障排除

### 1. 常见问题
- **端口检测失败**: 检查驱动安装和设备连接
- **编译失败**: 确认 mpy-cross 安装和版本
- **上传失败**: 检查设备状态和权限
- **缓存损坏**: 删除缓存文件重新运行

### 2. 调试技巧
- **详细模式**: 使用 --verbose 参数
- **单步执行**: 分别执行编译和上传
- **手动验证**: 使用 mpremote 手动验证

### 3. 性能调优
- **缓存清理**: 定期清理缓存文件
- **并行处理**: 启用并行文件操作
- **网络优化**: 优化网络连接参数

## 总结

这个 `build.py` 脚本是一个功能完整、设计精良的 MicroPython 项目构建和部署工具。它通过模块化设计、完善的错误处理、智能的缓存机制和友好的用户界面，为 ESP32-C3 项目的开发和部署提供了完整的解决方案。

脚本的核心优势在于：
1. **稳定可靠**: 多重错误处理和恢复机制
2. **高效性能**: 智能同步和缓存优化
3. **用户友好**: 彩色日志和详细反馈
4. **易于扩展**: 模块化设计和配置化参数
5. **跨平台**: Windows 和 Unix 系统兼容

通过本文档的详细说明，开发者可以完全理解脚本的工作原理，并能够根据需要进行定制和扩展。