from __future__ import annotations

from typing import Literal

from .pipeline import EngineError


def select_local_path(kind: Literal["video", "output"]) -> str:
    import platform
    import subprocess

    system = platform.system()
    if system == "Darwin":
        if kind == "output":
            script = (
                'POSIX path of (choose file name with prompt "选择导出视频保存位置" '
                'default name "video-tihuan-output.mp4")'
            )
        else:
            script = 'POSIX path of (choose file with prompt "选择视频文件")'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        raise EngineError("已取消选择文件")

    if system == "Windows":
        if kind == "output":
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.SaveFileDialog; "
                "$d.Filter = 'MP4 Video (*.mp4)|*.mp4|All files (*.*)|*.*'; "
                "$d.FileName = 'video-tihuan-output.mp4'; "
                "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
            )
        else:
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                "$d.Filter = 'Video files (*.mp4;*.mov;*.mkv)|*.mp4;*.mov;*.mkv|All files (*.*)|*.*'; "
                "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
            )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, check=False)
        path = result.stdout.strip()
        if result.returncode == 0 and path:
            return path
        raise EngineError("已取消选择文件")

    return _select_with_tk(kind)


def _select_with_tk(kind: Literal["video", "output"]) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        if kind == "output":
            path = filedialog.asksaveasfilename(
                title="选择导出视频保存位置",
                defaultextension=".mp4",
                filetypes=[("MP4 Video", "*.mp4"), ("All files", "*.*")],
            )
        else:
            path = filedialog.askopenfilename(
                title="选择视频文件",
                filetypes=[("Video files", "*.mp4 *.mov *.mkv"), ("All files", "*.*")],
            )
    finally:
        root.destroy()
    if not path:
        raise EngineError("已取消选择文件")
    return path
