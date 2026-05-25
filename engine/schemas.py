from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Point = list[float]
Quad = list[Point]


class AudioPolicy(StrEnum):
    ORIGINAL = "original"
    REPLACEMENT = "replacement"
    SILENT = "silent"


class FramePreview(BaseModel):
    width: int
    height: int
    fps: float
    frame_count: int = 0
    duration: float = 0
    image: str
    index: int = 0
    time: float = 0


class Candidate(BaseModel):
    id: str
    label: str
    quad: Quad
    confidence: float = Field(ge=0, le=1)
    reason: str


class AnalyzeResult(BaseModel):
    frame: FramePreview
    candidates: list[Candidate]


class TrackedFrame(BaseModel):
    index: int
    time: float
    quad: Quad
    status: Literal["tracked", "estimated", "lost"]


class TrackingResult(BaseModel):
    frame_count: int
    fps: float
    width: int
    height: int
    frames: list[TrackedFrame]


class TrackingKeyframe(BaseModel):
    index: int
    time: float = 0
    quad: Quad
    source: Literal["manual", "ai"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = None


class AiKeyframesResult(BaseModel):
    keyframes: list[TrackingKeyframe]


class RenderResult(BaseModel):
    output_path: str
    frame_count: int
    duration: float
    audio_policy: AudioPolicy


class ChromaFrameMetrics(BaseModel):
    roi: dict[str, int]
    screen_quad: Quad | None = None
    green_coverage: float = 0


class ChromaAnalyzeResult(ChromaFrameMetrics):
    frame: FramePreview
    mask_image: str
