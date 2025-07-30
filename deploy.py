# deploy.py (v4.0 - 智能部署版)
import sys
import time
import serial
import serial.tools.list_ports
import os
import shutil
import subprocess
from base64 import b64encode

# --- 配置区 ---
SOURCE_DIR = "micropython_src"
BUILD_DIR = "dist"
MPY_CROSS_CMD = "mpy-cross"  # 如果mpy-cross不在系统PATH中，请提供其完整路径

# --- 核心功能实现 ---

class PyboardError(Exception):
    """自定义异常，用于表示与开发板通信时发生的错误"""
    pass

class Pyboard:
    """一个健壮的类，用于处理与MicroPython开发板的底层通信。"""
    def __init__(self, port, baudrate=115200):
        try:
            self.serial = serial.Serial(port, baudrate=baudrate, timeout=1)
        except serial.SerialException as e:
            raise PyboardError(f"无法打开串口 {port}: {e}")

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()

    def read_until(self, min_len, ending, timeout=10):
        data = self.serial.read(min_len)
        start_time = time.time()
        while time.time() - start_time < timeout:
            if data.endswith(ending):
                break
            new_data = self.serial.read(1)
            if new_data:
                data += new_data
            else:
                time.sleep(0.01)
        return data

    def exec_raw(self, command, timeout=10, quiet=False):
        command_bytes = command.encode('utf-8')
        self.serial.write(command_bytes)
        self.serial.write(b'\x04') # Ctrl+D to execute
        
        response = self.read_until(2, b'>', timeout)
        if not response.endswith(b'>'):
             raise PyboardError(f"执行命令失败，未收到 '>' 提示符。收到: {response}")
        
        if b'OK' not in response:
            return response

        output, error = response.split(b'OK', 1)
        if b"Traceback" in error:
             raise PyboardError(f"远程执行出错:\n{error.decode('utf-8', 'ignore')}")
        
        return output

    def enter_raw_repl(self):
        print("[设备] 正在中断程序并进入裸 REPL 模式...")
        self.serial.write(b'\r\x03\x03') # 发送Ctrl+C两次以确保中断任何脚本
        time.sleep(0.2)
        self.serial.write(b'\x01') # Ctrl+A: 进入裸 REPL
        time.sleep(0.2)
        response = self.serial.read_all()
        if b'raw REPL' not in response:
            print(f"[警告] 可能未能正确进入裸 REPL。响应: {response}")
        print("[设备] 成功进入裸 REPL。")

    def exit_raw_repl(self):
        print("[设备] 正在退出裸 REPL 模式...")
        self.serial.write(b'\x02') # Ctrl+B 退出
        time.sleep(0.1)

    def soft_reset(self):
        print("[设备] 正在执行软复位...")
        self.serial.write(b'import machine; machine.reset()\x04')
        time.sleep(1.5) # 给设备重启留出时间
        print("[设备] 软复位完成。")

    def wipe_device(self):
        print("[设备] 正在清空设备文件系统 (这可能需要一些时间)...")
        self.exec_raw(
            "import uos\n"
            "def rm_all(path):\n"
            "  try:\n"
            "    for item in uos.ilistdir(path):\n"
            "      full_path = path + '/' + item[0]\n"
            "      if item[1] == 0x8000: uos.remove(full_path)\n" # 文件
            "      else: rm_all(full_path); uos.rmdir(full_path)\n" # 文件夹
            "  except OSError: pass\n"
            "rm_all('/')"
        , timeout=30)
        print("[设备] 文件系统已清空。")

    def put_file(self, local_path, remote_path):
        try:
            with open(local_path, 'rb') as f:
                content = f.read()
        except FileNotFoundError:
            raise PyboardError(f"本地文件未找到: {local_path}")
        
        print(f"  传输: {local_path} -> {remote_path} ({len(content)} bytes)")
        
        remote_dir = '/'.join(remote_path.split('/')[:-1])
        if remote_dir:
            self.exec_raw(f"try: uos.mkdir('{remote_dir}')\nexcept OSError: pass", quiet=True)

        encoded_content = b64encode(content)
        self.exec_raw(f"f = open('{remote_path}', 'wb'); import ubinascii", quiet=True)
        
        chunk_size = 256
        for i in range(0, len(encoded_content), chunk_size):
            chunk = encoded_content[i:i+chunk_size]
            self.exec_raw(f"f.write(ubinascii.a2b_base64(b'{chunk.decode('ascii')}'))", quiet=True)
        
        self.exec_raw("f.close()", quiet=True)


def build_project(compile_files=True):
    title = "步骤 1: 构建和编译项目" if compile_files else "步骤 1: 构建项目 (跳过编译)"
    print(f"--- {title} ---")

    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    stats = []
    total_before, total_after = 0, 0

    for root, dirs, files in os.walk(SOURCE_DIR):
        rel_path = os.path.relpath(root, SOURCE_DIR)
        dist_path = os.path.join(BUILD_DIR, rel_path) if rel_path != '.' else BUILD_DIR

        if not os.path.exists(dist_path):
            os.makedirs(dist_path)

        for file in files:
            local_file_path = os.path.join(root, file)
            
            if compile_files and file.endswith('.py'):
                mpy_file = file.replace('.py', '.mpy')
                dist_file_path = os.path.join(dist_path, mpy_file)
                try:
                    result = subprocess.run(
                        [MPY_CROSS_CMD, local_file_path, "-o", dist_file_path],
                        check=True, capture_output=True, text=True, encoding='utf-8'
                    )
                    
                    original_size = os.path.getsize(local_file_path)
                    compiled_size = os.path.getsize(dist_file_path)
                    reduction = (original_size - compiled_size) / original_size * 100 if original_size > 0 else 0
                    total_before += original_size
                    total_after += compiled_size
                    stats.append((file, original_size, compiled_size, reduction))

                except FileNotFoundError:
                    print(f"\n[致命错误] 找不到 mpy-cross 命令。请确保它已正确安装并位于系统 PATH 环境变量中。")
                    sys.exit(1)
                except subprocess.CalledProcessError as e:
                    print(f"\n[致命错误] 编译文件 '{local_file_path}' 失败。")
                    print("="*15 + " mpy-cross 编译器错误信息 " + "="*15)
                    print(e.stderr)
                    print("="*58)
                    print("错误原因可能是：\n  1. mpy-cross 版本与设备固件不兼容。\n  2. Python 代码中存在语法错误。")
                    print("\n[建议] 您可以尝试使用 '--no-compile' 选项跳过编译，直接部署 .py 源文件。")
                    sys.exit(1)
            else:
                shutil.copy(local_file_path, os.path.join(dist_path, file))

    if compile_files and stats:
        print("\n[编译报告]")
        print("-" * 60)
        print(f"{'文件名':<25} | {'原始大小':>10} | {'编译后大小':>12} | {'压缩率':>7}")
        print("-" * 60)
        for name, orig, comp, red in sorted(stats, key=lambda x: x[3], reverse=True):
            print(f"{name:<25} | {orig:>8} B | {comp:>10} B | {red:>6.1f}%")
        print("-" * 60)
        total_reduction = (total_before - total_after) / total_before * 100 if total_before > 0 else 0
        print(f"{'总计':<25} | {total_before:>8} B | {total_after:>10} B | {total_reduction:>6.1f}%")
        print("-" * 60)
    
    print(f"构建产物已输出到 '{BUILD_DIR}/' 目录。\n")


def find_serial_port():
    print("--- 步骤 2: 查找设备 ---")
    ports = serial.tools.list_ports.comports()
    # 增加了更多关键字以提高检测成功率
    keywords = ['ch340', 'cp210x', 'usb to serial', 'usb jtag/serial', 'uart']
    esp_ports = [p for p in ports if any(k in p.description.lower() for k in keywords)]
    
    if not esp_ports:
        raise PyboardError("未找到任何 ESP32/ESP8266 设备。请检查连接和驱动程序。")
    
    if len(esp_ports) > 1:
        print("检测到多个设备，请选择一个:")
        for i, p in enumerate(esp_ports):
            print(f"  [{i+1}]: {p.device} - {p.description}")
        try:
            choice = int(input("请输入端口编号: ")) - 1
            if not (0 <= choice < len(esp_ports)):
                raise ValueError
            return esp_ports[choice].device
        except (ValueError, IndexError, KeyboardInterrupt):
            print("\n选择无效或操作取消，脚本退出。")
            sys.exit(1)

    port = esp_ports[0].device
    print(f"自动选择设备: {port} - {esp_ports[0].description}")
    return port

def deploy(no_compile_flag):
    port = find_serial_port()
    
    print("\n--- 步骤 3: 部署到设备 ---")
    board = None
    try:
        board = Pyboard(port)
        board.enter_raw_repl()
        board.wipe_device()

        print("[部署] 开始上传文件...")
        # 上传 `dist` 目录的所有内容
        for root, dirs, files in os.walk(BUILD_DIR):
            for file in files:
                local_path = os.path.join(root, file)
                # 计算远程路径时，去掉 'dist/' 前缀
                remote_path = "/" + os.path.relpath(local_path, BUILD_DIR).replace("\\", "/")
                board.put_file(local_path, remote_path)
        
        print("[部署] 所有文件上传成功！")
        
        board.exit_raw_repl()
        board.soft_reset()

    except PyboardError as e:
        print(f"\n[致命错误] 部署过程中发生错误: {e}")
        sys.exit(1)
    finally:
        if board:
            board.close()

def main():
    print("=================================================")
    print("=      ESP32/MicroPython 智能部署工具 v4.0      =")
    print("=================================================\n")
    
    should_compile = '--no-compile' not in sys.argv
    
    build_project(compile_files=should_compile)
    deploy(no_compile_flag=(not should_compile))
    
    print("\n🎉 部署成功完成！")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code != 0:
             print(f"\n脚本因错误退出 (代码: {e.code})")
        else:
             print("\n\n用户中断了操作。")
    except Exception as e:
        print(f"\n发生未知错误: {e}")