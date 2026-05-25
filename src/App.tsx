import {
  CheckCircle2,
  Download,
  Eye,
  FileVideo,
  FolderOpen,
  Loader2,
  Radio,
  Scissors,
  SlidersHorizontal,
  Wand2,
} from "lucide-react";
import { useReducer, useRef, useState } from "react";
import {
  analyzeChroma,
  healthCheck,
  previewChroma,
  renderChromaReplacement,
  selectLocalPath,
} from "./lib/api";
import type { FramePreview, Rect } from "./lib/types";
import { appReducer, canAnalyze, canPreview, canRender, initialState } from "./lib/workflow";

export function App() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [zoomedPreview, setZoomedPreview] = useState<string | null>(null);
  const busy = ["analyzing", "previewing", "rendering"].includes(state.status);
  const analysisFrame = state.chromaAnalysis?.frame ?? null;

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
    dispatch({ type: "setStatus", status: "analyzing", message: "正在识别限定区域内的绿幕..." });
    try {
      const analysis = await analyzeChroma({
        backendUrl: state.backendUrl,
        sourcePath: state.sourcePath,
        roi: state.roi,
      });
      dispatch({ type: "setChromaAnalysis", analysis });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "绿幕识别失败" });
    }
  }

  async function runPreview() {
    dispatch({ type: "setStatus", status: "previewing", message: "正在生成合成预览..." });
    try {
      const preview = await previewChroma({
        backendUrl: state.backendUrl,
        sourcePath: state.sourcePath,
        replacementPath: state.replacementPath,
        time: 0,
        roi: state.roi,
        fitMode: state.fitMode,
        feather: state.feather,
        maskGrow: state.maskGrow,
      });
      dispatch({ type: "setChromaPreview", preview });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "预览失败" });
    }
  }

  async function runRender() {
    dispatch({ type: "setStatus", status: "rendering", message: "正在逐帧扣绿并导出 MP4..." });
    try {
      const renderResult = await renderChromaReplacement(state.backendUrl, {
        sourcePath: state.sourcePath,
        replacementPath: state.replacementPath,
        outputPath: state.outputPath,
        roi: state.roi,
        audioPolicy: state.audioPolicy,
        sourceVolume: state.sourceVolume,
        replacementVolume: state.replacementVolume,
        fitMode: state.fitMode,
        feather: state.feather,
        maskGrow: state.maskGrow,
      });
      dispatch({ type: "setRenderResult", renderResult });
    } catch (error) {
      dispatch({ type: "setError", message: error instanceof Error ? error.message : "导出失败" });
    }
  }

  return (
    <main className="app-shell chroma-app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Scissors size={23} />
          </div>
          <div>
            <h1>绿幕视频替换</h1>
            <p>Mac 桌面扣绿合成向导</p>
          </div>
        </div>

        <StatusPanel message={state.message} status={state.status} />

        <div className="steps">
          <Step done={Boolean(state.sourcePath && state.replacementPath)} label="上传两个视频" />
          <Step done={Boolean(state.chromaAnalysis)} label="确认绿幕区域" />
          <Step done={Boolean(state.renderResult)} label="导出合成视频" />
        </div>

        <div className="quick-note">
          <Wand2 size={18} />
          <p>主流程只扣绿色像素，手机边框、手指和非绿色背景会保留下来。</p>
        </div>
      </aside>

      <section className="workspace">
        <header className="toolbar">
          <div>
            <h2>三步完成手机绿幕替换</h2>
            <p>选择主体视频和替换视频，必要时拖动限定区域，再导出 MP4。</p>
          </div>
          <button className="ghost-button" onClick={checkBackend} type="button">
            <Radio size={17} />
            {backendOnline === null ? "检查引擎" : backendOnline ? "引擎在线" : "引擎离线"}
          </button>
        </header>

        <div className="wizard-grid">
          <section className="panel input-panel">
            <PanelTitle icon={<FileVideo size={18} />} title="1. 上传视频" />
            <Field label="主体视频">
              <div className="path-row">
                <input
                  aria-label="主体视频"
                  value={state.sourcePath}
                  onChange={(event) => dispatch({ type: "setSourcePath", path: event.target.value })}
                  placeholder="/Users/me/source-green-phone.mp4"
                />
                <button className="secondary-button" onClick={() => choosePath("source")} type="button">
                  <FolderOpen size={15} />
                  选择
                </button>
              </div>
            </Field>
            <Field label="替换视频">
              <div className="path-row">
                <input
                  aria-label="替换视频"
                  value={state.replacementPath}
                  onChange={(event) => dispatch({ type: "setReplacementPath", path: event.target.value })}
                  placeholder="/Users/me/replacement.mp4"
                />
                <button className="secondary-button" onClick={() => choosePath("replacement")} type="button">
                  <FolderOpen size={15} />
                  选择
                </button>
              </div>
            </Field>
            <Field label="导出路径">
              <div className="path-row">
                <input
                  aria-label="导出路径"
                  value={state.outputPath}
                  onChange={(event) => dispatch({ type: "setOutputPath", path: event.target.value })}
                  placeholder="留空则输出到主体视频目录"
                />
                <button className="secondary-button" onClick={() => choosePath("output")} type="button">
                  <FolderOpen size={15} />
                  选择
                </button>
              </div>
            </Field>
            <button className="primary-action" disabled={!canAnalyze(state) || busy} onClick={runAnalyze} type="button">
              {state.status === "analyzing" ? <Loader2 className="spin" size={18} /> : <Scissors size={18} />}
              识别绿幕
            </button>
          </section>

          <section className="panel settings-panel">
            <PanelTitle icon={<SlidersHorizontal size={18} />} title="2. 确认绿幕" />
            <div className="settings-grid">
              <Field label="画面适配">
                <select value={state.fitMode} onChange={(event) => dispatch({ type: "setFitMode", fitMode: event.target.value as never })}>
                  <option value="cover">填满裁剪</option>
                  <option value="stretch">拉伸填满</option>
                  <option value="contain">完整留边</option>
                </select>
              </Field>
              <VolumeField
                label="主体视频音量"
                value={state.sourceVolume}
                onChange={(volume) => dispatch({ type: "setSourceVolume", volume })}
              />
              <VolumeField
                label="手机视频音量"
                value={state.replacementVolume}
                onChange={(volume) => dispatch({ type: "setReplacementVolume", volume })}
              />
              <Field label="边缘羽化">
                <input
                  aria-label="边缘羽化"
                  min="0"
                  max="12"
                  type="number"
                  value={state.feather}
                  onChange={(event) => dispatch({ type: "setFeather", feather: Number(event.target.value) })}
                />
              </Field>
              <Field label="边缘扩展">
                <input
                  aria-label="边缘扩展"
                  min="-8"
                  max="8"
                  type="number"
                  value={state.maskGrow}
                  onChange={(event) => dispatch({ type: "setMaskGrow", maskGrow: Number(event.target.value) })}
                />
              </Field>
            </div>

            <div className="preview-grid">
              <PreviewCard title="主体首帧">
                {analysisFrame ? (
                  <RoiEditor
                    frame={analysisFrame}
                    roi={state.roi}
                    onChange={(roi) => dispatch({ type: "setRoi", roi })}
                  />
                ) : (
                  <EmptyPreview text="识别后显示主体首帧" />
                )}
              </PreviewCard>
              <PreviewCard title="绿色 Mask">
                {state.chromaAnalysis ? <img src={state.chromaAnalysis.mask_image} alt="绿色 mask 预览" /> : <EmptyPreview text="等待绿幕识别" />}
              </PreviewCard>
              <PreviewCard title="合成预览">
                {state.chromaPreview ? (
                  <button
                    aria-label="放大合成预览"
                    className="preview-zoom-button"
                    onClick={() => setZoomedPreview(state.chromaPreview?.image ?? null)}
                    type="button"
                  >
                    <img src={state.chromaPreview.image} alt="合成预览" />
                    <span>点击放大</span>
                  </button>
                ) : (
                  <EmptyPreview text="生成预览后显示" />
                )}
              </PreviewCard>
            </div>

            <button className="secondary-action" disabled={!canPreview(state) || busy} onClick={runPreview} type="button">
              {state.status === "previewing" ? <Loader2 className="spin" size={18} /> : <Eye size={18} />}
              生成预览
            </button>
          </section>
        </div>

        <section className="panel export-panel">
          <div>
            <PanelTitle icon={<Download size={18} />} title="3. 导出合成视频" />
            <p className="muted-text">
              {state.renderResult
                ? `导出完成：${state.renderResult.output_path}`
                : "导出时会逐帧扣绿，只覆盖限定区域内的绿色像素。"}
            </p>
          </div>
          <button className="primary-action" disabled={!canRender(state) || busy} onClick={runRender} type="button">
            {state.status === "rendering" ? <Loader2 className="spin" size={18} /> : <CheckCircle2 size={18} />}
            导出 MP4
          </button>
        </section>
      </section>

      {zoomedPreview ? (
        <div
          aria-label="合成预览放大查看"
          aria-modal="true"
          className="preview-lightbox"
          onClick={() => setZoomedPreview(null)}
          role="dialog"
        >
          <div className="preview-lightbox-panel" onClick={(event) => event.stopPropagation()}>
            <button
              aria-label="关闭放大预览"
              className="preview-lightbox-close"
              onClick={() => setZoomedPreview(null)}
              type="button"
            >
              关闭
            </button>
            <img src={zoomedPreview} alt="合成预览放大图" />
          </div>
        </div>
      ) : null}
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

function VolumeField({ label, value, onChange }: { label: string; value: number; onChange: (volume: number) => void }) {
  return (
    <label className="field volume-field">
      <span>
        {label}
        <em>{value}%</em>
      </span>
      <input
        aria-label={label}
        max="100"
        min="0"
        onChange={(event) => onChange(Number(event.target.value))}
        type="range"
        value={value}
      />
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

function PreviewCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="preview-card">
      <strong>{title}</strong>
      <div className="preview-frame">{children}</div>
    </div>
  );
}

function EmptyPreview({ text }: { text: string }) {
  return <div className="empty-preview">{text}</div>;
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

function RoiEditor({
  frame,
  roi,
  onChange,
}: {
  frame: FramePreview;
  roi: Rect | null;
  onChange: (roi: Rect) => void;
}) {
  type RoiDrag =
    | {
        type: "move";
        pointerId: number;
        startX: number;
        startY: number;
        startRoi: Rect;
      }
    | {
        type: "resize";
        corner: "nw" | "ne" | "se" | "sw";
        pointerId: number;
        startX: number;
        startY: number;
        startRoi: Rect;
      };
  const activeRoi = roi ?? {
    x: Math.round(frame.width * 0.2),
    y: Math.round(frame.height * 0.15),
    width: Math.round(frame.width * 0.6),
    height: Math.round(frame.height * 0.7),
  };
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<RoiDrag | null>(null);

  function clientToFrame(event: React.PointerEvent<HTMLElement>) {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return { x: 0, y: 0 };
    }
    return {
      x: ((event.clientX - rect.left) / rect.width) * frame.width,
      y: ((event.clientY - rect.top) / rect.height) * frame.height,
    };
  }

  function clampRoi(next: Rect): Rect {
    const width = Math.max(8, Math.min(frame.width, Math.round(next.width)));
    const height = Math.max(8, Math.min(frame.height, Math.round(next.height)));
    const x = Math.max(0, Math.min(frame.width - width, Math.round(next.x)));
    const y = Math.max(0, Math.min(frame.height - height, Math.round(next.y)));
    return {
      x,
      y,
      width,
      height,
    };
  }

  function resizeRoi(startRoi: Rect, corner: "nw" | "ne" | "se" | "sw", dx: number, dy: number): Rect {
    if (corner === "nw") {
      return clampRoi({
        x: startRoi.x + dx,
        y: startRoi.y + dy,
        width: startRoi.width - dx,
        height: startRoi.height - dy,
      });
    }
    if (corner === "ne") {
      return clampRoi({
        x: startRoi.x,
        y: startRoi.y + dy,
        width: startRoi.width + dx,
        height: startRoi.height - dy,
      });
    }
    if (corner === "sw") {
      return clampRoi({
        x: startRoi.x + dx,
        y: startRoi.y,
        width: startRoi.width - dx,
        height: startRoi.height + dy,
      });
    }
    return clampRoi({
      x: startRoi.x,
      y: startRoi.y,
      width: startRoi.width + dx,
      height: startRoi.height + dy,
    });
  }

  return (
    <div
      className="roi-stage"
      ref={stageRef}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== event.pointerId) return;
        const current = clientToFrame(event);
        const dx = current.x - drag.startX;
        const dy = current.y - drag.startY;
        if (drag.type === "resize") {
          onChange(resizeRoi(drag.startRoi, drag.corner, dx, dy));
          return;
        }
        onChange(clampRoi({ ...drag.startRoi, x: drag.startRoi.x + dx, y: drag.startRoi.y + dy }));
      }}
      onPointerUp={(event) => {
        if (dragRef.current?.pointerId === event.pointerId) {
          event.currentTarget.releasePointerCapture(event.pointerId);
          dragRef.current = null;
        }
      }}
      onPointerCancel={() => {
        dragRef.current = null;
      }}
    >
      <img src={frame.image} alt="主体视频首帧" />
      <div
        aria-label="限定区域"
        className="roi-box"
        onPointerDown={(event) => {
          event.preventDefault();
          const point = clientToFrame(event);
          stageRef.current?.setPointerCapture(event.pointerId);
          dragRef.current = {
            type: "move",
            pointerId: event.pointerId,
            startX: point.x,
            startY: point.y,
            startRoi: activeRoi,
          };
        }}
        role="button"
        style={{
          left: `${(activeRoi.x / frame.width) * 100}%`,
          top: `${(activeRoi.y / frame.height) * 100}%`,
          width: `${(activeRoi.width / frame.width) * 100}%`,
          height: `${(activeRoi.height / frame.height) * 100}%`,
        }}
        tabIndex={0}
      >
        <span>限定手机区域</span>
        {(["nw", "ne", "se", "sw"] as const).map((corner) => (
          <i
            aria-label={`缩放限定区域 ${corner}`}
            className={`roi-handle ${corner}`}
            key={corner}
            onPointerDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
              const point = clientToFrame(event);
              stageRef.current?.setPointerCapture(event.pointerId);
              dragRef.current = {
                type: "resize",
                corner,
                pointerId: event.pointerId,
                startX: point.x,
                startY: point.y,
                startRoi: activeRoi,
              };
            }}
          />
        ))}
      </div>
    </div>
  );
}
