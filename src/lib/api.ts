import type {
  AiCalibrationMode,
  AnalyzeResult,
  AudioPolicy,
  ChromaAnalyzeResult,
  ChromaPreviewResult,
  FitMode,
  FramePreview,
  Quad,
  Rect,
  RenderResult,
  TrackingKeyframe,
  TrackingResult,
} from "./types";

interface AnalyzePayload {
  backendUrl: string;
  videoPath: string;
}

export async function healthCheck(backendUrl: string, fetcher: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetcher(`${trimUrl(backendUrl)}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export async function selectLocalPath(
  backendUrl: string,
  kind: "video" | "output",
  fetcher: typeof fetch = fetch,
): Promise<string> {
  const response = await fetcher(`${trimUrl(backendUrl)}/select-path?kind=${encodeURIComponent(kind)}`);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || "选择文件失败");
  }
  const data = (await response.json()) as { path?: string };
  return data.path || "";
}

export async function analyzeTarget(payload: AnalyzePayload, fetcher: typeof fetch = fetch): Promise<AnalyzeResult> {
  return postJson<AnalyzeResult>(
    `${trimUrl(payload.backendUrl)}/analyze`,
    {
      video_path: payload.videoPath,
      prompt: "手动框选替换区域",
    },
    fetcher,
  );
}

export async function analyzeChroma(
  payload: {
    backendUrl: string;
    sourcePath: string;
    roi?: Rect | null;
  },
  fetcher: typeof fetch = fetch,
): Promise<ChromaAnalyzeResult> {
  return postJson<ChromaAnalyzeResult>(
    `${trimUrl(payload.backendUrl)}/chroma/analyze`,
    {
      source_path: payload.sourcePath,
      roi: payload.roi ?? undefined,
    },
    fetcher,
  );
}

export async function previewChroma(
  payload: {
    backendUrl: string;
    sourcePath: string;
    replacementPath: string;
    time: number;
    roi?: Rect | null;
    fitMode: FitMode;
    feather: number;
    maskGrow: number;
  },
  fetcher: typeof fetch = fetch,
): Promise<ChromaPreviewResult> {
  return postJson<ChromaPreviewResult>(
    `${trimUrl(payload.backendUrl)}/chroma/preview`,
    {
      source_path: payload.sourcePath,
      replacement_path: payload.replacementPath,
      time: payload.time,
      roi: payload.roi ?? undefined,
      fit_mode: payload.fitMode,
      feather: payload.feather,
      mask_grow: payload.maskGrow,
    },
    fetcher,
  );
}

export async function trackRegion(
  backendUrl: string,
  videoPath: string,
  initialQuad: Quad,
  keyframes: TrackingKeyframe[] = [],
  fetcher: typeof fetch = fetch,
): Promise<TrackingResult> {
  return postJson<TrackingResult>(
    `${trimUrl(backendUrl)}/track`,
    {
      video_path: videoPath,
      initial_quad: initialQuad,
      keyframes: keyframes.map((keyframe) => ({ index: keyframe.index, quad: keyframe.quad })),
    },
    fetcher,
  );
}

export async function generateAiKeyframes(
  payload: {
    backendUrl: string;
    videoPath: string;
    referenceQuad: Quad;
    mode: AiCalibrationMode;
    apiKey: string;
    baseUrl: string;
    model: string;
  },
  fetcher: typeof fetch = fetch,
): Promise<TrackingKeyframe[]> {
  const everyFrame = payload.mode === "every";
  const intervalSeconds = everyFrame ? undefined : Number(payload.mode);
  const result = await postJson<{ keyframes: TrackingKeyframe[] }>(
    `${trimUrl(payload.backendUrl)}/ai-keyframes`,
    {
      video_path: payload.videoPath,
      reference_quad: payload.referenceQuad,
      every_frame: everyFrame,
      interval_seconds: intervalSeconds,
      api_key: payload.apiKey || undefined,
      base_url: payload.baseUrl,
      model: payload.model,
    },
    fetcher,
  );
  return result.keyframes;
}

export async function readFramePreview(
  backendUrl: string,
  videoPath: string,
  time: number,
  fetcher: typeof fetch = fetch,
): Promise<FramePreview> {
  return postJson<FramePreview>(
    `${trimUrl(backendUrl)}/frame`,
    { video_path: videoPath, time },
    fetcher,
  );
}

export async function renderReplacement(
  backendUrl: string,
  payload: {
    sourcePath: string;
    replacementPath: string;
    tracking: TrackingResult;
    outputPath?: string;
    audioPolicy: AudioPolicy;
    sourceVolume: number;
    replacementVolume: number;
    fitMode: FitMode;
  },
  fetcher: typeof fetch = fetch,
): Promise<RenderResult> {
  return postJson<RenderResult>(
    `${trimUrl(backendUrl)}/render`,
    {
      source_path: payload.sourcePath,
      replacement_path: payload.replacementPath,
      tracking: payload.tracking,
      output_path: payload.outputPath || undefined,
      audio_policy: payload.audioPolicy,
      source_audio_volume: payload.sourceVolume,
      replacement_audio_volume: payload.replacementVolume,
      fit_mode: payload.fitMode,
    },
    fetcher,
  );
}

export async function renderChromaReplacement(
  backendUrl: string,
  payload: {
    sourcePath: string;
    replacementPath: string;
    outputPath?: string;
    roi?: Rect | null;
    audioPolicy: AudioPolicy;
    sourceVolume: number;
    replacementVolume: number;
    fitMode: FitMode;
    feather: number;
    maskGrow: number;
  },
  fetcher: typeof fetch = fetch,
): Promise<RenderResult> {
  return postJson<RenderResult>(
    `${trimUrl(backendUrl)}/chroma/render`,
    {
      source_path: payload.sourcePath,
      replacement_path: payload.replacementPath,
      output_path: payload.outputPath || undefined,
      roi: payload.roi ?? undefined,
      audio_policy: payload.audioPolicy,
      source_audio_volume: payload.sourceVolume,
      replacement_audio_volume: payload.replacementVolume,
      fit_mode: payload.fitMode,
      feather: payload.feather,
      mask_grow: payload.maskGrow,
    },
    fetcher,
  );
}

async function postJson<T>(url: string, body: unknown, fetcher: typeof fetch): Promise<T> {
  const response = await fetcher(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

function trimUrl(url: string): string {
  return url.replace(/\/+$/, "");
}
