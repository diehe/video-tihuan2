import type { AnalyzeResult, AudioPolicy, FitMode, Quad, RenderResult, TrackingResult } from "./types";

export type JobStatus = "idle" | "analyzing" | "calibrating" | "tracking" | "rendering" | "done" | "error";

export interface AppState {
  backendUrl: string;
  apiBaseUrl: string;
  apiKey: string;
  model: string;
  sourcePath: string;
  replacementPath: string;
  outputPath: string;
  audioPolicy: AudioPolicy;
  fitMode: FitMode;
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
  audioPolicy: "original",
  fitMode: "stretch",
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
  | { type: "setFitMode"; fitMode: FitMode }
  | { type: "setStatus"; status: JobStatus; message: string }
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
    case "setFitMode":
      return { ...state, fitMode: action.fitMode };
    case "setStatus":
      return { ...state, status: action.status, message: action.message };
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

export function canAnalyze(state: AppState): boolean {
  return Boolean(state.backendUrl && state.sourcePath && state.replacementPath);
}

export function canTrack(state: AppState): boolean {
  return Boolean(state.sourcePath && state.baseQuad);
}

export function canRender(state: AppState): boolean {
  return Boolean(state.sourcePath && state.replacementPath && state.baseQuad && state.tracking);
}

function resetPipeline(state: AppState): AppState {
  return {
    ...state,
    analysis: null,
    baseQuad: null,
    confirmedQuad: null,
    tracking: null,
    renderResult: null,
    status: "idle",
    message: "输入已更新，请重新载入首帧。",
  };
}
