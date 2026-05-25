export type Point = [number, number];
export type Quad = [Point, Point, Point, Point];
export type AudioPolicy = "original" | "replacement" | "silent";
export type FitMode = "stretch" | "cover" | "contain";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FramePreview {
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration: number;
  image: string;
  index: number;
  time: number;
}

export interface Candidate {
  id: string;
  label: string;
  quad: Quad;
  confidence: number;
  reason: string;
}

export interface AnalyzeResult {
  frame: FramePreview;
  candidates: Candidate[];
}

export interface ChromaFrameMetrics {
  roi: Rect;
  screen_quad: Quad | null;
  green_coverage: number;
}

export interface ChromaAnalyzeResult extends ChromaFrameMetrics {
  frame: FramePreview;
  mask_image: string;
}

export interface ChromaPreviewResult extends FramePreview {
  metrics: ChromaFrameMetrics;
}

export interface TrackedFrame {
  index: number;
  time: number;
  quad: Quad;
  status: "tracked" | "estimated" | "lost";
}

export interface TrackingResult {
  frame_count: number;
  fps: number;
  width?: number;
  height?: number;
  frames: TrackedFrame[];
}

export interface TrackingKeyframe {
  index: number;
  time: number;
  quad: Quad;
  source?: "manual" | "ai";
  confidence?: number;
  reason?: string;
}

export type AiCalibrationMode = "3" | "1" | "0.5" | "0.3" | "0.1" | "every";

export interface RenderResult {
  output_path: string;
  frame_count: number;
  duration: number;
  audio_policy: AudioPolicy;
}
