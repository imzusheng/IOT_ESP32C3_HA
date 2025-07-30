import os
import sys
import subprocess
import time
import serial
from pathlib import Path
import argparse
import shutil
import fileinput

# --- 配置区 ---
SRC_DIR = 'micropython_src'
DIST_DIR = 'dist'
DEFAULT_BAUD_RATE = 115200
MPY_CROSS_EXECUTABLE = 'mpy-cross'

# --- 工具函数 ---

def clean_local_dist():
    """删除本地的 dist 文件夹。"""
    dist_path = Path(DIST_DIR)
    if dist_path.exists():
        print(f"🗑️  正在清除旧的输出目录: {DIST_DIR}")
        try:
            shutil.rmtree(dist_path)
            print(f"✅  目录 '{DIST_DIR}' 已成功删除。")
        except OSError as e:
            print(f"❌ 错误: 删除目录 '{DIST_DIR}' 失败: {e}")
            sys.exit(1)

def compile_files(mode='dev'):
    """
    递归编译源文件到 dist 目录。
    - dev 模式: 保留 print 日志。
    - prod 模式: 开启优化，移除日志和断言。
    """
    clean_local_dist()
    print("="*50 + f"\n🚀 步骤 1: 开始交叉编译源文件 (模式: {mode.upper()})...\n" + "="*50)
    
    src_path, dist_path = Path(SRC_DIR), Path(DIST_DIR)
    config_py_path = src_path / 'lib' / 'config.py'
    config_py_backup_path = config_py_path.with_suffix('.py.bak')

    if not src_path.exists():
        print(f"❌ 错误: 源文件目录 '{SRC_DIR}' 不存在！"); return False
    dist_path.mkdir(parents=True, exist_ok=True)
    
    # 备份并根据模式修改 config.py 中的 DEBUG 标志
    if not config_py_path.exists():
        print(f"🟡 警告: 未找到 '{config_py_path}'，无法设置 DEBUG 模式。");
    else:
        shutil.copy(config_py_path, config_py_backup_path)
        print(f"  - 备份 config.py -> {config_py_backup_path.name}")
        try:
            print(f"  - 正在设置 DEBUG = {'True' if mode == 'dev' else 'False'}...")
            with fileinput.FileInput(config_py_path, inplace=True) as file:
                for line in file:
                    if line.strip().startswith('DEBUG ='):
                        print(f"DEBUG = {'True' if mode == 'dev' else 'False'}", end='\n')
                    else:
                        print(line, end='')
        except Exception as e:
            print(f"❌ 错误: 修改 '{config_py_path}' 失败: {e}")
            shutil.move(config_py_backup_path, config_py_path) # 出错时恢复
            return False

    # 开始编译
    try:
        source_files = list(src_path.rglob('*.py'))
        if not source_files:
            print("🟡 警告: 没有在源目录中找到任何 .py 文件。"); return True

        for py_path in source_files:
            relative_path = py_path.relative_to(src_path)
            mpy_path = dist_path / relative_path.with_suffix('.mpy')
            mpy_path.parent.mkdir(parents=True, exist_ok=True)
            
            command = [MPY_CROSS_EXECUTABLE]
            if mode == 'prod':
                command.append('-O1') # 添加优化级别
            command.extend([str(py_path), '-o', str(mpy_path)])

            try:
                print(f"  - 编译中: {relative_path}")
                subprocess.run(command, check=True, capture_output=True, text=True)
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                print(f"❌ 错误: 编译 {relative_path} 失败。")
                print(f"  请确保 '{MPY_CROSS_EXECUTABLE}' 已安装并位于系统 PATH 中。")
                if hasattr(e, 'stderr'): print(f"  错误信息: {e.stderr}")
                return False
        print("\n✅ 编译成功完成！\n")
        return True
    finally:
        # 无论编译成功与否，都恢复原始的 config.py
        if config_py_backup_path.exists():
            shutil.move(config_py_backup_path, config_py_path)
            print(f"  - 已恢复原始 config.py 文件。")


def detect_serial_port():
    """自动检测可用的串口号。"""
    import serial.tools.list_ports
    ports = serial.tools.list_ports.comports()
    keywords = ['usb', 'serial', 'ch340', 'cp210', 'ftdi', 'micropython', 'uart']
    return [p.device for p in ports if any(k in (p.description or '').lower() for k in keywords)]


class MicroPythonFlasher:
    """封装与 MicroPython 设备交互的核心逻辑"""
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"\n✅ 成功连接到设备: {self.port}")
            return True
        except serial.SerialException as e:
            print(f"❌ 错误: 无法打开串口 {self.port}。请检查设备连接。错误: {e}")
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def enter_raw_repl(self):
        self.ser.write(b'\r\x03\x03'); time.sleep(0.2)
        self.ser.write(b'\r\x01'); time.sleep(0.2)
        self.ser.read_all()
        
    def exit_raw_repl(self):
        self.ser.write(b'\r\x02'); time.sleep(0.2)
        self.ser.read_all()

    def remote_exec(self, command, timeout=10):
        command_bytes = command.encode('utf-8')
        self.ser.write(command_bytes)
        self.ser.write(b'\x04')
        response = b''
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
                if response.endswith(b'>'): break
            time.sleep(0.01)
        if not response.startswith(b'OK'):
            raise IOError(f"远程命令执行失败: {response.decode('utf-8', 'ignore')}")
        return response[2:response.find(b'\x04')].strip()

    def wipe_filesystem(self):
        print("\n" + "="*50 + "\n💣 步骤 2: 开始清空设备文件系统...\n" + "="*50)
        self.enter_raw_repl()
        try:
            wipe_script = """
import os
def wipe(path='/'):
    try: items = os.listdir(path)
    except OSError: return
    for item in items:
        full_path = f"{path}/{item}" if path != '/' else f"/{item}"
        try:
            is_dir = (os.stat(full_path)[0] & 0x4000) != 0
            if is_dir: wipe(full_path)
            else: os.remove(full_path); print(f"Deleted file: {full_path}")
        except: pass
    if path != '/':
        try: os.rmdir(path); print(f"Deleted dir: {path}")
        except: pass
wipe('/')
print('Wipe finished.')
"""
            self.remote_exec(wipe_script)
            print("\n✅ 设备文件系统已完全清空。")
        except IOError as e:
            print(f"❌ 清空设备时出错: {e}")
        finally:
            self.exit_raw_repl()

    def upload(self, source_upload=False):
        """根据模式上传文件 (.py 或 .mpy)"""
        
        # 根据模式确定上传源和文件类型
        if source_upload:
            print("\n" + "="*50 + "\n🚀 步骤 3: 开始上传源代码 (.py)...\n" + "="*50)
            base_path = Path(SRC_DIR)
            files_to_upload = list(base_path.rglob('*.py'))
        else: # 默认编译模式
            print("\n" + "="*50 + "\n🚀 步骤 3: 开始上传编译文件 (.mpy)...\n" + "="*50)
            base_path = Path(DIST_DIR)
            files_to_upload = list(base_path.rglob('*.mpy'))
        
        # 无论何种模式，都上传 config.json
        config_json_path = Path(SRC_DIR) / 'config.json'
        if config_json_path.exists(): files_to_upload.append(config_json_path)

        # 1. 创建所有需要的目录
        self.enter_raw_repl()
        try:
            print("  - 正在创建远程目录...")
            remote_dirs = set()
            for p in files_to_upload:
                parent = p.relative_to(Path(SRC_DIR) if p.name == 'config.json' else base_path).parent
                if str(parent) != '.': remote_dirs.add(str(parent).replace('\\', '/'))
            for d in sorted(list(remote_dirs)):
                 self.remote_exec(f"try: import os; os.mkdir('/{d}')\nexcept: pass")
            print("  - 目录创建完成。")
        finally:
            self.exit_raw_repl()

        # 2. 上传文件
        for file_path in files_to_upload:
            is_config = file_path.name == 'config.json'
            remote_path = ('/config.json' if is_config 
                           else '/' + str(file_path.relative_to(base_path)).replace('\\', '/'))
            print(f"  - 上传中: {file_path.name} -> {remote_path}")
            with open(file_path, 'rb') as f: content = f.read()
            self.enter_raw_repl()
            try:
                self.remote_exec(f"f = open('{remote_path}', 'wb')")
                chunk_size = 256
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i+chunk_size]
                    self.remote_exec(f"f.write({repr(chunk)})")
                self.remote_exec("f.close()")
            finally:
                self.exit_raw_repl()
        print("\n✅ 所有文件上传成功！")

    def soft_reboot(self):
        print("\n🔄 正在软重启设备...")
        try:
            self.ser.write(b'\x04')
            time.sleep(1)
            output = self.ser.read_all().decode('utf-8', errors='ignore')
            print(output)
            print("✨ 设备已重启。")
        except serial.SerialException as e:
            print(f"🟡 重启时串口断开 (这是正常现象): {e}")


def main():
    parser = argparse.ArgumentParser(
        description='MicroPython 代码编译和部署工具 (v6 - 支持源码上传)',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--mode', type=str, choices=['dev', 'prod'], default='dev',
        help="编译模式 (仅在上传编译文件时有效):\n"
             "  dev  - 开发模式，保留日志打印 (默认)\n"
             "  prod - 生产模式，移除日志并优化"
    )
    parser.add_argument(
        '--source', action='store_true',
        help="上传 .py 源代码而不是编译后的 .mpy 文件。\n"
             "使用此标志将忽略 --mode 参数。"
    )
    parser.add_argument('-p', '--port', type=str, help='指定串口号 (例如: COM3, /dev/ttyUSB0)')
    parser.add_argument('-b', '--baud', type=int, default=DEFAULT_BAUD_RATE, help=f'波特率 (默认: {DEFAULT_BAUD_RATE})')
    parser.add_argument('--list-ports', action='store_true', help='列出所有可用串口')
    parser.add_argument('--compile-only', action='store_true', help='仅编译，不上传')
    args = parser.parse_args()

    if args.list_ports:
        ports = detect_serial_port()
        if not ports: print("未找到任何兼容的串口设备。")
        else: print("可用串口:"); [print(f"  - {p}") for p in ports]
        return

    # 如果不是源码上传模式，则执行编译
    if not args.source:
        if not compile_files(args.mode): sys.exit(1)
        if args.compile_only: print("✅ 编译完成，跳过上传步骤。"); return
    else:
        print(" ஸ  源码上传模式，跳过编译步骤。")

    if args.compile_only and args.source:
        print("🟡 警告: --compile-only 和 --source 参数冲突，将不执行任何操作。")
        return

    # ... (选择串口的逻辑保持不变)
    port = args.port
    if not port:
        ports = detect_serial_port()
        if not ports: print("❌ 错误: 未检测到串口设备。"); sys.exit(1)
        elif len(ports) == 1: port = ports[0]; print(f"🔍 自动检测到串口: {port}")
        else:
            print("🔍 检测到多个串口:"); [print(f"  {i+1}. {p}") for i, p in enumerate(ports)]
            try:
                choice = int(input("请选择串口 (输入数字): ")) - 1
                if 0 <= choice < len(ports): port = ports[choice]
                else: print("❌ 无效选择"); sys.exit(1)
            except (ValueError, KeyboardInterrupt): print("\n❌ 操作取消"); sys.exit(1)

    flasher = MicroPythonFlasher(port, args.baud)
    if not flasher.connect(): sys.exit(1)
    
    try:
        flasher.wipe_filesystem()
        flasher.upload(source_upload=args.source)
        flasher.soft_reboot()
    except Exception as e:
        print(f"\n❌ 部署过程中发生严重错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        flasher.disconnect()

if __name__ == "__main__":
    main()