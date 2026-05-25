from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .schemas import (
    AiKeyframesResult,
    AnalyzeResult,
    AudioPolicy,
    Candidate,
    ChromaAnalyzeResult,
    ChromaFrameMetrics,
    FramePreview,
    Quad,
    RenderResult,
    TrackedFrame,
    TrackingKeyframe,
    TrackingResult,
)


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class EngineError(RuntimeError):
    pass


def analyze_target(
    video_path: str,
    prompt: str = "手动框选替换区域",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> AnalyzeResult:
    frame, fps, frame_count = _read_first_frame(video_path)
    height, width = frame.shape[:2]
    image = _encode_frame(frame)

    candidates: list[Candidate] = []
    green_candidate = _green_screen_candidate(frame)
    if green_candidate is not None:
        expanded_candidate = _expanded_green_screen_candidate(frame, green_candidate)
        if expanded_candidate is not None:
            candidates.append(expanded_candidate)
        candidates.append(green_candidate)

    if api_key:
        candidates.extend(
            _try_cloud_candidates(
                frame=frame,
                prompt=prompt,
                api_key=api_key,
                base_url=base_url or DEFAULT_BASE_URL,
                model=model or DEFAULT_MODEL,
            )
        )

    if not candidates:
        candidates = [_fallback_candidate(width, height)]

    return AnalyzeResult(
        frame=FramePreview(
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration=frame_count / fps if fps else 0,
            image=image,
        ),
        candidates=candidates,
    )


def read_frame_preview(video_path: str, time_seconds: float) -> FramePreview:
    capture = _open_capture(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    index = max(0, int(round(max(0.0, time_seconds) * fps)))
    if frame_count:
        index = min(index, frame_count - 1)
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise EngineError(f"无法读取指定时间的帧: {time_seconds:.2f}s")
    return FramePreview(
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration=frame_count / fps if fps else 0,
        image=_encode_frame(frame),
        index=index,
        time=index / fps,
    )


def generate_ai_keyframes(
    video_path: str,
    reference_quad: Quad,
    interval_seconds: float | None,
    every_frame: bool,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    detector=None,
) -> AiKeyframesResult:
    reference = _quad_array(reference_quad)
    capture = _open_capture(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ok, reference_frame = capture.read()
    if not ok:
        capture.release()
        raise EngineError(f"无法读取视频首帧: {video_path}")

    detector = detector or _try_cloud_keyframe
    keyframes: list[TrackingKeyframe] = []
    attempted = 0
    failed_calls = 0
    for index in _ai_keyframe_indices(frame_count, fps, interval_seconds, every_frame):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            continue
        attempted += 1
        try:
            detected = detector(
                reference_frame=reference_frame,
                current_frame=frame,
                reference_quad=_quad_list(reference),
                index=index,
                fps=fps,
                api_key=api_key,
                base_url=base_url or DEFAULT_BASE_URL,
                model=model or DEFAULT_MODEL,
            )
            quad = _valid_quad(detected.get("quad"), width, height)
            if quad is None:
                continue
            keyframes.append(
                TrackingKeyframe(
                    index=index,
                    time=index / fps,
                    quad=quad,
                    source="ai",
                    confidence=float(detected.get("confidence") or 0.65),
                    reason=str(detected.get("reason") or "AI 自动校准"),
                )
            )
        except Exception:
            failed_calls += 1
            continue
    capture.release()
    if attempted > 0 and failed_calls == attempted:
        raise EngineError(
            f"AI 校准请求全部失败：已尝试 {attempted} 帧。"
            "请检查 API Base URL、模型名、本地模型服务日志，以及该模型是否兼容 OpenAI chat/completions 视觉输入。"
        )
    return AiKeyframesResult(keyframes=keyframes)


def track_region(video_path: str, initial_quad: Quad, keyframes: list[dict[str, Any]] | None = None) -> TrackingResult:
    capture = _open_capture(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    ok, first = capture.read()
    if not ok:
        capture.release()
        raise EngineError(f"无法读取视频: {video_path}")

    initial = _quad_array(initial_quad)
    keyed = _tracking_keyed_quads(keyframes or [], frame_count)
    if 0 in keyed:
        initial = keyed[0]
    previous_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    reference_gray = previous_gray.copy()
    reference_quad = initial.copy()
    reference_points = _planar_reference_points(reference_gray, reference_quad)
    previous_quad = initial.copy()
    previous_points = _feature_points(previous_gray, initial)
    track_by_green = _green_coverage(first, initial) > 0.12
    frames = [TrackedFrame(index=0, time=0, quad=_quad_list(previous_quad), status="tracked")]

    index = 1
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if index in keyed:
            current_quad = keyed[index]
            status = "estimated"
            reference_gray = gray.copy()
            reference_quad = current_quad.copy()
            reference_points = _planar_reference_points(reference_gray, reference_quad)
            previous_points = _feature_points(gray, current_quad)
            track_by_green = _green_coverage(frame, current_quad) > 0.12
        else:
            used_green_tracking = False
            current_quad, status = _track_with_feature_matching(
                reference_gray,
                gray,
                reference_quad,
                previous_quad,
            )
            if status == "lost":
                current_quad, status = _track_with_planar_v2(
                    reference_gray,
                    gray,
                    reference_quad,
                    reference_points,
                    previous_quad,
                )

            if status != "lost":
                previous_points = _feature_points(gray, current_quad)
            else:
                green_quad = _green_quad_near(frame, previous_quad) if track_by_green else None
                if green_quad is not None and _is_plausible_transition(previous_quad, green_quad):
                    current_quad = green_quad
                    previous_points = _feature_points(gray, current_quad)
                    status = "estimated"
                    used_green_tracking = True

            if status == "lost":
                current_quad, previous_points, status = _track_with_optical_flow(
                    previous_gray,
                    gray,
                    previous_quad,
                    previous_points,
                )

            if status == "lost":
                contour_quad = _bright_quad_near(gray, previous_quad)
            else:
                contour_quad = None

            if contour_quad is not None and _is_plausible_transition(previous_quad, contour_quad):
                current_quad = contour_quad
                previous_points = _feature_points(gray, current_quad)
                status = "estimated"

            if status != "lost" and not used_green_tracking:
                current_quad = _refine_quad_by_edge_template(reference_gray, gray, reference_quad, current_quad)
                previous_points = _feature_points(gray, current_quad)

        frames.append(
            TrackedFrame(
                index=index,
                time=index / fps,
                quad=_quad_list(current_quad),
                status=status,
            )
        )
        previous_gray = gray
        previous_quad = current_quad
        index += 1

    capture.release()
    constraint_keyed = {0: initial.copy(), **keyed} if keyed else keyed
    frames = _apply_keyframe_constraints(frames, constraint_keyed)
    frames = _smooth_tracked_frames(frames, window=7, preserve_indices=set(constraint_keyed))
    return TrackingResult(frame_count=len(frames), fps=fps, width=width, height=height, frames=frames)

def render_replacement(
    source_path: str,
    replacement_path: str,
    tracking: TrackingResult,
    output_path: str,
    audio_policy: AudioPolicy = AudioPolicy.ORIGINAL,
    fit_mode: str = "stretch",
) -> RenderResult:
    source = _open_capture(source_path)
    replacement = _open_capture(replacement_path)
    fps = tracking.fps or source.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(source.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(source.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video-tihuan-") as temp_dir:
        temp_video = Path(temp_dir) / "video_only.mp4"
        writer = cv2.VideoWriter(
            str(temp_video),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise EngineError("无法创建导出视频")

        replacement_frames = _load_replacement_frames(replacement)
        if not replacement_frames:
            raise EngineError(f"无法读取替换视频: {replacement_path}")

        written = 0
        for frame_data in tracking.frames:
            ok, source_frame = source.read()
            if not ok:
                break
            replacement_frame = replacement_frames[written % len(replacement_frames)]
            composed = _composite_frame(source_frame, replacement_frame, _quad_array(frame_data.quad), fit_mode)
            writer.write(composed)
            written += 1

        writer.release()
        source.release()
        replacement.release()

        if audio_policy == AudioPolicy.SILENT:
            shutil.copyfile(temp_video, output)
        else:
            audio_source = source_path if audio_policy == AudioPolicy.ORIGINAL else replacement_path
            if not _mux_audio(temp_video, audio_source, output):
                shutil.copyfile(temp_video, output)

    return RenderResult(
        output_path=str(output),
        frame_count=written,
        duration=written / fps if fps else 0,
        audio_policy=audio_policy,
    )


def analyze_chroma_screen(video_path: str, roi: dict[str, int] | None = None) -> ChromaAnalyzeResult:
    frame, fps, frame_count = _read_first_frame(video_path)
    height, width = frame.shape[:2]
    normalized_roi = _normalize_roi(roi, width, height)
    mask = _chroma_mask(frame, normalized_roi)
    quad = _chroma_quad_from_mask(mask)
    return ChromaAnalyzeResult(
        frame=FramePreview(
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration=frame_count / fps if fps else 0,
            image=_encode_frame(frame),
        ),
        mask_image=_encode_frame(_mask_preview(frame, mask)),
        roi=normalized_roi,
        screen_quad=_quad_list(quad) if quad is not None else None,
        green_coverage=_mask_coverage(mask, normalized_roi),
    )


def compose_chroma_frame(
    source: np.ndarray,
    replacement: np.ndarray,
    roi: dict[str, int] | None = None,
    fit_mode: str = "cover",
    feather: int = 3,
    mask_grow: int = -1,
) -> tuple[np.ndarray, ChromaFrameMetrics]:
    height, width = source.shape[:2]
    normalized_roi = _normalize_roi(roi, width, height)
    raw_mask = _chroma_mask(source, normalized_roi)
    quad = _chroma_quad_from_mask(raw_mask)
    metrics = ChromaFrameMetrics(
        roi=normalized_roi,
        screen_quad=_quad_list(quad) if quad is not None else None,
        green_coverage=_mask_coverage(raw_mask, normalized_roi),
    )
    if quad is None:
        return source.copy(), metrics

    mask = _adjust_chroma_mask(raw_mask, feather=feather, mask_grow=mask_grow)
    warped = _warp_replacement_to_quad(replacement, quad, width, height, fit_mode)
    alpha = (mask.astype(np.float32) / 255.0)[:, :, None]
    composed = source.astype(np.float32) * (1 - alpha) + warped.astype(np.float32) * alpha
    return np.clip(composed, 0, 255).astype(np.uint8), metrics


def render_chroma_replacement(
    source_path: str,
    replacement_path: str,
    output_path: str,
    roi: dict[str, int] | None = None,
    audio_policy: AudioPolicy = AudioPolicy.ORIGINAL,
    fit_mode: str = "cover",
    feather: int = 3,
    mask_grow: int = -1,
) -> RenderResult:
    source = _open_capture(source_path)
    replacement = _open_capture(replacement_path)
    fps = source.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(source.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(source.get(cv2.CAP_PROP_FRAME_HEIGHT))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="video-tihuan-chroma-") as temp_dir:
        temp_video = Path(temp_dir) / "video_only.mp4"
        writer = cv2.VideoWriter(
            str(temp_video),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise EngineError("无法创建导出视频")

        replacement_frames = _load_replacement_frames(replacement)
        if not replacement_frames:
            raise EngineError(f"无法读取替换视频: {replacement_path}")

        written = 0
        while True:
            ok, source_frame = source.read()
            if not ok:
                break
            replacement_frame = replacement_frames[written % len(replacement_frames)]
            composed, _ = compose_chroma_frame(
                source_frame,
                replacement_frame,
                roi=roi,
                fit_mode=fit_mode,
                feather=feather,
                mask_grow=mask_grow,
            )
            writer.write(composed)
            written += 1

        writer.release()
        source.release()
        replacement.release()

        if audio_policy == AudioPolicy.SILENT:
            shutil.copyfile(temp_video, output)
        else:
            audio_source = source_path if audio_policy == AudioPolicy.ORIGINAL else replacement_path
            if not _mux_audio(temp_video, audio_source, output):
                shutil.copyfile(temp_video, output)

    return RenderResult(
        output_path=str(output),
        frame_count=written,
        duration=written / fps if fps else 0,
        audio_policy=audio_policy,
    )


def _try_cloud_candidates(
    frame: np.ndarray,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
) -> list[Candidate]:
    width = frame.shape[1]
    height = frame.shape[0]
    image_data = _encode_frame(frame)
    endpoint = _chat_completions_endpoint(base_url)
    system_prompt = (
        "你是视频平面替换助手。请只返回 JSON，不要解释。"
        "从图片中找出最符合用户描述的屏幕、招牌、海报或平面区域。"
        "返回格式: {\"candidates\":[{\"label\":\"...\",\"confidence\":0.0,"
        "\"quad\":[[x,y],[x,y],[x,y],[x,y]],\"reason\":\"...\"}]}"
        f"坐标必须在 0<=x<={width}, 0<=y<={height} 内，四角顺序为左上、右上、右下、左下。"
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data}},
                ],
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    try:
        result = subprocess.run(
            [
                "curl",
                "-sS",
                "--fail",
                "--max-time",
                "45",
                endpoint,
                *_keyframe_auth_headers(api_key),
                "-d",
                json.dumps(payload),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        content = json.loads(result.stdout)["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
        raw_candidates = parsed.get("candidates", [])
        candidates = []
        for index, item in enumerate(raw_candidates[:3]):
            quad = _clamp_quad(item["quad"], width, height)
            candidates.append(
                Candidate(
                    id=f"ai-{index + 1}",
                    label=str(item.get("label") or "AI 候选平面"),
                    quad=quad,
                    confidence=float(item.get("confidence") or 0.65),
                    reason=str(item.get("reason") or "根据描述和关键帧识别"),
                )
            )
        return candidates
    except Exception:
        return []


def _try_cloud_keyframe(
    reference_frame: np.ndarray,
    current_frame: np.ndarray,
    reference_quad: Quad,
    index: int,
    fps: float,
    api_key: str | None,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    width = current_frame.shape[1]
    height = current_frame.shape[0]
    endpoint = _chat_completions_endpoint(base_url)
    reference_crop = _crop_quad_region(reference_frame, reference_quad)
    system_prompt = (
        "你是视频平面追踪校准助手。请只返回 JSON，不要解释。"
        "任务是追踪同一个真实物理平面的四个外边界角点，不是识别画面内容。"
        "输入图片顺序：第一张是参考帧全图，第二张是参考帧中用户框出的目标裁剪图，第三张是当前帧全图。"
        "请用参考四角和裁剪图确认目标，在当前帧中找同一个物理平面边界。"
        "不要选择替换视频画面里的图案、文字、亮光、手机内部内容或相似广告内容；要贴合手机屏幕/海报/招牌等实体平面的可见边缘。"
        "如果目标被手指或物体遮挡，请根据未遮挡边缘推断被遮挡的原始平面角点。"
        "返回格式: {\"quad\":[[x,y],[x,y],[x,y],[x,y]],\"confidence\":0.0,\"reason\":\"...\"}。"
        f"坐标必须在 0<=x<={width}, 0<=y<={height} 内，四角顺序为左上、右上、右下、左下。"
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"参考帧目标四角是 {json.dumps(reference_quad)}。"
                            f"当前帧序号 {index}，时间 {index / fps:.3f}s。"
                            "请返回当前帧同一物理平面外边界四角。"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": _encode_frame(reference_frame)}},
                    {"type": "image_url", "image_url": {"url": _encode_frame(reference_crop)}},
                    {"type": "image_url", "image_url": {"url": _encode_frame(current_frame)}},
                ],
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "--fail",
            "--max-time",
            "45",
            endpoint,
            *_keyframe_auth_headers(api_key),
            "-d",
            json.dumps(payload),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EngineError(f"AI 校准请求失败: {result.stderr.strip() or result.stdout.strip() or endpoint}")
    content = json.loads(result.stdout)["choices"][0]["message"]["content"]
    return _parse_json_object(content)


def _chat_completions_endpoint(base_url: str) -> str:
    endpoint = base_url.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return f"{endpoint}/chat/completions"


def _keyframe_auth_headers(api_key: str | None) -> list[str]:
    headers: list[str] = []
    if api_key:
        headers.extend(["-H", f"Authorization: Bearer {api_key}"])
    headers.extend(["-H", "Content-Type: application/json"])
    return headers


def _crop_quad_region(frame: np.ndarray, quad: Quad) -> np.ndarray:
    points = _quad_array(quad)
    x, y, w, h = cv2.boundingRect(points.astype(np.int32))
    if w <= 1 or h <= 1:
        return frame

    margin = max(6, int(max(w, h) * 0.08))
    left = max(0, x - margin)
    top = max(0, y - margin)
    right = min(frame.shape[1], x + w + margin)
    bottom = min(frame.shape[0], y + h + margin)
    return frame[top:bottom, left:right]


def _fallback_candidate(width: int, height: int) -> Candidate:
    margin_x = width * 0.25
    margin_y = height * 0.25
    return Candidate(
        id="manual-1",
        label="需要确认的候选平面",
        confidence=0.45,
        quad=[
            [margin_x, margin_y],
            [width - margin_x, margin_y],
            [width - margin_x, height - margin_y],
            [margin_x, height - margin_y],
        ],
        reason="未使用或未成功调用云端识别，已提供中央区域供手动调整。",
    )


def _open_capture(path: str) -> cv2.VideoCapture:
    if not Path(path).exists():
        raise EngineError(f"文件不存在: {path}")
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise EngineError(f"无法打开视频: {path}")
    return capture


def _read_first_frame(video_path: str) -> tuple[np.ndarray, float, int]:
    capture = _open_capture(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise EngineError(f"无法读取视频首帧: {video_path}")
    return frame, fps, frame_count


def _encode_frame(frame: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise EngineError("无法编码关键帧")
    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def _quad_array(quad: Quad) -> np.ndarray:
    points = np.array(quad, dtype=np.float32)
    if points.shape != (4, 2):
        raise EngineError("四角坐标必须是 [[x,y], [x,y], [x,y], [x,y]]")
    return points


def _quad_list(quad: np.ndarray) -> Quad:
    return [[float(point[0]), float(point[1])] for point in quad.reshape(4, 2)]


def _feature_points(gray: np.ndarray, quad: np.ndarray) -> np.ndarray | None:
    edge_mask = np.zeros_like(gray)
    side_lengths = _quad_side_lengths(quad)
    thickness = max(4, int(min(side_lengths) * 0.055))
    cv2.polylines(edge_mask, [quad.astype(np.int32)], True, 255, thickness)
    corner_radius = max(6, thickness * 2)
    for point in quad.astype(np.int32):
        cv2.circle(edge_mask, tuple(point), corner_radius, 255, -1)

    points = cv2.goodFeaturesToTrack(gray, maxCorners=160, qualityLevel=0.008, minDistance=3, mask=edge_mask)
    if points is not None and len(points) >= 8:
        return points

    wider_edge_mask = np.zeros_like(gray)
    cv2.polylines(wider_edge_mask, [quad.astype(np.int32)], True, 255, max(6, thickness * 2))
    for point in quad.astype(np.int32):
        cv2.circle(wider_edge_mask, tuple(point), max(8, thickness * 3), 255, -1)
    return cv2.goodFeaturesToTrack(gray, maxCorners=160, qualityLevel=0.006, minDistance=3, mask=wider_edge_mask)


def _planar_tracking_mask(frame_shape: tuple[int, int] | tuple[int, int, int], quad: np.ndarray) -> np.ndarray:
    height, width = int(frame_shape[0]), int(frame_shape[1])
    mask = np.zeros((height, width), dtype=np.uint8)
    points = quad.astype(np.int32)
    side_lengths = _quad_side_lengths(quad.astype(np.float32))
    thickness = max(6, int(min(side_lengths) * 0.09))

    cv2.polylines(mask, [points], True, 255, thickness)
    for point in points:
        cv2.circle(mask, tuple(point), max(7, thickness * 2), 255, -1)

    polygon = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(polygon, points, 255)
    inner = np.zeros((height, width), dtype=np.uint8)
    inner_quad = _scale_quad(quad.astype(np.float32), scale_x=0.72, scale_y=0.72)
    cv2.fillConvexPoly(inner, inner_quad.astype(np.int32), 255)
    edge_band = cv2.bitwise_and(polygon, cv2.bitwise_not(inner))
    return cv2.bitwise_or(mask, edge_band)


def _planar_reference_points(gray: np.ndarray, quad: np.ndarray) -> np.ndarray:
    mask = _planar_tracking_mask(gray.shape, quad)
    points = cv2.goodFeaturesToTrack(gray, maxCorners=240, qualityLevel=0.006, minDistance=3, mask=mask)
    if points is not None and len(points) >= 12:
        return points.astype(np.float32)

    edge_points = cv2.findNonZero(cv2.bitwise_and(cv2.Canny(gray, 45, 150), mask))
    if edge_points is not None and len(edge_points) >= 12:
        step = max(1, len(edge_points) // 160)
        return edge_points[::step].astype(np.float32)

    sampled: list[list[float]] = []
    for start, end in zip(quad, np.roll(quad, -1, axis=0)):
        for amount in np.linspace(0.08, 0.92, 10):
            point = start + (end - start) * amount
            sampled.append([float(point[0]), float(point[1])])
    return np.array(sampled, dtype=np.float32).reshape(-1, 1, 2)


def _track_with_feature_matching(
    reference_gray: np.ndarray,
    gray: np.ndarray,
    reference_quad: np.ndarray,
    previous_quad: np.ndarray,
) -> tuple[np.ndarray, str]:
    detector, norm_type = _feature_match_detector()
    if detector is None:
        return previous_quad, "lost"

    reference_mask = _planar_tracking_mask(reference_gray.shape, reference_quad)
    current_mask = _planar_search_mask(gray.shape, previous_quad)
    ref_keypoints, ref_descriptors = detector.detectAndCompute(reference_gray, reference_mask)
    cur_keypoints, cur_descriptors = detector.detectAndCompute(gray, current_mask)
    if ref_descriptors is None or cur_descriptors is None:
        return previous_quad, "lost"
    if len(ref_keypoints) < 10 or len(cur_keypoints) < 10:
        return previous_quad, "lost"

    matcher = cv2.BFMatcher(norm_type)
    raw_matches = matcher.knnMatch(ref_descriptors, cur_descriptors, k=2)
    matches = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        best, second = pair
        if best.distance < second.distance * 0.76:
            matches.append(best)

    if len(matches) < 10:
        return previous_quad, "lost"

    reference_points = np.float32([ref_keypoints[match.queryIdx].pt for match in matches])
    current_points = np.float32([cur_keypoints[match.trainIdx].pt for match in matches])
    matrix, inliers = cv2.findHomography(reference_points, current_points, cv2.RANSAC, 3.0)
    if matrix is None or inliers is None:
        return previous_quad, "lost"

    inlier_count = int(inliers.sum())
    inlier_ratio = inlier_count / max(len(matches), 1)
    if inlier_count < 8 or inlier_ratio < 0.3:
        return previous_quad, "lost"

    current_quad = cv2.perspectiveTransform(reference_quad.reshape(1, 4, 2), matrix).reshape(4, 2)
    if not _is_plausible_transition(previous_quad, current_quad):
        return previous_quad, "lost"
    if not _is_plausible_planar_quad(reference_quad, current_quad):
        return previous_quad, "lost"
    return current_quad.astype(np.float32), "tracked"


def _feature_match_detector():
    if hasattr(cv2, "SIFT_create"):
        return cv2.SIFT_create(nfeatures=500, contrastThreshold=0.01, edgeThreshold=8), cv2.NORM_L2
    if hasattr(cv2, "AKAZE_create"):
        return cv2.AKAZE_create(), cv2.NORM_HAMMING
    return None, cv2.NORM_L2


def _planar_search_mask(frame_shape: tuple[int, int] | tuple[int, int, int], quad: np.ndarray) -> np.ndarray:
    height, width = int(frame_shape[0]), int(frame_shape[1])
    mask = np.zeros((height, width), dtype=np.uint8)
    expanded = _scale_quad(quad.astype(np.float32), scale_x=1.55, scale_y=1.55)
    expanded[:, 0] = np.clip(expanded[:, 0], 0, width - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, height - 1)
    cv2.fillConvexPoly(mask, expanded.astype(np.int32), 255)
    return mask


def _track_with_planar_v2(
    reference_gray: np.ndarray,
    gray: np.ndarray,
    reference_quad: np.ndarray,
    reference_points: np.ndarray,
    previous_quad: np.ndarray,
) -> tuple[np.ndarray, str]:
    if reference_points is None or len(reference_points) < 8:
        return previous_quad, "lost"

    next_points, status, _ = cv2.calcOpticalFlowPyrLK(
        reference_gray,
        gray,
        reference_points,
        None,
        winSize=(23, 23),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if next_points is None or status is None:
        return previous_quad, "lost"

    back_points, back_status, _ = cv2.calcOpticalFlowPyrLK(
        gray,
        reference_gray,
        next_points,
        None,
        winSize=(23, 23),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if back_points is None or back_status is None:
        return previous_quad, "lost"

    valid = (status.flatten() == 1) & (back_status.flatten() == 1)
    if not np.any(valid):
        return previous_quad, "lost"

    forward = reference_points.reshape(-1, 2)
    backward = back_points.reshape(-1, 2)
    fb_error = np.linalg.norm(forward - backward, axis=1)
    valid = valid & (fb_error < 2.5)
    good_reference = forward[valid]
    good_current = next_points.reshape(-1, 2)[valid]
    if len(good_reference) < 8:
        return previous_quad, "lost"

    matrix, inliers = cv2.findHomography(good_reference, good_current, cv2.RANSAC, 3.0)
    if matrix is None or inliers is None:
        return previous_quad, "lost"

    inlier_count = int(inliers.sum())
    inlier_ratio = inlier_count / max(len(good_reference), 1)
    if inlier_count < 8 or inlier_ratio < 0.28:
        return previous_quad, "lost"

    current_quad = cv2.perspectiveTransform(reference_quad.reshape(1, 4, 2), matrix).reshape(4, 2)
    if not _is_plausible_transition(previous_quad, current_quad):
        return previous_quad, "lost"
    if not _is_plausible_planar_quad(reference_quad, current_quad):
        return previous_quad, "lost"

    return current_quad.astype(np.float32), "tracked"


def _track_with_optical_flow(
    previous_gray: np.ndarray,
    gray: np.ndarray,
    previous_quad: np.ndarray,
    previous_points: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray | None, str]:
    if previous_points is None or len(previous_points) < 4:
        return previous_quad, _feature_points(gray, previous_quad), "lost"

    next_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, previous_points, None)
    if next_points is None or status is None:
        return previous_quad, _feature_points(gray, previous_quad), "lost"

    good_previous = previous_points[status.flatten() == 1].reshape(-1, 2)
    good_next = next_points[status.flatten() == 1].reshape(-1, 2)
    if len(good_previous) < 4:
        return previous_quad, _feature_points(gray, previous_quad), "lost"

    matrix, inliers = cv2.findHomography(good_previous, good_next, cv2.RANSAC, 4.0)
    if matrix is None or inliers is None or int(inliers.sum()) < 4:
        return previous_quad, _feature_points(gray, previous_quad), "lost"

    current_quad = cv2.perspectiveTransform(previous_quad.reshape(1, 4, 2), matrix).reshape(4, 2)
    if not _is_plausible_transition(previous_quad, current_quad):
        return previous_quad, _feature_points(gray, previous_quad), "lost"

    return current_quad.astype(np.float32), good_next.reshape(-1, 1, 2).astype(np.float32), "tracked"


def _refine_quad_by_template(
    reference_gray: np.ndarray,
    gray: np.ndarray,
    reference_quad: np.ndarray,
    current_quad: np.ndarray,
) -> np.ndarray:
    reference_rect = cv2.boundingRect(reference_quad.astype(np.int32))
    template = _crop_rect(reference_gray, reference_rect)
    if template is None or template.shape[0] < 12 or template.shape[1] < 12:
        return current_quad

    current_rect = cv2.boundingRect(current_quad.astype(np.int32))
    search_rect = _expand_rect(current_rect, gray.shape[1], gray.shape[0], padding=16)
    search = _crop_rect(gray, search_rect)
    if search is None or search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return current_quad

    template_edges = cv2.Canny(template, 60, 160)
    search_edges = cv2.Canny(search, 60, 160)
    result = cv2.matchTemplate(search_edges, template_edges, cv2.TM_CCOEFF_NORMED)
    _, score, _, max_loc = cv2.minMaxLoc(result)
    if score < 0.18:
        return current_quad

    matched_x = search_rect[0] + max_loc[0]
    matched_y = search_rect[1] + max_loc[1]
    dx = matched_x - current_rect[0]
    dy = matched_y - current_rect[1]
    refined = current_quad + np.array([dx, dy], dtype=np.float32)
    if not _is_plausible_transition(current_quad, refined):
        return current_quad
    return refined.astype(np.float32)


def _refine_quad_by_edge_template(
    reference_gray: np.ndarray,
    gray: np.ndarray,
    reference_quad: np.ndarray,
    current_quad: np.ndarray,
) -> np.ndarray:
    reference_rect = cv2.boundingRect(reference_quad.astype(np.int32))
    current_rect = cv2.boundingRect(current_quad.astype(np.int32))
    search_rect = _expand_rect(current_rect, gray.shape[1], gray.shape[0], padding=34)

    reference_edges = _masked_quad_edges(reference_gray, reference_quad)
    gray_edges = cv2.Canny(gray, 60, 160)
    template = _crop_rect(reference_edges, reference_rect)
    search = _crop_rect(gray_edges, search_rect)
    if template is None or search is None:
        return current_quad
    if template.shape[0] < 12 or template.shape[1] < 12:
        return current_quad
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return current_quad

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, max_loc = cv2.minMaxLoc(result)
    if score < 0.14:
        return current_quad

    matched_x = search_rect[0] + max_loc[0]
    matched_y = search_rect[1] + max_loc[1]
    refined = reference_quad + np.array([matched_x - reference_rect[0], matched_y - reference_rect[1]], dtype=np.float32)
    if not _is_plausible_transition(current_quad, refined):
        return current_quad
    return refined.astype(np.float32)


def _masked_quad_edges(gray: np.ndarray, quad: np.ndarray) -> np.ndarray:
    edge_mask = np.zeros_like(gray)
    side_lengths = _quad_side_lengths(quad)
    thickness = max(5, int(min(side_lengths) * 0.075))
    cv2.polylines(edge_mask, [quad.astype(np.int32)], True, 255, thickness)
    for point in quad.astype(np.int32):
        cv2.circle(edge_mask, tuple(point), max(8, thickness * 2), 255, -1)
    return cv2.bitwise_and(cv2.Canny(gray, 60, 160), edge_mask)


def _crop_rect(gray: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray | None:
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return None
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(gray.shape[1], x + w)
    y1 = min(gray.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return gray[y0:y1, x0:x1]


def _expand_rect(rect: tuple[int, int, int, int], width: int, height: int, padding: int) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    x0 = max(0, x - padding)
    y0 = max(0, y - padding)
    x1 = min(width, x + w + padding)
    y1 = min(height, y + h + padding)
    return x0, y0, x1 - x0, y1 - y0


def _is_plausible_transition(previous_quad: np.ndarray, current_quad: np.ndarray) -> bool:
    previous_area = abs(cv2.contourArea(previous_quad.astype(np.float32)))
    current_area = abs(cv2.contourArea(current_quad.astype(np.float32)))
    if previous_area < 25 or current_area < 25:
        return False

    area_ratio = current_area / previous_area
    if not 0.45 <= area_ratio <= 2.2:
        return False

    previous_center = previous_quad.mean(axis=0)
    current_center = current_quad.mean(axis=0)
    previous_diag = max(float(np.linalg.norm(previous_quad[2] - previous_quad[0])), 1.0)
    center_shift = float(np.linalg.norm(current_center - previous_center))
    if center_shift > max(18.0, previous_diag * 0.42):
        return False

    previous_sides = _quad_side_lengths(previous_quad)
    current_sides = _quad_side_lengths(current_quad)
    for previous_side, current_side in zip(previous_sides, current_sides):
        ratio = current_side / max(previous_side, 1.0)
        if not 0.35 <= ratio <= 2.8:
            return False

    return True


def _is_plausible_planar_quad(reference_quad: np.ndarray, current_quad: np.ndarray) -> bool:
    reference_area = abs(cv2.contourArea(reference_quad.astype(np.float32)))
    current_area = abs(cv2.contourArea(current_quad.astype(np.float32)))
    if reference_area < 25 or current_area < 25:
        return False

    area_ratio = current_area / reference_area
    if not 0.35 <= area_ratio <= 2.8:
        return False

    reference_sides = _quad_side_lengths(reference_quad)
    current_sides = _quad_side_lengths(current_quad)
    for reference_side, current_side in zip(reference_sides, current_sides):
        ratio = current_side / max(reference_side, 1.0)
        if not 0.25 <= ratio <= 3.2:
            return False

    return True


def _quad_side_lengths(quad: np.ndarray) -> list[float]:
    return [
        float(np.linalg.norm(quad[1] - quad[0])),
        float(np.linalg.norm(quad[2] - quad[1])),
        float(np.linalg.norm(quad[3] - quad[2])),
        float(np.linalg.norm(quad[0] - quad[3])),
    ]


def _bright_quad_near(gray: np.ndarray, previous_quad: np.ndarray) -> np.ndarray | None:
    _, threshold = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    previous_center = previous_quad.mean(axis=0)
    best: tuple[float, np.ndarray] | None = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 100:
            continue
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect).astype(np.float32)
        ordered = _order_quad(box)
        center = ordered.mean(axis=0)
        distance = float(np.linalg.norm(center - previous_center))
        score = area - distance * 20
        if best is None or score > best[0]:
            best = (score, ordered)
    return best[1] if best else None


def _order_quad(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2).astype(np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).flatten()
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def _green_screen_candidate(frame: np.ndarray) -> Candidate | None:
    quad = _green_quad_near(frame, None)
    if quad is None:
        return None

    area = abs(cv2.contourArea(quad.astype(np.float32)))
    frame_area = float(frame.shape[0] * frame.shape[1])
    confidence = min(0.95, max(0.55, area / max(frame_area * 0.18, 1.0)))
    return Candidate(
        id="green-screen",
        label="绿色屏幕候选",
        quad=_quad_list(quad),
        confidence=confidence,
        reason="检测到明显绿色屏幕区域，已优先作为替换平面。",
    )


def _expanded_green_screen_candidate(frame: np.ndarray, candidate: Candidate) -> Candidate | None:
    quad = _quad_array(candidate.quad)
    expanded = _scale_quad(quad, scale_x=1.15, scale_y=1.56)
    expanded[:, 0] = np.clip(expanded[:, 0], 0, frame.shape[1] - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, frame.shape[0] - 1)
    if cv2.contourArea(expanded.astype(np.float32)) <= cv2.contourArea(quad.astype(np.float32)) * 1.05:
        return None
    return Candidate(
        id="green-screen-expanded",
        label="扩展屏幕区域",
        quad=_quad_list(expanded),
        confidence=max(0.5, candidate.confidence - 0.08),
        reason="基于绿色屏幕向外扩展，用作 AE 式替换层大范围，手指和手机边框会作为上层遮挡保留。",
    )


def _scale_quad(quad: np.ndarray, scale_x: float, scale_y: float) -> np.ndarray:
    center = quad.mean(axis=0)
    scaled = quad.copy().astype(np.float32)
    scaled[:, 0] = center[0] + (scaled[:, 0] - center[0]) * scale_x
    scaled[:, 1] = center[1] + (scaled[:, 1] - center[1]) * scale_y
    return scaled


def _green_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([35, 70, 45]), np.array([90, 255, 255]))
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def _green_quad_near(frame: np.ndarray, previous_quad: np.ndarray | None) -> np.ndarray | None:
    mask = _green_mask(frame)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_area = frame.shape[0] * frame.shape[1]
    previous_center = previous_quad.mean(axis=0) if previous_quad is not None else None
    best: tuple[float, np.ndarray] | None = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < max(180.0, frame_area * 0.002):
            continue

        quad = _contour_quad(contour)
        if quad is None:
            continue

        if previous_center is None:
            score = area
        else:
            center = quad.mean(axis=0)
            distance = float(np.linalg.norm(center - previous_center))
            score = area - distance * 40
        if best is None or score > best[0]:
            best = (score, quad)

    return best[1] if best else None


def _contour_quad(contour: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for epsilon_ratio in (0.015, 0.025, 0.04, 0.06):
        approx = cv2.approxPolyDP(hull, epsilon_ratio * perimeter, True)
        if len(approx) == 4:
            return _order_quad(approx.reshape(4, 2).astype(np.float32))

    rect = cv2.minAreaRect(hull)
    box = cv2.boxPoints(rect).astype(np.float32)
    if abs(cv2.contourArea(box)) < 1:
        return None
    return _order_quad(box)


def _green_coverage(frame: np.ndarray, quad: np.ndarray) -> float:
    mask = _green_mask(frame)
    region = np.zeros(mask.shape, dtype=np.uint8)
    cv2.fillConvexPoly(region, quad.astype(np.int32), 255)
    region_area = cv2.countNonZero(region)
    if region_area == 0:
        return 0.0
    return cv2.countNonZero(cv2.bitwise_and(mask, region)) / region_area


def _smooth_tracked_frames(frames: list[TrackedFrame], window: int, preserve_indices: set[int] | None = None) -> list[TrackedFrame]:
    if len(frames) < 3:
        return frames

    preserve_indices = preserve_indices or set()
    half = max(1, window // 2)
    smoothed: list[TrackedFrame] = []
    for index, frame in enumerate(frames):
        if frame.index in preserve_indices or frame.status == "lost":
            smoothed.append(frame)
            continue
        previous_anchor = max((item for item in preserve_indices if item < frame.index), default=-1)
        next_anchor = min((item for item in preserve_indices if item > frame.index), default=len(frames))
        start = max(0, index - half, previous_anchor)
        end = min(len(frames), index + half + 1, next_anchor)
        quads = np.array(
            [
                frames[item].quad
                for item in range(start, end)
                if frames[item].status != "lost"
            ],
            dtype=np.float32,
        )
        if len(quads) < 2:
            smoothed.append(frame)
            continue
        smooth_quad = np.mean(quads, axis=0)
        smoothed.append(
            TrackedFrame(index=frame.index, time=frame.time, quad=_quad_list(smooth_quad), status=frame.status)
        )
    return smoothed


def _apply_keyframe_constraints(frames: list[TrackedFrame], keyed: dict[int, np.ndarray]) -> list[TrackedFrame]:
    if not keyed:
        return frames

    next_frames = list(frames)
    anchors = sorted(index for index in keyed if 0 <= index < len(frames))
    for anchor in anchors:
        current = next_frames[anchor]
        next_frames[anchor] = TrackedFrame(
            index=current.index,
            time=current.time,
            quad=_quad_list(keyed[anchor].astype(np.float32)),
            status="estimated" if anchor != 0 else current.status,
        )

    for start_index, end_index in zip(anchors, anchors[1:]):
        if end_index <= start_index + 1:
            continue
        start_quad = keyed[start_index]
        end_quad = keyed[end_index]
        span = end_index - start_index
        for index in range(start_index + 1, end_index):
            t = (index - start_index) / span
            baseline = start_quad * (1.0 - t) + end_quad * t
            current = next_frames[index]
            raw = np.array(current.quad, dtype=np.float32)
            constrained = _blend_tracking_residual(baseline, raw, current.status)
            next_frames[index] = TrackedFrame(
                index=current.index,
                time=current.time,
                quad=_quad_list(constrained.astype(np.float32)),
                status="estimated",
            )
    return _apply_single_keyframe_ramps(next_frames, keyed, anchors)


def _blend_tracking_residual(baseline: np.ndarray, raw: np.ndarray, status: str) -> np.ndarray:
    if status == "lost":
        return baseline

    residual = raw - baseline
    max_residual = max(float(np.linalg.norm(baseline[2] - baseline[0])) * 0.08, 12.0)
    lengths = np.linalg.norm(residual, axis=1)
    scale = np.ones_like(lengths, dtype=np.float32)
    mask = lengths > max_residual
    scale[mask] = max_residual / np.maximum(lengths[mask], 1e-6)
    capped = residual * scale[:, None]
    return baseline + capped * 0.35


def _apply_single_keyframe_ramps(
    frames: list[TrackedFrame],
    keyed: dict[int, np.ndarray],
    anchors: list[int],
    radius: int = 8,
) -> list[TrackedFrame]:
    next_frames = list(frames)
    anchor_set = set(anchors)
    for anchor in anchors:
        key_quad = keyed[anchor]
        previous_anchor = max((item for item in anchors if item < anchor), default=None)
        next_anchor = min((item for item in anchors if item > anchor), default=None)

        start = max(0, anchor - radius)
        if previous_anchor is not None:
            start = anchor
        end = min(len(frames) - 1, anchor + radius)
        if next_anchor is not None:
            end = anchor

        for index in range(start, end + 1):
            if index in anchor_set:
                continue
            distance = abs(index - anchor)
            if distance > radius:
                continue
            weight = (radius - distance + 1) / (radius + 1)
            current = next_frames[index]
            raw = np.array(current.quad, dtype=np.float32)
            blended = raw * (1.0 - weight) + key_quad * weight
            next_frames[index] = TrackedFrame(
                index=current.index,
                time=current.time,
                quad=_quad_list(blended.astype(np.float32)),
                status="estimated",
            )
    return next_frames


def _tracking_keyed_quads(keyframes: list[dict[str, Any]], frame_count: int) -> dict[int, np.ndarray]:
    keyed: dict[int, np.ndarray] = {}
    for item in keyframes:
        index = int(item.get("index", 0))
        if index >= 0 and (frame_count <= 0 or index < frame_count):
            keyed[index] = _quad_array(item["quad"])
    return keyed


def _ai_keyframe_indices(frame_count: int, fps: float, interval_seconds: float | None, every_frame: bool) -> list[int]:
    if frame_count <= 1:
        return []
    if every_frame:
        return list(range(1, frame_count))

    interval = max(float(interval_seconds or 0.5), 1 / max(fps, 1.0))
    step = max(1, int(round(interval * fps)))
    indices = list(range(step, frame_count, step))
    last = frame_count - 1
    if last not in indices:
        indices.append(last)
    return sorted(set(index for index in indices if index > 0))


def _load_replacement_frames(capture: cv2.VideoCapture) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    return frames


def _composite_frame(source: np.ndarray, replacement: np.ndarray, quad: np.ndarray, fit_mode: str) -> np.ndarray:
    h, w = source.shape[:2]
    target_w = max(2, int(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3]))))
    target_h = max(2, int(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1]))))
    fitted = _fit_frame(replacement, target_w, target_h, fit_mode)
    src_quad = np.array([[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src_quad, quad.astype(np.float32))
    warped = cv2.warpPerspective(fitted, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)

    mask = _replacement_mask(source, quad)
    mask = cv2.GaussianBlur(mask, (5, 5), 0)
    alpha = (mask.astype(np.float32) / 255.0)[:, :, None]
    composed = source.astype(np.float32) * (1 - alpha) + warped.astype(np.float32) * alpha
    return np.clip(composed, 0, 255).astype(np.uint8)


def _replacement_mask(source: np.ndarray, quad: np.ndarray) -> np.ndarray:
    h, w = source.shape[:2]
    polygon_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillConvexPoly(polygon_mask, quad.astype(np.int32), 255)
    return polygon_mask


def _fit_frame(frame: np.ndarray, target_w: int, target_h: int, fit_mode: str) -> np.ndarray:
    src_h, src_w = frame.shape[:2]
    if fit_mode == "stretch":
        return cv2.resize(frame, (target_w, target_h))

    if fit_mode == "contain":
        scale = min(target_w / src_w, target_h / src_h)
        resized = cv2.resize(frame, (max(1, int(src_w * scale)), max(1, int(src_h * scale))))
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        y = (target_h - resized.shape[0]) // 2
        x = (target_w - resized.shape[1]) // 2
        canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
        return canvas

    scale = max(target_w / src_w, target_h / src_h)
    resized = cv2.resize(frame, (max(1, math.ceil(src_w * scale)), max(1, math.ceil(src_h * scale))))
    y = max(0, (resized.shape[0] - target_h) // 2)
    x = max(0, (resized.shape[1] - target_w) // 2)
    return resized[y : y + target_h, x : x + target_w]


def _normalize_roi(roi: dict[str, int] | None, width: int, height: int) -> dict[str, int]:
    if not roi:
        return {"x": 0, "y": 0, "width": width, "height": height}

    x = int(round(float(roi.get("x", 0))))
    y = int(round(float(roi.get("y", 0))))
    w = int(round(float(roi.get("width", width))))
    h = int(round(float(roi.get("height", height))))
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    x1 = max(x + 1, min(width, x + max(1, w)))
    y1 = max(y + 1, min(height, y + max(1, h)))
    return {"x": x, "y": y, "width": x1 - x, "height": y1 - y}


def _chroma_mask(frame: np.ndarray, roi: dict[str, int]) -> np.ndarray:
    mask = _green_mask(frame)
    constrained = np.zeros(mask.shape, dtype=np.uint8)
    x, y, w, h = roi["x"], roi["y"], roi["width"], roi["height"]
    constrained[y : y + h, x : x + w] = mask[y : y + h, x : x + w]
    return constrained


def _chroma_quad_from_mask(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < 25:
        return None
    return _contour_quad(best)


def _adjust_chroma_mask(mask: np.ndarray, feather: int, mask_grow: int) -> np.ndarray:
    adjusted = mask.copy()
    if mask_grow != 0:
        kernel_size = max(1, abs(int(mask_grow)) * 2 + 1)
        kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
        if mask_grow > 0:
            adjusted = cv2.dilate(adjusted, kernel, iterations=1)
        else:
            adjusted = cv2.erode(adjusted, kernel, iterations=1)

    if feather > 0:
        radius = max(1, int(feather))
        kernel_size = radius * 2 + 1
        adjusted = cv2.GaussianBlur(adjusted, (kernel_size, kernel_size), 0)
    return adjusted


def _warp_replacement_to_quad(
    replacement: np.ndarray,
    quad: np.ndarray,
    width: int,
    height: int,
    fit_mode: str,
) -> np.ndarray:
    target_w = max(2, int(max(np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3]))))
    target_h = max(2, int(max(np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1]))))
    fitted = _fit_frame(replacement, target_w, target_h, fit_mode)
    src_quad = np.array(
        [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src_quad, quad.astype(np.float32))
    return cv2.warpPerspective(fitted, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


def _mask_coverage(mask: np.ndarray, roi: dict[str, int]) -> float:
    x, y, w, h = roi["x"], roi["y"], roi["width"], roi["height"]
    area = max(1, w * h)
    return cv2.countNonZero(mask[y : y + h, x : x + w]) / area


def _mask_preview(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    preview = frame.copy()
    green_layer = np.zeros_like(preview)
    green_layer[:, :] = (40, 230, 80)
    alpha = (mask.astype(np.float32) / 255.0)[:, :, None] * 0.55
    return np.clip(preview.astype(np.float32) * (1 - alpha) + green_layer.astype(np.float32) * alpha, 0, 255).astype(
        np.uint8
    )


def _mux_audio(video_only: Path, audio_source: str, output: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_only),
        "-i",
        audio_source,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return result.returncode == 0 and output.exists()


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return {}
        return json.loads(match.group(0))


def _clamp_quad(quad: Any, width: int, height: int) -> Quad:
    points = _quad_array(quad)
    points[:, 0] = np.clip(points[:, 0], 0, width)
    points[:, 1] = np.clip(points[:, 1], 0, height)
    return _quad_list(points)


def _valid_quad(quad: Any, width: int, height: int) -> Quad | None:
    points = _quad_array(quad)
    if np.any(points[:, 0] < 0) or np.any(points[:, 0] > width):
        return None
    if np.any(points[:, 1] < 0) or np.any(points[:, 1] > height):
        return None
    if abs(cv2.contourArea(points.astype(np.float32))) < 4:
        return None
    return _quad_list(points)
