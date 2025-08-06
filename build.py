# build.py
import os
import shutil
import subprocess
import sys
import argparse

# --- 配置 ---
# 源目录：存放你的 .py 源代码
SRC_DIR = "src"
# 输出目录：存放编译后的 .mpy 文件和其它文件
DIST_DIR = "dist"
# mpy-cross 可执行文件的名称或路径
MPY_CROSS_EXECUTABLE = "mpy-cross"

# 不需要编译，而是直接复制的 .py 文件列表
NO_COMPILE_FILES = ['boot.py', 'main.py']

# 默认情况下要从构建中完全排除的目录列表
# 注意：这里的路径是相对于 SRC_DIR 的
DEFAULT_EXCLUDE_DIRS = ['tests']


def main():
    """主执行函数"""
    # --- 1. 设置和解析命令行参数 ---
    parser = argparse.ArgumentParser(description="MicroPython 项目构建脚本")
    parser.add_argument(
        '-t', '--test',
        action='store_true',
        help="包含 'tests' 目录进行构建 (默认排除)。"
    )
    args = parser.parse_args()

    # 根据参数确定最终要排除的目录列表
    exclude_dirs = [] if args.test else [os.path.join(SRC_DIR, d) for d in DEFAULT_EXCLUDE_DIRS]

    print("--- MicroPython Build Script ---")
    if args.test:
        print("模式: 包含 tests 目录进行构建 (已启用 --test)。")
    else:
        print(f"模式: 排除目录 {DEFAULT_EXCLUDE_DIRS}。")


    # --- 2. 检查 mpy-cross 是否可用 ---
    if not shutil.which(MPY_CROSS_EXECUTABLE):
        print(f"错误: '{MPY_CROSS_EXECUTABLE}' 命令未找到。", file=sys.stderr)
        print("请确保 mpy-cross 已经编译并已添加到系统的 PATH 环境变量中。", file=sys.stderr)
        sys.exit(1)

    # --- 3. 清理并创建输出目录 ---
    print(f"清理输出目录: {DIST_DIR}")
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    # --- 4. 遍历源目录并处理文件 ---
    print(f"开始处理源目录: {SRC_DIR}")
    if not os.path.isdir(SRC_DIR):
        print(f"错误: 源目录 '{SRC_DIR}' 不存在。", file=sys.stderr)
        sys.exit(1)

    total_files = 0
    compiled_files = 0
    copied_files = 0

    for root, dirs, files in os.walk(SRC_DIR, topdown=True):
        # --- 过滤排除的目录 ---
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in exclude_dirs]
        
        # 计算相对于源目录的路径
        relative_path = os.path.relpath(root, SRC_DIR)
        
        # 在目标目录中创建对应的子目录
        dist_root = os.path.join(DIST_DIR, relative_path) if relative_path != '.' else DIST_DIR
        if not os.path.exists(dist_root):
            os.makedirs(dist_root)

        for file in files:
            total_files += 1
            src_path = os.path.join(root, file)
            dist_path = os.path.join(dist_root, file)

            # 如果是 .py 文件，则根据配置决定编译或复制
            if file.endswith('.py'):
                if file in NO_COMPILE_FILES:
                    print(f"  复制: {src_path} -> {dist_path}")
                    shutil.copy2(src_path, dist_path)
                    copied_files += 1
                else:
                    dist_path_mpy = os.path.splitext(dist_path)[0] + '.mpy'
                    print(f"  编译: {src_path} -> {dist_path_mpy}")
                    try:
                        command = [MPY_CROSS_EXECUTABLE, "-o", dist_path_mpy, src_path]
                        subprocess.run(command, check=True, capture_output=True, text=True)
                        compiled_files += 1
                    except subprocess.CalledProcessError as e:
                        print(f"\n!!! 编译失败: {src_path}", file=sys.stderr)
                        print(e.stderr, file=sys.stderr)
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