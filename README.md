# 绿幕视频替换

一个面向“手机屏幕为绿幕”的本地桌面合成工具。用户选择主体视频和替换视频后，软件在限定区域内逐帧扣绿，将替换视频合成到手机绿幕区域，并导出 MP4。

前端使用 Tauri v2 + React，处理引擎使用 Python + OpenCV + FFmpeg。

## 功能

- 选择主体视频和替换视频。
- 自动识别绿幕区域，并支持拖动限定手机区域，避免误扣其他绿色物体。
- 预览主体首帧、绿色 mask 和合成效果。
- 支持填满裁剪、拉伸填满、完整留边三种画面适配。
- 支持分别调节主体视频和手机替换视频音量，并在导出时自动混音。

## 本地开发

```bash
python3 -m pip install -r requirements-dev.txt
npm install
chmod +x scripts/dev.sh
./scripts/dev.sh
```

## 验证

```bash
python3 -m pytest
npm test
npm run build
```

## 桌面打包说明

Tauri 桌面构建需要安装 Rust 工具链。打包命令会先用 PyInstaller
把 Python/OpenCV 后端引擎打成 sidecar，再由 Tauri 生成桌面 App：

```bash
npm run package:app
```

打包产物在 `src-tauri/target/release/bundle/`。构建机需要安装
FFmpeg；脚本会把 `ffmpeg` 一起放入后端 sidecar，用户安装 App 后
不需要单独安装 Python、Node、FFmpeg 或手动启动后端服务。

### Windows 打包

Windows 安装包需要在 Windows 构建环境中生成，因为 Tauri 桌面壳、
PyInstaller 后端 sidecar、OpenCV wheel 都是平台相关产物。仓库内
已提供 GitHub Actions 工作流：

1. 推送代码到 GitHub。
2. 打开 `Actions` -> `Release Desktop Apps`。
3. 点击 `Run workflow`，输入版本号，例如 `v0.1.0`。
4. 构建完成后，GitHub Releases 页面会生成同版本下载页，
   里面包含 macOS `.dmg` 和 Windows `.exe` 安装包。

如果只想单独构建 Windows 包，可以运行 `Build Windows App` 工作流，
构建完成后在 `windows-installers` artifact 中下载安装包。

如果在本地 Windows 机器构建，安装 Node.js、Python 3.12、Rust 和
FFmpeg 后运行：

```bash
npm ci
npm run package:app:windows
```
