# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 玄学工具箱
构建命令：.venv\Scripts\pyinstaller.exe mysticism_tools.spec --noconfirm
产物：dist\玄学工具箱\ 目录（onedir 模式，启动快、杀软误报少）
"""
import os

project_root = os.path.abspath(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        # 个人配置模板随包分发；运行时真实配置由程序生成在 exe 旁的 config/ 下
        ('config/llm_config.example.json', 'config'),
        ('packaging/使用说明.txt', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',   # requirements 中列出但源码未使用，排除可大幅减小体积
        'tkinter',
        'sxtwl',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='玄学工具箱',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # 不用 UPX：压缩收益小且显著增加杀软误报率
    console=False,           # GUI 程序，不显示控制台黑窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='玄学工具箱',
)
