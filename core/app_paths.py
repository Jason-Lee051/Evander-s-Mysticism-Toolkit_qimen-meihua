"""
core/app_paths.py — 应用路径解析

开发环境：以项目根目录为基准。
PyInstaller 打包后：
  - 可写数据（config/llm_config.json）固定放在 exe 所在目录，
    保证用户设置在多次启动之间保留；
  - 只读资源走 sys._MEIPASS（onefile 解包目录）。
"""
import os
import sys


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境中"""
    return getattr(sys, "frozen", False)


def app_dir() -> str:
    """应用基准目录（可写）：打包后为 exe 所在目录；开发时为项目根目录"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    # core/app_paths.py 的上两级 = 项目根
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """只读资源目录：onefile 模式下为 _MEIPASS 解包目录"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return app_dir()


def config_file() -> str:
    """LLM 配置文件完整路径（exe 目录下 config/llm_config.json）"""
    return os.path.join(app_dir(), "config", "llm_config.json")


def config_example_file() -> str:
    """LLM 配置示例文件完整路径（随包分发的只读模板）"""
    return os.path.join(resource_dir(), "config", "llm_config.example.json")
