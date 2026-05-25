import {
  CheckCircle2,
  Cpu,
  FileVideo,
  Loader2,
  MousePointer2,
  Move,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Settings,
  Trash2,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  analyzeTarget,
  generateAiKeyframes,
  healthCheck,
  readFramePreview,
  renderReplacement,
  selectLocalPath,
  trackRegion,
} from "./lib/api";
import { mergeAiKeyframes } from "./lib/keyframes";
import {
  clientPointToFrame,
  formatQuadText,
  formatSvgQuadPoints,
  moveQuad,
  moveQuadPoint,
  panView,
  parseQuadText,
  zoomAtPoint,
} from "./lib/quad";
import { loadAiSettings, saveAiSettings } from "./lib/settings";
import type { ViewTransform } from "./lib/quad";
import type { AiCalibrationMode, FramePreview, Quad, TrackingKeyframe } from "./lib/types";
import { appReducer, canAnalyze, canRender, canTrack, initialState } from "./lib/workflow";

export function App() {
  const [state, dispatch] = useReducer(appReducer, initialState, (state) => ({ ...state, ...loadAiSettings() }));
  const frameRequestId = useRef(0);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [previewFrame, setPreviewFrame] = useState<FramePreview | null>(null);
  const [frameTime, setFrameTime] = useState(0);
  const [aiCalibrationMode, setAiCalibrationMode] = useState<AiCalibrationMode>("0.5");
  const [trackingKeyframes, setTrackingKeyframes] = useState<TrackingKeyframe[]>([]);
  const [previewView, setPreviewView] = useState<ViewTransform>({ scale: 1, x: 0, y: 0 });
  const [previewMode, setPreviewMode] = useState<"edit" | "pan">("edit");
  const lastTrackingRef = useRef(state.tracking);
  const [panDrag, setPanDrag] = useState<{
    pointerId: number;
    startX: number;
    startY: number;
    startView: ViewTransform;
  } | null>(null);
  const busy = ["analyzing", "calibrating", "tracking", "rendering"].includes(state.status);
  const activeFrame = previewFrame ?? state.analysis?.frame ?? null;
  const timelineDuration = Math.max(
    activeFrame?.duration ?? 0,
    state.tracking ? state.tracking.frame_count / state.tracking.fps : 0,
  );
  const timelineFrameCount = activeFrame?.frame_count || state.tracking?.frame_count || 0;
  const currentFrameTime = activeFrame?.time ?? frameTime;
  const currentFrameIndex = activeFrame?.index ?? 0;
  const currentKeyframe = trackingKeyframes.find((keyframe) => keyframe.index === currentFrameIndex);
  const currentTrackedFrame = state.tracking?.frames.find((frame) => frame.index === currentFrameIndex);

  useEffect(() => {
    saveAiSettings({
      apiBaseUrl: state.apiBaseUrl,
      apiKey: state.apiKey,
      model: state.model,
    });
  }, [state.apiBaseUrl, state.apiKey, state.model]);

  useEffect(() => {
    if (state.tracking) {
      lastTrackingRef.current = state.tracking;
      return;
    }
    if (!state.analysis) {
      lastTrackingRef.current = null;
    }
  }, [state.analysis, state.tracking]);

  const quadText = useMemo(() => {
    if (!state.confirmedQuad) return "";
    return formatQuadText(state.confirmedQuad);
  }, [state.confirmedQuad]);

  async function checkBackend() {
    setBackendOnline(null);
    setBackendOnline(await healthCheck(state.backendUrl));
  }

  async function choosePath(target: "source" | "replacement" | "output") {
    try {
      const path = await selectLocalPath(state.backendUrl || "http://127.0.0.1:8765", target === "output" ? "output" : "video");
      if (!path) return;
      if (target === "source") dispatch({ type: "setSourcePath", path });
      if (target === "replacement") dispatch({ type: "setReplacementPath", path });
      if (target === "output") dispatch({ type: "setOutputPath", path });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "选择文件失败" });
    }
  }

  async function runAnalyze() {
    dispatch({ type: "setStatus", status: "analyzing", message: "正在抽取关键帧并识别目标区域..." });
    try {
      const result = await analyzeTarget({
        backendUrl: state.backendUrl,
        videoPath: state.sourcePath,
      });
      setPreviewView({ scale: 1, x: 0, y: 0 });
      setPreviewMode("edit");
      setPreviewFrame(result.frame);
      setFrameTime(0);
      setTrackingKeyframes([]);
      dispatch({ type: "setAnalysis", analysis: result });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "分析失败" });
    }
  }

  async function runTrack(keyframes = trackingKeyframes, baseQuad = state.baseQuad) {
    if (!baseQuad) return;
    dispatch({
      type: "setStatus",
      status: "tracking",
      message: keyframes.length
        ? `正在按 ${keyframes.length} 个修正关键帧追踪...`
        : "正在追踪平面区域...",
    });
    try {
      const tracking = await trackRegion(state.backendUrl, state.sourcePath, baseQuad, keyframes);
      lastTrackingRef.current = tracking;
      dispatch({ type: "setTracking", tracking });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "追踪失败" });
    }
  }

  async function rebuildTrackingAfterKeyframes(
    keyframes: TrackingKeyframe[],
    options: { baseQuad?: Quad | null; frameIndex?: number } = {},
  ) {
    const baseQuad = options.baseQuad ?? state.baseQuad;
    if (!state.sourcePath || !baseQuad || !lastTrackingRef.current) return;
    dispatch({
      type: "setStatus",
      status: "tracking",
      message: "正在按关键帧重建轨迹...",
    });
    try {
      const tracking = await trackRegion(state.backendUrl, state.sourcePath, baseQuad, keyframes);
      lastTrackingRef.current = tracking;
      dispatch({ type: "setTracking", tracking });

      const frameIndex = options.frameIndex ?? currentFrameIndex;
      const keyframe = keyframes.find((item) => item.index === frameIndex);
      const trackedFrame = tracking.frames.find((item) => item.index === frameIndex);
      const quad = keyframe?.quad ?? trackedFrame?.quad;
      if (quad) {
        dispatch({ type: "setPreviewQuad", quad, updateBase: frameIndex === 0 });
      }
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "重建轨迹失败" });
    }
  }

  async function loadFrameAtTime(time = frameTime, options: { resetView?: boolean } = {}) {
    if (!state.sourcePath) return;
    const requestedTime = Number.isFinite(time) ? Math.max(0, time) : 0;
    const requestId = ++frameRequestId.current;
    setFrameTime(requestedTime);
    try {
      const frame = await readFramePreview(state.backendUrl, state.sourcePath, requestedTime);
      if (requestId !== frameRequestId.current) return;
      setPreviewFrame(frame);
      setFrameTime(Math.round(frame.time * 100) / 100);
      if (options.resetView) {
        setPreviewView({ scale: 1, x: 0, y: 0 });
      }
      const existingKeyframe = trackingKeyframes.find((keyframe) => keyframe.index === frame.index);
      if (existingKeyframe) {
        dispatch({ type: "setPreviewQuad", quad: existingKeyframe.quad, updateBase: frame.index === 0 });
        return;
      }
      const trackedFrame = state.tracking?.frames.find((item) => item.index === frame.index);
      if (trackedFrame) {
        dispatch({ type: "setPreviewQuad", quad: trackedFrame.quad, updateBase: frame.index === 0 });
        return;
      }
      if (frame.index === 0 && state.baseQuad) {
        dispatch({ type: "setPreviewQuad", quad: state.baseQuad, updateBase: true });
      }
    } catch (error) {
      if (requestId !== frameRequestId.current) return;
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "读取关键帧失败" });
    }
  }

  function saveCurrentKeyframe() {
    if (!activeFrame || !state.confirmedQuad) return;
    const quad = state.confirmedQuad;
    const next = trackingKeyframes
      .filter((item) => item.index !== activeFrame.index)
      .concat({ index: activeFrame.index, time: activeFrame.time, quad, source: "manual" })
      .sort((a, b) => a.index - b.index);
    setTrackingKeyframes(next);
    dispatch({ type: "setPreviewQuad", quad, updateBase: activeFrame.index === 0 });
    void rebuildTrackingAfterKeyframes(next, {
      baseQuad: activeFrame.index === 0 ? quad : state.baseQuad,
      frameIndex: activeFrame.index,
    });
  }

  function updateCurrentQuad(quad: Quad) {
    if ((activeFrame?.index ?? 0) === 0) {
      dispatch({ type: "setBaseQuad", quad });
      return;
    }
    dispatch({ type: "confirmQuad", quad });
  }

  function removeKeyframe(index: number) {
    const next = trackingKeyframes.filter((item) => item.index !== index);
    setTrackingKeyframes(next);
    void rebuildTrackingAfterKeyframes(next, { frameIndex: currentFrameIndex });
  }

  async function runAiCalibration() {
    if (!state.sourcePath || !state.baseQuad) return;
    dispatch({ type: "setStatus", status: "calibrating", message: `正在请求 ${state.apiBaseUrl} 生成 AI 校准关键帧...` });
    try {
      const keyframes = await generateAiKeyframes({
        backendUrl: state.backendUrl,
        videoPath: state.sourcePath,
        referenceQuad: state.baseQuad,
        mode: aiCalibrationMode,
        apiKey: state.apiKey,
        baseUrl: state.apiBaseUrl,
        model: state.model,
      });
      if (keyframes.length === 0) {
        dispatch({
          type: "setError",
          message: "AI 请求已完成，但没有生成有效关键帧。请检查模型是否支持图片输入、返回是否为 JSON，以及 API 地址是否正确。",
        });
        return;
      }
      const next = mergeAiKeyframes(trackingKeyframes, keyframes);
      setTrackingKeyframes(next);
      await rebuildTrackingAfterKeyframes(next);
      dispatch({
        type: "setStatus",
        status: "idle",
        message: `AI 已生成 ${keyframes.length} 个校准关键帧，可以拖动时间轴核查。`,
      });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "AI 校准失败" });
    }
  }

  async function runRender() {
    if (!state.tracking) return;
    dispatch({ type: "setStatus", status: "rendering", message: "正在合成并导出 MP4..." });
    try {
      const renderResult = await renderReplacement(state.backendUrl, {
        sourcePath: state.sourcePath,
        replacementPath: state.replacementPath,
        tracking: state.tracking,
        outputPath: state.outputPath,
        audioPolicy: state.audioPolicy,
        fitMode: state.fitMode,
      });
      dispatch({ type: "setRenderResult", renderResult });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "导出失败" });
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Wand2 size={22} />
          </div>
          <div>
            <h1>视频替换</h1>
            <p>平面追踪替换 MVP</p>
          </div>
        </div>
        <StatusPanel message={state.message} status={state.status} />
        <div className="steps">
          <Step done={Boolean(state.analysis)} label="框选区域" />
          <Step done={Boolean(state.tracking)} label="追踪四角" />
          <Step done={Boolean(state.renderResult)} label="导出视频" />
        </div>
      </aside>

      <section className="workspace">
        <header className="toolbar">
          <div>
            <h2>替换任务</h2>
            <p>选择本地视频，载入首帧后手动框选替换区域。</p>
          </div>
          <button className="ghost-button" onClick={checkBackend} type="button">
            <Radio size={17} />
            {backendOnline === null ? "检查引擎" : backendOnline ? "引擎在线" : "引擎离线"}
          </button>
        </header>

        <div className="grid">
          <section className="panel">
            <PanelTitle icon={<FileVideo size={18} />} title="输入" />
            <Field label="原视频路径">
              <div className="path-row">
                <input
                  value={state.sourcePath}
                  onChange={(event) => dispatch({ type: "setSourcePath", path: event.target.value })}
                  placeholder="/Users/me/source.mp4"
                />
                <button className="secondary-button" onClick={() => choosePath("source")} type="button">
                  选择
                </button>
              </div>
            </Field>
            <Field label="替换视频路径">
              <div className="path-row">
                <input
                  value={state.replacementPath}
                  onChange={(event) => dispatch({ type: "setReplacementPath", path: event.target.value })}
                  placeholder="/Users/me/replacement.mp4"
                />
                <button className="secondary-button" onClick={() => choosePath("replacement")} type="button">
                  选择
                </button>
              </div>
            </Field>
          </section>

          <section className="panel">
            <PanelTitle icon={<Settings size={18} />} title="设置" />
            <Field label="后端地址">
              <input
                value={state.backendUrl}
                onChange={(event) => dispatch({ type: "setBackendUrl", backendUrl: event.target.value })}
              />
            </Field>
            <Field label="API Base URL">
              <input
                value={state.apiBaseUrl}
                onChange={(event) => dispatch({ type: "setApiBaseUrl", apiBaseUrl: event.target.value })}
                placeholder="https://api.openai.com/v1"
              />
            </Field>
            <Field label="API Key">
              <input
                type="password"
                value={state.apiKey}
                onChange={(event) => dispatch({ type: "setApiKey", apiKey: event.target.value })}
                placeholder="用于 AI 校准关键帧"
              />
            </Field>
            <div className="two-columns">
              <Field label="模型">
                <input value={state.model} onChange={(event) => dispatch({ type: "setModel", model: event.target.value })} />
              </Field>
              <Field label="音频">
                <select
                  value={state.audioPolicy}
                  onChange={(event) => dispatch({ type: "setAudioPolicy", audioPolicy: event.target.value as never })}
                >
                  <option value="original">保留原视频</option>
                  <option value="replacement">使用替换视频</option>
                  <option value="silent">静音</option>
                </select>
              </Field>
              <Field label="画面适配">
                <select
                  value={state.fitMode}
                  onChange={(event) => dispatch({ type: "setFitMode", fitMode: event.target.value as never })}
                >
                  <option value="stretch">拉伸填满（无黑边）</option>
                  <option value="contain">完整留边（可能有黑边）</option>
                  <option value="cover">填满裁剪（会放大）</option>
                </select>
              </Field>
            </div>
            <Field label="导出路径">
              <div className="path-row">
                <input
                  value={state.outputPath}
                  onChange={(event) => dispatch({ type: "setOutputPath", path: event.target.value })}
                  placeholder="留空则输出到原视频目录"
                />
                <button className="secondary-button" onClick={() => choosePath("output")} type="button">
                  选择
                </button>
              </div>
            </Field>
          </section>
        </div>

        <section className="panel preview-panel">
          <PanelTitle icon={<MousePointer2 size={18} />} title="框选与确认" />
          <div className="preview-layout">
            <div className="frame-preview">
              {state.analysis && activeFrame ? (
                <div
                  className={[
                    "zoom-surface",
                    previewMode === "pan" ? "pan-mode" : "edit-mode",
                    panDrag ? "panning" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onContextMenu={(event) => event.preventDefault()}
                  onPointerDown={(event) => {
                    const canPan =
                      (previewMode === "pan" && event.button === 0) || event.button === 1 || event.button === 2;
                    if (!canPan) return;
                    event.preventDefault();
                    event.currentTarget.setPointerCapture(event.pointerId);
                    setPanDrag({
                      pointerId: event.pointerId,
                      startX: event.clientX,
                      startY: event.clientY,
                      startView: previewView,
                    });
                  }}
                  onPointerMove={(event) => {
                    if (!panDrag || panDrag.pointerId !== event.pointerId) return;
                    setPreviewView(
                      panView(panDrag.startView, event.clientX - panDrag.startX, event.clientY - panDrag.startY),
                    );
                  }}
                  onPointerUp={(event) => {
                    if (panDrag?.pointerId === event.pointerId) {
                      event.currentTarget.releasePointerCapture(event.pointerId);
                      setPanDrag(null);
                    }
                  }}
                  onPointerCancel={() => setPanDrag(null)}
                  onWheel={(event) => {
                    event.preventDefault();
                    const rect = event.currentTarget.getBoundingClientRect();
                    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
                    const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
                    setPreviewView((view) => zoomAtPoint(view, point, factor));
                  }}
                >
                  <div
                    className="image-stage"
                    style={{
                      transform: `translate(${previewView.x}px, ${previewView.y}px) scale(${previewView.scale})`,
                    }}
                  >
                    <img src={activeFrame.image} alt="关键帧预览" />
                    <QuadEditor
                      disabled={previewMode === "pan"}
                      quad={state.confirmedQuad}
                      width={activeFrame.width}
                      height={activeFrame.height}
                      onChange={updateCurrentQuad}
                    />
                  </div>
                  <div className="preview-toolbox" aria-label="预览工具" onPointerDown={(event) => event.stopPropagation()}>
                    <button
                      aria-label="编辑区域"
                      className={previewMode === "edit" ? "active" : ""}
                      onClick={() => {
                        setPanDrag(null);
                        setPreviewMode("edit");
                      }}
                      title="编辑区域"
                      type="button"
                    >
                      <MousePointer2 size={15} />
                    </button>
                    <button
                      aria-label="移动视图"
                      className={previewMode === "pan" ? "active" : ""}
                      onClick={() => {
                        setPanDrag(null);
                        setPreviewMode("pan");
                      }}
                      title="移动视图"
                      type="button"
                    >
                      <Move size={15} />
                    </button>
                    <button
                      aria-label="重置预览视图"
                      onClick={() => setPreviewView({ scale: 1, x: 0, y: 0 })}
                      title="重置预览视图"
                      type="button"
                    >
                      <RotateCcw size={15} />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="empty-preview">等待载入首帧</div>
              )}
            </div>
            <div className="candidate-list">
              {state.analysis?.candidates.map((candidate) => (
                <button
                  className="candidate"
                  key={candidate.id}
                  onClick={() => {
                    if (state.analysis) {
                      setPreviewFrame(state.analysis.frame);
                      setFrameTime(0);
                    }
                    dispatch({ type: "setBaseQuad", quad: candidate.quad });
                  }}
                  type="button"
                >
                  <strong>{candidate.label}</strong>
                  <span>{Math.round(candidate.confidence * 100)}% · {candidate.reason}</span>
                </button>
              ))}
              <Field label="四角坐标（左上、右上、右下、左下）">
                <textarea
                  value={quadText}
                  onChange={(event) => {
                    const quad = parseQuadText(event.target.value);
                    if (quad) updateCurrentQuad(quad);
                  }}
                  placeholder="32,28  112,26  118,86  28,88"
                />
              </Field>
              <div className="keyframe-editor">
                <div className="ai-calibration-row">
                  <Field label="AI 校准间隔">
                    <select
                      value={aiCalibrationMode}
                      onChange={(event) => setAiCalibrationMode(event.target.value as AiCalibrationMode)}
                    >
                      <option value="3">3 秒</option>
                      <option value="1">1 秒</option>
                      <option value="0.5">0.5 秒</option>
                      <option value="0.3">0.3 秒</option>
                      <option value="0.1">0.1 秒</option>
                      <option value="every">每帧</option>
                    </select>
                  </Field>
                  <button disabled={!state.sourcePath || !state.baseQuad || busy} onClick={runAiCalibration} type="button">
                    {state.status === "calibrating" ? <Loader2 className="spin" size={16} /> : <Cpu size={16} />}
                    AI 生成校准帧
                  </button>
                </div>
                <div className="timeline-panel">
                  <div className={currentKeyframe ? `timeline-readout ${keyframeTone(currentKeyframe)}` : "timeline-readout"}>
                    <span>{currentFrameTime.toFixed(2)}s</span>
                    <strong>第 {currentFrameIndex} 帧</strong>
                    {currentTrackedFrame ? (
                      <em className={`track-status ${currentTrackedFrame.status}`}>{currentTrackedFrame.status}</em>
                    ) : null}
                  </div>
                  <div className="timeline-track">
                    <input
                      aria-label="时间轴预览"
                      disabled={!state.sourcePath || !activeFrame || busy}
                      max={Math.max(timelineDuration, 0)}
                      min="0"
                      onChange={(event) => void loadFrameAtTime(Number(event.target.value))}
                      step={activeFrame?.fps ? 1 / activeFrame.fps : 0.1}
                      type="range"
                      value={Math.min(currentFrameTime, Math.max(timelineDuration, 0))}
                    />
                    <div className="timeline-markers">
                      {trackingKeyframes.map((keyframe) => (
                        <button
                          aria-label={`${keyframe.time.toFixed(2)}s 校准帧`}
                          className={`timeline-marker ${keyframeTone(keyframe)}`}
                          key={keyframe.index}
                          onClick={() => void loadFrameAtTime(keyframe.time)}
                          style={{
                            left: `${
                              (keyframe.index / Math.max(1, timelineFrameCount - 1)) * 100
                            }%`,
                          }}
                          type="button"
                        />
                      ))}
                    </div>
                  </div>
                </div>
                <button disabled={!activeFrame || !state.confirmedQuad || busy} onClick={saveCurrentKeyframe} type="button">
                  <Plus size={16} />
                  保存当前帧修正
                </button>
                <div className="keyframe-list">
                  {trackingKeyframes.length ? (
                    trackingKeyframes.map((keyframe) => (
                      <div className="keyframe-item" key={keyframe.index}>
                        <span>
                          {keyframe.time.toFixed(2)}s · 第 {keyframe.index} 帧 · {keyframe.source === "ai" ? `AI ${Math.round((keyframe.confidence ?? 0) * 100)}%` : "手动"}
                        </span>
                        <button
                          aria-label="删除关键帧"
                          className="icon-button"
                          onClick={() => removeKeyframe(keyframe.index)}
                          type="button"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <p className="muted-text">可在偏移处载入该秒画面，拖框后保存为修正关键帧。</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        <footer className="actions">
          <button disabled={!canAnalyze(state) || busy} onClick={runAnalyze} type="button">
            {state.status === "analyzing" ? <Loader2 className="spin" size={18} /> : <MousePointer2 size={18} />}
            载入首帧
          </button>
          <button disabled={!canTrack(state) || busy} onClick={() => void runTrack()} type="button">
            {state.status === "tracking" ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            开始追踪
          </button>
          <button disabled={!canRender(state) || busy} onClick={runRender} type="button">
            {state.status === "rendering" ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
            导出 MP4
          </button>
        </footer>
      </section>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function PanelTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h3>{title}</h3>
    </div>
  );
}

function Step({ done, label }: { done: boolean; label: string }) {
  return (
    <div className={done ? "step done" : "step"}>
      <CheckCircle2 size={16} />
      {label}
    </div>
  );
}

function StatusPanel({ message, status }: { message: string; status: string }) {
  return (
    <div className={`status status-${status}`}>
      <span>{status}</span>
      <p>{message}</p>
    </div>
  );
}

function keyframeTone(keyframe: TrackingKeyframe): string {
  if (keyframe.source === "ai") {
    return (keyframe.confidence ?? 0) < 0.65 ? "ai-low" : "ai";
  }
  return "manual";
}

function QuadEditor({
  disabled = false,
  quad,
  width,
  height,
  onChange,
}: {
  disabled?: boolean;
  quad: Quad | null;
  width: number;
  height: number;
  onChange: (quad: Quad) => void;
}) {
  const currentQuad = quad ?? [
    [0, 0],
    [0, 0],
    [0, 0],
    [0, 0],
  ];
  const [drag, setDrag] = useState<
    | { type: "point"; index: number }
    | { type: "move"; startX: number; startY: number; startQuad: Quad }
    | null
  >(null);
  const points = formatSvgQuadPoints(currentQuad, width, height);

  if (!quad) return null;

  function toFramePoint(event: React.PointerEvent, overlay: SVGSVGElement) {
    return clientPointToFrame(event.clientX, event.clientY, overlay.getBoundingClientRect(), width, height);
  }

  function onPointerMove(event: React.PointerEvent<SVGElement>) {
    if (disabled || !drag) return;
    const point = toFramePoint(event, event.currentTarget as SVGSVGElement);
    if (drag.type === "point") {
      onChange(moveQuadPoint(currentQuad, drag.index, point.x, point.y, width, height));
      return;
    }
    onChange(moveQuad(drag.startQuad, point.x - drag.startX, point.y - drag.startY, width, height));
  }

  return (
    <svg
      className={disabled ? "quad-overlay disabled" : "quad-overlay"}
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      onPointerMove={onPointerMove}
      onPointerUp={(event) => {
        event.currentTarget.releasePointerCapture(event.pointerId);
        setDrag(null);
      }}
      onPointerCancel={() => setDrag(null)}
    >
      <polygon className="quad-boundary-box" points={points} />
      <polygon
        className="quad-hit-area"
        points={points}
        onPointerDown={(event) => {
          if (disabled) return;
          const overlay = event.currentTarget.ownerSVGElement;
          if (!overlay) return;
          const point = toFramePoint(event, overlay);
          overlay.setPointerCapture(event.pointerId);
          setDrag({ type: "move", startX: point.x, startY: point.y, startQuad: currentQuad });
        }}
      />
      {currentQuad.map(([x, y], index) => (
        <g
          className="quad-corner-handle"
          key={index}
          onPointerDown={(event) => {
            if (disabled) return;
            event.stopPropagation();
            event.currentTarget.ownerSVGElement?.setPointerCapture(event.pointerId);
            setDrag({ type: "point", index });
          }}
        >
          <rect
            className="quad-corner-hit"
            x={(x / width) * 100 - 3.2}
            y={(y / height) * 100 - 3.2}
            width="6.4"
            height="6.4"
          />
          <path d={cornerPath(index, (x / width) * 100, (y / height) * 100)} />
        </g>
      ))}
    </svg>
  );
}

function cornerPath(index: number, x: number, y: number): string {
  const length = 4.8;
  const sx = index === 0 || index === 3 ? -1 : 1;
  const sy = index === 0 || index === 1 ? -1 : 1;
  return `M ${x} ${y + sy * length} L ${x} ${y} L ${x + sx * length} ${y}`;
}
