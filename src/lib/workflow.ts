import type {
  AnalyzeResult,
  AudioPolicy,
  ChromaAnalyzeResult,
  ChromaPreviewResult,
  FitMode,
  Quad,
  Rect,
  RenderResult,
  TrackingResult,
} from "./types";

export type JobStatus = "idle" | "analyzing" | "previewing" | "calibrating" | "tracking" | "rendering" | "done" | "error";

export interface AppState {
  backendUrl: string;
  apiBaseUrl: string;
  apiKey: string;
  model: string;
  sourcePath: string;
  replacementPath: string;
  outputPath: string;
  audioPolicy: AudioPolicy;
  sourceVolume: number;
  replacementVolume: number;
  fitMode: FitMode;
  feather: number;
  maskGrow: number;
  roi: Rect | null;
  chromaAnalysis: ChromaAnalyzeResult | null;
  chromaPreview: ChromaPreviewResult | null;
  analysis: AnalyzeResult | null;
  baseQuad: Quad | null;
  confirmedQuad: Quad | null;
  tracking: TrackingResult | null;
  renderResult: RenderResult | null;
  status: JobStatus;
  message: string;
}

export const initialState: AppState = {
  backendUrl: "http://127.0.0.1:8765",
  apiBaseUrl: "https://api.openai.com/v1",
  apiKey: "",
  model: "gpt-4.1-mini",
  sourcePath: "",
  replacementPath: "",
  outputPath: "",
  audioPolicy: "mixed",
  sourceVolume: 100,
  replacementVolume: 100,
  fitMode: "cover",
  feather: 3,
  maskGrow: 3,
  roi: null,
  chromaAnalysis: null,
  chromaPreview: null,
  analysis: null,
  baseQuad: null,
  confirmedQuad: null,
  tracking: null,
  renderResult: null,
  status: "idle",
  message: "选择视频后载入首帧，拖动四角框选替换区域。",
};

export type Action =
  | { type: "setBackendUrl"; backendUrl: string }
  | { type: "setApiBaseUrl"; apiBaseUrl: string }
  | { type: "setApiKey"; apiKey: string }
  | { type: "setModel"; model: string }
  | { type: "setSourcePath"; path: string }
  | { type: "setReplacementPath"; path: string }
  | { type: "setOutputPath"; path: string }
  | { type: "setAudioPolicy"; audioPolicy: AudioPolicy }
  | { type: "setSourceVolume"; volume: number }
  | { type: "setReplacementVolume"; volume: number }
  | { type: "setFitMode"; fitMode: FitMode }
  | { type: "setFeather"; feather: number }
  | { type: "setMaskGrow"; maskGrow: number }
  | { type: "setRoi"; roi: Rect | null }
  | { type: "setStatus"; status: JobStatus; message: string }
  | { type: "setChromaAnalysis"; analysis: ChromaAnalyzeResult }
  | { type: "setChromaPreview"; preview: ChromaPreviewResult }
  | { type: "setAnalysis"; analysis: AnalyzeResult }
  | { type: "setBaseQuad"; quad: Quad }
  | { type: "confirmQuad"; quad: Quad }
  | { type: "setPreviewQuad"; quad: Quad; updateBase?: boolean }
  | { type: "setTracking"; tracking: TrackingResult }
  | { type: "setRenderResult"; renderResult: RenderResult }
  | { type: "setError"; message: string }
  | { type: "resetResult" };

export function appReducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "setBackendUrl":
      return { ...state, backendUrl: action.backendUrl.trim() };
    case "setApiBaseUrl":
      return { ...state, apiBaseUrl: action.apiBaseUrl.trim() };
    case "setApiKey":
      return { ...state, apiKey: action.apiKey.trim() };
    case "setModel":
      return { ...state, model: action.model.trim() };
    case "setSourcePath":
      return resetPipeline({ ...state, sourcePath: action.path });
    case "setReplacementPath":
      return resetPipeline({ ...state, replacementPath: action.path });
    case "setOutputPath":
      return { ...state, outputPath: action.path };
    case "setAudioPolicy":
      return { ...state, audioPolicy: action.audioPolicy };
    case "setSourceVolume":
      return { ...state, sourceVolume: clampVolume(action.volume), renderResult: null };
    case "setReplacementVolume":
      return { ...state, replacementVolume: clampVolume(action.volume), renderResult: null };
    case "setFitMode":
      return { ...state, fitMode: action.fitMode };
    case "setFeather":
      return { ...state, feather: action.feather, chromaPreview: null, renderResult: null };
    case "setMaskGrow":
      return { ...state, maskGrow: action.maskGrow, chromaPreview: null, renderResult: null };
    case "setRoi":
      return { ...state, roi: action.roi, chromaPreview: null, renderResult: null };
    case "setStatus":
      return { ...state, status: action.status, message: action.message };
    case "setChromaAnalysis":
      return {
        ...state,
        chromaAnalysis: action.analysis,
        chromaPreview: null,
        roi: action.analysis.roi,
        renderResult: null,
        status: "idle",
        message: `已识别绿幕，覆盖率 ${Math.round(action.analysis.green_coverage * 100)}%。`,
      };
    case "setChromaPreview":
      return {
        ...state,
        chromaPreview: action.preview,
        status: "idle",
        message: `预览已生成，绿幕覆盖率 ${Math.round(action.preview.metrics.green_coverage * 100)}%。`,
      };
    case "setAnalysis":
      const initialQuad = action.analysis.candidates[0]?.quad ?? null;
      return {
        ...state,
        analysis: action.analysis,
        baseQuad: initialQuad,
        confirmedQuad: initialQuad,
        tracking: null,
        renderResult: null,
        status: "idle",
        message: "已载入首帧，可以拖动四角框选后开始追踪。",
      };
    case "setBaseQuad":
      return { ...state, baseQuad: action.quad, confirmedQuad: action.quad, tracking: null, renderResult: null };
    case "confirmQuad":
      return { ...state, confirmedQuad: action.quad, tracking: null, renderResult: null };
    case "setPreviewQuad":
      return {
        ...state,
        baseQuad: action.updateBase ? action.quad : state.baseQuad,
        confirmedQuad: action.quad,
        renderResult: null,
      };
    case "setTracking":
      return {
        ...state,
        tracking: action.tracking,
        status: "idle",
        message: `追踪完成，共 ${action.tracking.frame_count} 帧。`,
      };
    case "setRenderResult":
      return {
        ...state,
        renderResult: action.renderResult,
        status: "done",
        message: `导出完成：${action.renderResult.output_path}`,
      };
    case "setError":
      return { ...state, status: "error", message: action.message };
    case "resetResult":
      return resetPipeline(state);
    default:
      return state;
  }
}

function clampVolume(volume: number): number {
  return Math.max(0, Math.min(100, Math.round(volume)));
}

export function canAnalyze(state: AppState): boolean {
  return Boolean(state.backendUrl && state.sourcePath && state.replacementPath);
}

export function canPreview(state: AppState): boolean {
  return Boolean(state.backendUrl && state.sourcePath && state.replacementPath && state.chromaAnalysis);
}

export function canTrack(state: AppState): boolean {
  return Boolean(state.sourcePath && state.baseQuad);
}

export function canRender(state: AppState): boolean {
  if (state.chromaAnalysis) {
    return Boolean(state.backendUrl && state.sourcePath && state.replacementPath && state.roi);
  }
  return Boolean(state.sourcePath && state.replacementPath && state.baseQuad && state.tracking);
}

function resetPipeline(state: AppState): AppState {
  return {
    ...state,
    chromaAnalysis: null,
    chromaPreview: null,
    roi: null,
    analysis: null,
    baseQuad: null,
    confirmedQuad: null,
    tracking: null,
    renderResult: null,
    status: "idle",
    message: "输入已更新，请重新载入首帧。",
  };
}
