# build.py
import os
import shutil
import subprocess
import sys

# --- 配置 ---
# 源目录：存放你的 .py 源代码
SRC_DIR = "src"
# 输出目录：存放编译后的 .mpy 文件和其它文件
DIST_DIR = "dist"
# mpy-cross 可执行文件的名称或路径
MPY_CROSS_EXECUTABLE = "mpy-cross"

def main():
    """主执行函数"""
    print("--- MicroPython Build Script ---")

    # 1. 检查 mpy-cross 是否可用
    if not shutil.which(MPY_CROSS_EXECUTABLE):
        print(f"错误: '{MPY_CROSS_EXECUTABLE}' 命令未找到。")
        print("请确保 mpy-cross 已经编译并已添加到系统的 PATH 环境变量中。")
        sys.exit(1)

    # 2. 清理并创建输出目录
    print(f"清理输出目录: {DIST_DIR}")
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    # 3. 遍历源目录并处理文件
    print(f"开始处理源目录: {SRC_DIR}")
    if not os.path.isdir(SRC_DIR):
        print(f"错误: 源目录 '{SRC_DIR}' 不存在。")
        sys.exit(1)

    total_files = 0
    compiled_files = 0
    copied_files = 0

    for root, dirs, files in os.walk(SRC_DIR):
        # 计算相对于源目录的路径，以在目标目录中重建结构
        relative_path = os.path.relpath(root, SRC_DIR)
        
        # 在目标目录中创建对应的子目录
        dist_root = os.path.join(DIST_DIR, relative_path) if relative_path != '.' else DIST_DIR
        if not os.path.exists(dist_root):
            os.makedirs(dist_root)

        for file in files:
            total_files += 1
            src_path = os.path.join(root, file)
            dist_path = os.path.join(dist_root, file)

            # 如果是 .py 文件，则使用 mpy-cross 编译
            if file.endswith('.py'):
                # boot.py 和 main.py 通常不建议编译，除非有特殊需求
                if file in ['boot.py', 'main.py']:
                    print(f"  复制: {src_path} -> {dist_path}")
                    shutil.copy2(src_path, dist_path)
                    copied_files += 1
                else:
                    dist_path_mpy = os.path.splitext(dist_path)[0] + '.mpy'
                    print(f"  编译: {src_path} -> {dist_path_mpy}")
                    try:
                        # 使用 -o 参数直接指定输出文件，更可靠
                        command = [MPY_CROSS_EXECUTABLE, "-o", dist_path_mpy, src_path]
                        subprocess.run(command, check=True, capture_output=True, text=True)
                        compiled_files += 1
                    except subprocess.CalledProcessError as e:
                        print(f"\n!!! 编译失败: {src_path}", file=sys.stderr)
                        print(e.stderr, file=sys.stderr) # 打印 mpy-cross 的错误输出
                        sys.exit(1)
            # 否则，直接复制文件
            else:
                print(f"  复制: {src_path} -> {dist_path}")
                shutil.copy2(src_path, dist_path)
                copied_files += 1

    print("\n--- 构建完成 ---")
    print(f"总共处理文件: {total_files}")
    print(f"成功编译文件: {compiled_files}")
    print(f"直接复制文件: {copied_files}")
    print(f"输出目录 '{DIST_DIR}' 已准备好，可以部署到您的设备上。")

if __name__ == "__main__":
    main()