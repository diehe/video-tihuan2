from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .file_dialog import select_local_path as _select_local_path
from .pipeline import (
    EngineError,
    analyze_chroma_screen,
    analyze_target,
    generate_ai_keyframes,
    preview_chroma_replacement,
    read_frame_preview,
    render_chroma_replacement,
    render_replacement,
    track_region,
)
from .schemas import (
    AnalyzeResult,
    AudioPolicy,
    ChromaAnalyzeResult,
    ChromaPreviewResult,
    FramePreview,
    Quad,
    RenderResult,
    TrackingKeyframe,
    TrackingResult,
)

app = FastAPI(title="Video Tihuan Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    video_path: str
    prompt: str = "手动框选替换区域"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class TrackRequest(BaseModel):
    video_path: str
    initial_quad: Quad
    keyframes: list[TrackingKeyframe] = []


class FrameRequest(BaseModel):
    video_path: str
    time: float = 0


class AiKeyframesRequest(BaseModel):
    video_path: str
    reference_quad: Quad
    interval_seconds: float | None = None
    every_frame: bool = False
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class RenderRequest(BaseModel):
    source_path: str
    replacement_path: str
    tracking: TrackingResult
    output_path: str | None = None
    audio_policy: AudioPolicy = AudioPolicy.MIXED
    source_audio_volume: float = 100
    replacement_audio_volume: float = 100
    fit_mode: str = "stretch"


class ChromaAnalyzeRequest(BaseModel):
    source_path: str
    roi: dict[str, int] | None = None


class ChromaPreviewRequest(BaseModel):
    source_path: str
    replacement_path: str
    time: float = 0
    roi: dict[str, int] | None = None
    fit_mode: str = "cover"
    feather: int = 3
    mask_grow: int = 3


class ChromaRenderRequest(BaseModel):
    source_path: str
    replacement_path: str
    output_path: str | None = None
    roi: dict[str, int] | None = None
    audio_policy: AudioPolicy = AudioPolicy.MIXED
    source_audio_volume: float = 100
    replacement_audio_volume: float = 100
    fit_mode: str = "cover"
    feather: int = 3
    mask_grow: int = 3


class SelectPathResult(BaseModel):
    path: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/select-path", response_model=SelectPathResult)
def select_path(kind: Literal["video", "output"] = "video") -> SelectPathResult:
    return _guard(lambda: SelectPathResult(path=_select_local_path(kind)))


@app.post("/analyze", response_model=AnalyzeResult)
def analyze(request: AnalyzeRequest) -> AnalyzeResult:
    return _guard(
        lambda: analyze_target(
            request.video_path,
            request.prompt,
            api_key=request.api_key,
            base_url=request.base_url,
            model=request.model,
        )
    )


@app.post("/track", response_model=TrackingResult)
def track(request: TrackRequest) -> TrackingResult:
    return _guard(
        lambda: track_region(
            request.video_path,
            request.initial_quad,
            [keyframe.model_dump(mode="json") for keyframe in request.keyframes],
        )
    )


@app.post("/frame", response_model=FramePreview)
def frame(request: FrameRequest) -> FramePreview:
    return _guard(lambda: read_frame_preview(request.video_path, request.time))


@app.post("/ai-keyframes")
def ai_keyframes(request: AiKeyframesRequest):
    return _guard(
        lambda: generate_ai_keyframes(
            video_path=request.video_path,
            reference_quad=request.reference_quad,
            interval_seconds=request.interval_seconds,
            every_frame=request.every_frame,
            api_key=request.api_key,
            base_url=request.base_url,
            model=request.model,
        )
    )


@app.post("/render", response_model=RenderResult)
def render(request: RenderRequest) -> RenderResult:
    output_path = request.output_path
    if not output_path:
        output_path = str(Path(request.source_path).with_name("video-tihuan-output.mp4"))
    return _guard(
        lambda: render_replacement(
            source_path=request.source_path,
            replacement_path=request.replacement_path,
            tracking=request.tracking,
            output_path=output_path,
            audio_policy=request.audio_policy,
            source_audio_volume=request.source_audio_volume,
            replacement_audio_volume=request.replacement_audio_volume,
            fit_mode=request.fit_mode,
        )
    )


@app.post("/chroma/analyze", response_model=ChromaAnalyzeResult)
def chroma_analyze(request: ChromaAnalyzeRequest) -> ChromaAnalyzeResult:
    return _guard(lambda: analyze_chroma_screen(request.source_path, roi=request.roi))


@app.post("/chroma/preview", response_model=ChromaPreviewResult)
def chroma_preview(request: ChromaPreviewRequest) -> ChromaPreviewResult:
    return _guard(
        lambda: preview_chroma_replacement(
            source_path=request.source_path,
            replacement_path=request.replacement_path,
            time_seconds=request.time,
            roi=request.roi,
            fit_mode=request.fit_mode,
            feather=request.feather,
            mask_grow=request.mask_grow,
        )
    )


@app.post("/chroma/render", response_model=RenderResult)
def chroma_render(request: ChromaRenderRequest) -> RenderResult:
    output_path = request.output_path
    if not output_path:
        output_path = str(Path(request.source_path).with_name("video-tihuan-chroma-output.mp4"))
    return _guard(
        lambda: render_chroma_replacement(
            source_path=request.source_path,
            replacement_path=request.replacement_path,
            output_path=output_path,
            roi=request.roi,
            audio_policy=request.audio_policy,
            source_audio_volume=request.source_audio_volume,
            replacement_audio_volume=request.replacement_audio_volume,
            fit_mode=request.fit_mode,
            feather=request.feather,
            mask_grow=request.mask_grow,
        )
    )


def _guard(operation):
    try:
        return operation()
    except EngineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"处理失败: {exc}") from exc
