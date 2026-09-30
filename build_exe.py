#!/usr/bin/env python3
"""
MyFtp 一键打包脚本
==================
自动完成以下步骤：
  1. 检查并安装 PyInstaller
  2. 清理旧的构建产物（build/ dist/）
  3. 使用 PyInstaller 打包生成单个 EXE
  4. 输出结果信息

用法:
    py build_exe.py          # 默认打包
    py build_exe.py --clean  # 清理构建产物后退出（不打包）
"""

import subprocess
import shutil
import os
import sys
import time

# ---- 配置 ----
APP_NAME = "MyFtp"
ENTRY_SCRIPT = "main.py"
SPEC_FILE = f"{APP_NAME}.spec"
BUILD_DIR = "build"
DIST_DIR = "dist"

# 获取脚本所在目录（即项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, check=True):
    """运行命令并实时显示输出"""
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if check and result.returncode != 0:
        print(f"\n  [错误] 命令执行失败 (返回码 {result.returncode})")
        sys.exit(1)
    return result.returncode


def check_pyinstaller():
    """检查 PyInstaller 是否已安装，未安装则自动安装"""
    print("\n[1/4] 检查 PyInstaller...")
    ret = subprocess.run(
        [sys.executable, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
        capture_output=True, text=True
    )
    if ret.returncode == 0:
        version = ret.stdout.strip()
        print(f"  已安装 PyInstaller {version}")
        return True

    print("  PyInstaller 未安装，正在安装...")
    ret = run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    if ret != 0:
        print("  [错误] PyInstaller 安装失败，请手动运行: pip install pyinstaller")
        return False
    print("  PyInstaller 安装成功")
    return True


def clean_build():
    """清理旧的构建产物"""
    print("\n[2/4] 清理旧构建产物...")
    cleaned = []
    for name in [BUILD_DIR, DIST_DIR]:
        path = os.path.join(PROJECT_ROOT, name)
        if os.path.exists(path):
            shutil.rmtree(path)
            cleaned.append(name)
    if cleaned:
        print(f"  已清理: {', '.join(cleaned)}")
    else:
        print("  无需清理")


def build_exe():
    """使用 PyInstaller 打包"""
    print("\n[3/4] 开始打包...")
    spec_path = os.path.join(PROJECT_ROOT, SPEC_FILE)
    if os.path.exists(spec_path):
        # 使用 spec 文件打包
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",    # 覆盖已有输出
            "--clean",        # 清理 PyInstaller 缓存
            SPEC_FILE,
        ]
    else:
        # 没有 spec 文件，使用命令行参数打包
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",          # 单个 EXE
            "--windowed",          # GUI 程序，不显示控制台
            "--name", APP_NAME,
            "--hidden-import", "core",
            "--hidden-import", "core.config_manager",
            "--hidden-import", "core.ftp_client",
            "--hidden-import", "core.file_monitor",
            "--hidden-import", "gui",
            "--hidden-import", "gui.app",
            "--hidden-import", "gui.msgbox",
            ENTRY_SCRIPT,
        ]
    run(cmd)


def show_result():
    """输出打包结果"""
    print("\n[4/4] 打包结果")
    exe_path = os.path.join(PROJECT_ROOT, DIST_DIR, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  ┌──────────────────────────────────────────┐")
        print(f"  │  打包成功!                                │")
        print(f"  │                                          │")
        print(f"  │  文件: {DIST_DIR}\\{APP_NAME}.exe")
        print(f"  │  大小: {size_mb:.1f} MB")
        print(f"  │  路径: {exe_path}")
        print(f"  └──────────────────────────────────────────┘")
    else:
        print(f"  [警告] 未找到输出文件: {exe_path}")
        print("  请检查上方打包日志中的错误信息")


def main():
    print("=" * 50)
    print(f"  {APP_NAME} 一键打包工具")
    print("=" * 50)
    start_time = time.time()

    # 清理模式
    if "--clean" in sys.argv:
        clean_build()
        print("\n清理完成。")
        return

    # 执行打包流程
    if not check_pyinstaller():
        return
    clean_build()
    build_exe()
    show_result()

    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()
