# 绿幕视频替换

一个面向“手机屏幕为绿幕”的本地桌面合成工具。用户选择主体视频和替换视频后，软件在限定区域内逐帧扣绿，将替换视频合成到手机绿幕区域，并导出 MP4。

前端使用 Tauri v2 + React，处理引擎使用 Python + OpenCV + FFmpeg。

## 功能

- 选择主体视频和替换视频。
- 自动识别绿幕区域，并支持拖动限定手机区域，避免误扣其他绿色物体。
- 预览主体首帧、绿色 mask 和合成效果。
- 支持填满裁剪、拉伸填满、完整留边三种画面适配。
- 支持保留主体音频、使用替换视频音频或静音导出。

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

Tauri 桌面构建需要安装 Rust 工具链。Python 引擎需要先打成 sidecar 二进制并放到 `sidecars/` 目录：

```bash
./scripts/build-sidecar.sh
npm run tauri build
```
