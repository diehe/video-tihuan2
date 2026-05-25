# 绿幕视频替换实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将旧的追踪替换 MVP 改造成 Mac 桌面绿幕扣像替换软件。

**架构：** 复用 Tauri + React + Python sidecar。Python 新增 chroma-key 分析、预览和导出接口；React 改为三步向导，不再依赖追踪和 AI 校准。

**技术栈：** Tauri v2、React 18、TypeScript、FastAPI、OpenCV、NumPy、FFmpeg、Vitest、Pytest。

---

## 文件结构

- 迁移：旧项目基础文件到新项目，排除 `.git`、`node_modules`、`dist`、`build`、`sidecars`、缓存和目标产物。
- 修改：`engine/schemas.py`，新增 chroma 参数、分析结果、预览结果。
- 修改：`engine/pipeline.py`，新增绿幕 mask、四角估算、单帧合成、完整导出。
- 修改：`engine/api_server.py` 和 `engine/simple_server.py`，新增 `/chroma/*` 接口。
- 修改：`src/lib/types.ts`、`src/lib/api.ts`、`src/lib/workflow.ts`，改成 chroma 主流程。
- 重写：`src/App.tsx` 和 `src/styles/app.css`，三步向导 UI。
- 修改：`tests/test_engine.py`，新增 chroma 引擎测试。
- 修改：`src/lib/*.test.ts` 和 `src/App.test.tsx`，覆盖新状态流和 API。

## 任务

### 任务 1：迁移项目基础

- [ ] 复制旧项目的源码、配置和打包文件到新目录。
- [ ] 更新 `.gitignore`，忽略 `.superpowers/` 和构建产物。
- [ ] 运行 `npm install`，确保前端依赖可用。

### 任务 2：Python chroma 引擎 TDD

- [ ] 先写失败测试：限定区域只扣手机绿幕，不扣区域外绿色干扰物。
- [ ] 运行 `python3 -m pytest tests/test_engine.py::test_chroma_analyze_respects_roi -q`，确认失败。
- [ ] 实现最小的 chroma 分析函数。
- [ ] 运行测试确认通过。
- [ ] 先写失败测试：单帧合成只替换绿色 mask，非绿色边框保留。
- [ ] 实现单帧合成函数。
- [ ] 先写失败测试：完整导出生成 MP4 并写入预期帧数。
- [ ] 实现 chroma render。

### 任务 3：后端 API

- [ ] 先写或更新 API 测试，验证 `/chroma/analyze`、`/chroma/preview`、`/chroma/render` payload。
- [ ] 在 FastAPI server 中暴露 chroma 接口。
- [ ] 保留旧接口，避免 sidecar 兼容问题。

### 任务 4：前端状态和 API TDD

- [ ] 先写失败测试：选择两个视频后可以分析，分析后可以预览和导出。
- [ ] 更新 TypeScript 类型和 API 调用。
- [ ] 更新 reducer，删除 tracking 作为导出前置条件。

### 任务 5：三步向导 UI

- [ ] 重写 App UI 为输入、确认绿幕、导出三段。
- [ ] 保留路径选择、引擎检查、输出路径选择。
- [ ] 显示首帧、mask 预览、限定区域拖拽和轻量参数。
- [ ] 移除 AI 校准、关键帧列表、追踪按钮。

### 任务 6：验证

- [ ] 运行 `python3 -m pytest`。
- [ ] 运行 `npm test`。
- [ ] 运行 `npm run build`。
- [ ] 如时间允许，运行 Tauri dev 或浏览器预览检查界面。

