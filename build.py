#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MicroPython 项目构建和部署脚本 (v4.5 - 终极稳定版)

主要功能:
1.  [修复] 修正了文件上传后的验证逻辑，使用 os.path.exists 替代 ls，解决了 OSError: 20 错误。
2.  [修复] 修正了目录已存在时的错误判断逻辑。
3.  [修复] 采用更强大的 `resume` 命令来准备设备，解决顽固的“could not enter raw repl”错误。
4.  [简化] 完全移除了进度条功能，专注于核心部署逻辑。
5.  [重构] 使用官方工具 `mpremote` 替代 `rshell`，显著提升性能和稳定性。
6.  上传前可选择清空设备。
7.  智能同步：仅上传变更过的文件（基于MD5缓存）。
8.  支持端口自动检测和缓存。

作者: Gemini (基于 v4.4 版本修复)
日期: 2024
"""

import os
import shutil
import subprocess
import sys
import argparse
import time
import serial
import serial.tools.list_ports
import json
import hashlib
from pathlib import Path

# --- 配置常量 ---
SRC_DIR = "src"
DIST_DIR = "dist"
MPY_CROSS_EXECUTABLE = "mpy-cross"
MPREMOTE_EXECUTABLE = "mpremote"
NO_COMPILE_FILES = ['boot.py', 'main.py']
DEFAULT_EXCLUDE_DIRS = ['tests']

# 缓存文件
PORT_CACHE_FILE = ".port_cache"
UPLOAD_CACHE_FILE = ".upload_cache.json"

# 排除的文件和目录
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "Thumbs.db",
    PORT_CACHE_FILE,
    UPLOAD_CACHE_FILE
]

# ESP32 设备识别模式
ESP32_VID_PID_PATTERNS = [
    (0x303A, 0x1001),  # Espressif
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH343
    (0x0403, 0x6001),  # FTDI
]
ESP32_KEYWORDS = ['esp32', 'cp210', 'ch340', 'ch343', 'usb to uart', 'serial']

# --- 辅助函数 ---

def print_message(message, msg_type="INFO"):
    """格式化打印消息"""
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\033[92m",
        "WARNING": "\033[93m", "ERROR": "\033[91m",
        "HEADER": "\033[95m", "RESET": "\033[0m"
    }
    color = colors.get(msg_type.upper(), colors["INFO"])
    reset = colors["RESET"]
    timestamp = time.strftime("%H:%M:%S")
    print(f"{color}[{timestamp}] [{msg_type.upper()}] {message}{reset}")

def get_file_md5(file_path):
    """计算文件的MD5哈希值"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def load_cache(cache_file):
    """加载JSON缓存文件"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print_message(f"缓存文件 {cache_file} 已损坏，将重新创建。", "WARNING")
    return {}

def save_cache(cache_data, cache_file):
    """保存数据到JSON缓存文件"""
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
    except IOError as e:
        print_message(f"无法写入缓存文件 {cache_file}: {e}", "ERROR")

# --- 核心功能 ---

def detect_esp32_port():
    """自动检测ESP32设备端口 (带缓存功能)"""
    cached_port = load_cache(PORT_CACHE_FILE).get('port')
    if cached_port:
        print_message(f"从缓存中找到端口: {cached_port}", "INFO")
        try:
            with serial.Serial(cached_port) as ser:
                print_message(f"端口 {cached_port} 验证成功。", "SUCCESS")
                return cached_port
        except serial.SerialException:
            print_message(f"缓存的端口 {cached_port} 无效或无法访问。", "WARNING")

    print_message("正在扫描可用串口...", "INFO")
    ports = list(serial.tools.list_ports.comports())
    esp32_ports = []
    for port in ports:
        is_esp_port = False
        if port.vid and port.pid and (port.vid, port.pid) in ESP32_VID_PID_PATTERNS:
            is_esp_port = True
        if not is_esp_port and port.description and any(keyword in port.description.lower() for keyword in ESP32_KEYWORDS):
            is_esp_port = True
        if is_esp_port:
            esp32_ports.append(port)

    if not esp32_ports:
        print_message("未能自动识别出ESP32设备。", "ERROR")
        return None

    if len(esp32_ports) == 1:
        selected_port_dev = esp32_ports[0].device
        print_message(f"自动选择ESP32设备: {selected_port_dev} ({esp32_ports[0].description})", "SUCCESS")
    else:
        print_message(f"找到 {len(esp32_ports)} 个可能的ESP32设备:", "INFO")
        for i, port in enumerate(esp32_ports):
            print(f"  {i+1}. {port.device} - {port.description}")
        try:
            choice = input(f"请选择设备序号 (1-{len(esp32_ports)}): ").strip()
            index = int(choice) - 1
            selected_port_dev = esp32_ports[index].device
        except (ValueError, IndexError, KeyboardInterrupt):
            print_message("无效选择或已取消，将使用第一个设备。", "WARNING")
            selected_port_dev = esp32_ports[0].device
    
    save_cache({'port': selected_port_dev}, PORT_CACHE_FILE)
    print_message(f"已选择端口 {selected_port_dev} 并更新缓存。", "SUCCESS")
    return selected_port_dev

def check_tool(executable):
    """检查工具是否可用"""
    try:
        cmd = [executable, "version"] if executable == MPREMOTE_EXECUTABLE else [executable, "--version"]
        subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=5)
        print_message(f"{executable} 可用", "SUCCESS")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_message(f"检查 {executable} 时出错: {e}", "ERROR")
        if executable == MPY_CROSS_EXECUTABLE:
            print_message("请从 https://micropython.org/download/ 下载 mpy-cross", "ERROR")
        elif executable == MPREMOTE_EXECUTABLE:
            print_message("请使用 'pip install mpremote' 命令进行安装。", "ERROR")
        return False

def execute_mpremote_command(port, *cmd_args, timeout=60):
    """执行 mpremote 命令并返回结果"""
    command = [MPREMOTE_EXECUTABLE, 'connect', port, *cmd_args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True,
            timeout=timeout
        )
        return 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        print_message(f"命令未找到: {MPREMOTE_EXECUTABLE}. 请确保已安装并添加到系统路径中。", "ERROR")
        print_message("安装命令: pip install mpremote", "INFO")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip(), e.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"命令 '{' '.join(command)}' 执行超时 ({timeout}s)"

def compile_project(verbose=False, exclude_dirs=None):
    """编译项目文件"""
    if not os.path.exists(SRC_DIR):
        print_message(f"源码目录 {SRC_DIR} 不存在", "ERROR")
        return False
    if exclude_dirs is None: exclude_dirs = []
    if os.path.exists(DIST_DIR): shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)

    compiled_files, copied_files = 0, 0
    for root, dirs, files in os.walk(SRC_DIR, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d != '__pycache__']
        rel_dir = os.path.relpath(root, SRC_DIR)
        target_dir = os.path.join(DIST_DIR, rel_dir) if rel_dir != '.' else DIST_DIR
        os.makedirs(target_dir, exist_ok=True)

        for file in files:
            if any(file.endswith(p.strip('*')) for p in EXCLUDE_PATTERNS if p.startswith('*.')) or file in EXCLUDE_PATTERNS:
                continue
            src_file = os.path.join(root, file)
            if file.endswith('.py') and file not in NO_COMPILE_FILES:
                mpy_file = file.replace('.py', '.mpy')
                target_file = os.path.join(target_dir, mpy_file)
                try:
                    subprocess.run([MPY_CROSS_EXECUTABLE, "-o", target_file, src_file], check=True, capture_output=True, text=True, timeout=30)
                    if verbose: print_message(f"编译: {src_file} -> {target_file}", "SUCCESS")
                    compiled_files += 1
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print_message(f"编译失败 {file}: {e.stderr if hasattr(e, 'stderr') else e}", "ERROR")
                    return False
            else:
                target_file = os.path.join(target_dir, file)
                shutil.copy2(src_file, target_file)
                if verbose: print_message(f"复制: {src_file} -> {target_file}", "SUCCESS")
                copied_files += 1
    
    print_message(f"构建完成 - 编译: {compiled_files}, 复制: {copied_files}", "SUCCESS")
    return True

def prepare_device(port, verbose=False):
    """通过发送 resume 命令来中断任何正在运行的脚本，以准备设备。"""
    print_message("正在准备设备 (发送中断和恢复信号)...", "INFO")
    # 'resume' 命令会发送 Ctrl+B (退出裸 REPL) 和 Ctrl+C (中断程序)
    # 这是让繁忙设备恢复响应的最可靠方法。
    rc, stdout, stderr = execute_mpremote_command(port, "resume", timeout=20)
    if rc == 0:
        print_message("设备已准备就绪。", "SUCCESS")
        time.sleep(0.5)
        return True
    else:
        # 即使 resume 失败，也可能让设备进入了可接受命令的状态。
        # 我们再尝试一次简单的命令来确认。
        print_message("第一次准备尝试失败，正在重试...", "WARNING")
        if verbose: print_message(f"Stderr: {stderr}", "INFO")
        time.sleep(1)
        rc_retry, _, stderr_retry = execute_mpremote_command(port, "exec", "pass", timeout=20)
        if rc_retry == 0:
            print_message("设备在重试后准备就绪。", "SUCCESS")
            return True
        else:
            print_message(f"准备设备最终失败: {stderr_retry or stderr}", "ERROR")
            return False

def clean_device(port):
    """清空设备上的所有文件和文件夹"""
    print_message("--- 开始清理设备 ---", "HEADER")
    
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
    rc, stdout, stderr = execute_mpremote_command(port, "exec", CLEAN_SCRIPT, timeout=120)

    if rc == 0:
        print_message("设备清理完成。", "SUCCESS")
        return True
    else:
        print_message("设备清理失败。", "ERROR")
        print_message(f"错误信息: {stderr or stdout}", "ERROR")
        return False

def upload_file(port, local_path, remote_path):
    """上传单个文件并验证"""
    remote_target = ":" + remote_path.lstrip('/')
    
    rc, _, stderr = execute_mpremote_command(port, "cp", local_path, remote_target, timeout=60)
    if rc != 0:
        return 1, f"上传失败: {stderr}"

    # [FIX] 使用 os.path.exists() 进行验证，避免对文件使用 ls
    # 这个脚本如果路径存在则返回0，否则返回1
    verify_script = f"import os, sys; sys.exit(0) if os.path.exists('{remote_path.lstrip('/')}') else sys.exit(1)"
    rc_verify, _, stderr_verify = execute_mpremote_command(port, "exec", verify_script, timeout=20)

    if rc_verify == 0:
        return 0, ""
    else:
        return 1, f"验证失败: {stderr_verify or '文件在设备上未找到'}"

def upload_directory(port, dist_dir, verbose=False, force_full_upload=False):
    """上传目录，支持智能同步"""
    print_message("正在分析文件变更...", "INFO")
    upload_cache = {} if force_full_upload else load_cache(UPLOAD_CACHE_FILE)
    if force_full_upload:
        print_message("强制全量上传模式已启用，将忽略并覆盖现有缓存。", "WARNING")
    
    new_cache = {}
    files_to_upload = []

    for root, _, files in os.walk(dist_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, dist_dir)
            current_md5 = get_file_md5(local_path)
            if current_md5 != upload_cache.get(rel_path):
                files_to_upload.append((local_path, rel_path))
            new_cache[rel_path] = current_md5

    if not files_to_upload:
        print_message("所有文件均为最新，无需上传。", "SUCCESS")
        return True

    print_message(f"发现 {len(files_to_upload)} 个文件需要上传。", "INFO")

    dirs_to_create = set()
    for _, rel_path in files_to_upload:
        parent_dir = Path(rel_path).parent
        if str(parent_dir) != '.':
            dirs_to_create.add(parent_dir)

    if dirs_to_create:
        print_message("正在创建远程目录...", "INFO")
        sorted_dirs = sorted(list(dirs_to_create), key=lambda p: len(p.parts))
        for d in sorted_dirs:
            remote_dir_target = d.as_posix()
            if verbose: print_message(f"创建目录: :{remote_dir_target}", "INFO")
            rc, _, stderr = execute_mpremote_command(port, "fs", "mkdir", remote_dir_target)
            # [FIX] 检查 'File exists' 来正确处理目录已存在的情况
            if rc != 0 and 'File exists' not in stderr:
                 print_message(f"创建目录 :{remote_dir_target} 失败: {stderr}", "ERROR")
                 return False
    
    failed_uploads = []
    for local_path, rel_path in files_to_upload:
        remote_path = Path(rel_path).as_posix()
        print_message(f"正在上传: {rel_path} -> :{remote_path}", "INFO")
        
        returncode, stderr = upload_file(port, local_path, remote_path)
        if returncode != 0:
            failed_uploads.append((rel_path, stderr))
            msg = f"上传失败 {rel_path}: {stderr}"
            print_message(msg, "ERROR")

    if failed_uploads:
        print_message(f"上传完成，但有 {len(failed_uploads)} 个文件失败。", "ERROR")
        for file, err in failed_uploads: print(f"  - {file}: {err}")
        return False
    else:
        print_message(f"成功上传 {len(files_to_upload)} 个文件。", "SUCCESS")
        save_cache(new_cache, UPLOAD_CACHE_FILE)
        print_message("上传缓存已更新。", "INFO")
        return True

def reset_device(port):
    """重置设备"""
    print_message("正在重置设备...", "INFO")
    rc, _, stderr = execute_mpremote_command(port, "reset", timeout=15)
    if rc == 0:
        time.sleep(2) 
        print_message("设备已重置。", "SUCCESS")
    else:
        print_message(f"重置设备失败: {stderr}", "ERROR")

def start_interactive_repl(port):
    """启动独立的交互式REPL会话"""
    print_message("启动交互式 REPL (输入 Ctrl+] 退出)...", "INFO")
    try:
        subprocess.run([MPREMOTE_EXECUTABLE, "connect", port, "repl"])
    except KeyboardInterrupt:
        print_message("REPL 会话结束。", "INFO")
    except Exception as e:
        print_message(f"启动 REPL 失败: {e}", "ERROR")

def monitor_device(port):
    """启动设备输出监控"""
    print_message("开始监控设备输出 (按 Ctrl+C 停止)...", "INFO")
    try:
        subprocess.run([MPREMOTE_EXECUTABLE, "connect", port, "monitor"])
    except KeyboardInterrupt:
        print_message("\n监控会话结束。", "INFO")
    except Exception as e:
        print_message(f"启动监控失败: {e}", "ERROR")

# --- 主函数 ---

def main():
    parser = argparse.ArgumentParser(
        description="MicroPython 高性能构建和部署脚本 (v4.5 - mpremote)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
使用示例:
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
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--compile", action="store_true", help="仅编译 src 目录到 dist")
    group.add_argument("-u", "--upload", action="store_true", help="仅上传 dist 目录到设备 (可与 --clean, --full-upload 组合)")
    group.add_argument("-r", "--repl", action="store_true", help="仅连接并进入交互式REPL")
    group.add_argument("-m", "--monitor", action="store_true", help="仅连接并监控设备输出")
    
    parser.add_argument("-p", "--port", type=str, help="指定设备端口 (不指定则自动检测)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细的调试输出")
    parser.add_argument("--no-reset", action="store_true", help="上传后不重置设备")
    parser.add_argument("--clean", action="store_true", help="上传前清空设备上的所有文件")
    parser.add_argument("--full-upload", action="store_true", help="强制全量上传，忽略缓存 (需与-u或默认模式一同使用)")
    
    args = parser.parse_args()

    # --- 编译操作 ---
    if args.compile:
        print_message("--- 开始编译 ---", "HEADER")
        if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
        if not compile_project(args.verbose): sys.exit(1)
        print_message("编译完成。", "SUCCESS")
        return

    # --- 设备相关操作 ---
    is_device_action = args.upload or args.repl or args.monitor or args.clean or \
                       (not args.compile and not args.repl and not args.monitor)
    if not is_device_action:
        parser.print_help()
        return

    print_message("--- 连接设备 ---", "HEADER")
    if not check_tool(MPREMOTE_EXECUTABLE): sys.exit(1)
    device_port = args.port or detect_esp32_port()
    if not device_port: sys.exit(1)

    # 仅进入REPL
    if args.repl:
        start_interactive_repl(device_port)
        return

    # 仅监控
    if args.monitor:
        monitor_device(device_port)
        return

    # 上传或默认流程
    is_upload_action = args.upload or args.clean or (not args.compile and not args.repl and not args.monitor)
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
        
        try:
            # [FIX] 在执行任何文件系统操作前，先准备设备
            if not prepare_device(device_port, args.verbose):
                print_message("无法准备设备，部署中止。", "ERROR")
                sys.exit(1)

            if args.clean:
                if not clean_device(device_port):
                    print_message("设备清理失败，部署中止。", "ERROR")
                    sys.exit(1)
                    
            if not upload_directory(device_port, DIST_DIR, args.verbose, args.full_upload):
                print_message("部署因文件上传失败而中止。", "ERROR")
                sys.exit(1)
            
            if not args.no_reset:
                reset_device(device_port)
            
            # 默认流程上传后进入监控模式
            if not args.upload and not args.clean:
                monitor_device(device_port)

        except Exception as e:
            print_message(f"部署过程中发生严重错误: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print_message("所有任务已成功完成！", "SUCCESS")

if __name__ == "__main__":
    # [FIX] 强制Windows控制台使用UTF-8代码页
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 > nul")
        except Exception as e:
            print_message(f"尝试设置Windows代码页失败: {e}", "WARNING")
    
    try:
        main()
    except KeyboardInterrupt:
        print_message("\n用户中断操作。", "WARNING")
        sys.exit(1)
    except Exception as e:
        import traceback
        print_message(f"脚本执行时发生未捕获的异常: {e}", "ERROR")
        traceback.print_exc()
        sys.exit(1)
