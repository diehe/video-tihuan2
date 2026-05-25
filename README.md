# 视频替换 MVP

一个面向“屏幕 / 招牌 / 海报 / 电视”等平面区域的视频追踪替换工具。前端使用 Tauri v2 + React，处理引擎使用 Python + OpenCV + FFmpeg。

## 本地开发

```bash
python3 -m pip install -r requirements-dev.txt
npm install
chmod +x scripts/dev.sh
./scripts/dev.sh
```

打开 Vite 输出的本地地址后，填写：

- 后端地址：`http://127.0.0.1:8765`
- 原视频绝对路径
- 替换视频绝对路径
- OpenAI 兼容 API Key
- 替换描述，例如“替换墙上的广告牌”

## 验证

```bash
python3 -m pytest
npm test
npm run build
```

## 桌面打包说明

Tauri 桌面构建需要安装 Rust 工具链。Python 引擎需要先打成 sidecar 二进制并放到 `sidecars/` 目录。当前 MVP 已提供 Tauri 配置和 sidecar 启动命令，macOS/Windows 发布还需要分别在对应平台生成 sidecar。
