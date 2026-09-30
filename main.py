#!/usr/bin/env python3
"""
MyFtp - 项目文件同步工具
============================
一个类FTP的桌面工具，支持：
  · 多FTP服务器管理
  · 项目文件定时扫描，检测变更后手动上传
  · 全量目录同步
  · 文件浏览、上传、下载
  · 同步日志记录

用法:
    python main.py
"""

import sys
import os

# 兼容 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后，模块已在临时目录中，无需额外设置
    APPLICATION_PATH = sys._MEIPASS
else:
    # 开发模式，确保项目根目录在 path 中
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, APPLICATION_PATH)


def main():
    from gui.app import run
    run()


if __name__ == "__main__":
    main()
