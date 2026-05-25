from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

import engine.api_server as api_server
import engine.pipeline as pipeline
from engine.pipeline import (
    _composite_frame,
    _chat_completions_endpoint,
    _fit_frame,
    _keyframe_auth_headers,
    _apply_keyframe_constraints,
    _planar_reference_points,
    _planar_tracking_mask,
    _refine_quad_by_template,
    _track_with_feature_matching,
    analyze_target,
    generate_ai_keyframes,
    read_frame_preview,
    render_replacement,
    track_region,
)
from engine.schemas import AudioPolicy, Quad, TrackedFrame


def _write_source_video(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (160, 120),
    )
    quads: list[Quad] = []
    for index in range(frames):
        offset = index
        quad: Quad = [
            [32 + offset, 28],
            [112 + offset, 26],
            [118 + offset, 86],
            [28 + offset, 88],
        ]
        quads.append(quad)
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (245, 245, 245))
        cv2.putText(frame, str(index), (8, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
        writer.write(frame)
    writer.release()
    return quads


def _write_replacement_video(path: Path, frames: int = 18) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (96, 64),
    )
    for index in range(frames):
        frame = np.zeros((64, 96, 3), dtype=np.uint8)
        frame[:, :] = (32, 210, 80)
        cv2.circle(frame, (12 + index * 3 % 72, 32), 10, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def _write_chroma_source_with_distractor(path: Path, frames: int = 12) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    quads: list[Quad] = []
    for index in range(frames):
        offset = index
        quad: Quad = [
            [72 + offset, 34],
            [146 + offset, 30],
            [152 + offset, 126],
            [66 + offset, 130],
        ]
        quads.append(quad)
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (36, 38, 42)
        cv2.rectangle(frame, (8, 10), (42, 58), (0, 245, 0), -1)
        cv2.putText(frame, "BG", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (0, 245, 0))
        cv2.polylines(frame, [np.array(quad, dtype=np.int32)], True, (8, 8, 8), 4)
        writer.write(frame)
    writer.release()
    return quads


def _write_video_with_bright_distractor(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (180, 130),
    )
    quads: list[Quad] = []
    for index in range(frames):
        offset = index
        quad: Quad = [
            [28 + offset, 35],
            [92 + offset, 32],
            [96 + offset, 92],
            [24 + offset, 95],
        ]
        quads.append(quad)
        frame = np.zeros((130, 180, 3), dtype=np.uint8)
        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (42, 58, 63))
        cv2.polylines(frame, [np.array(quad, dtype=np.int32)], True, (180, 190, 170), 2)
        for point in quad:
            cv2.circle(frame, (int(point[0]), int(point[1])), 4, (210, 220, 190), -1)
        cv2.line(frame, (int(35 + offset), 48), (int(84 + offset), 82), (150, 170, 160), 2)
        if index >= 3:
            cv2.rectangle(frame, (92, 14), (170, 112), (245, 245, 245), -1)
        writer.write(frame)
    writer.release()
    return quads


def _write_green_screen_video(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    quads: list[Quad] = []
    for index in range(frames):
        offset_x = index * 2
        offset_y = index // 3
        quad: Quad = [
            [62 + offset_x, 28 + offset_y],
            [146 + offset_x, 24 + offset_y],
            [152 + offset_x, 130 + offset_y],
            [56 + offset_x, 134 + offset_y],
        ]
        quads.append(quad)
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (48, 54, 58)
        cv2.rectangle(frame, (12, 18), (72, 136), (20, 120, 220), -1)
        cv2.putText(frame, "AD", (18, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (245, 245, 245), 3)
        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (0, 245, 0))
        cv2.polylines(frame, [np.array(quad, dtype=np.int32)], True, (8, 8, 8), 3)
        writer.write(frame)
    writer.release()
    return quads


def _write_jittery_green_screen_video(path: Path, frames: int = 18) -> Quad:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    stable_quad: Quad = [
        [62, 28],
        [146, 24],
        [152, 130],
        [56, 134],
    ]
    for index in range(frames):
        jitter = -3 if index % 2 else 3
        noisy_quad = [[x + jitter, y] for x, y in stable_quad]
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (48, 54, 58)
        cv2.polylines(frame, [np.array(stable_quad, dtype=np.int32)], True, (8, 8, 8), 5)
        cv2.fillConvexPoly(frame, np.array(noisy_quad, dtype=np.int32), (0, 245, 0))
        writer.write(frame)
    writer.release()
    return stable_quad


def _write_jump_green_screen_video(path: Path, frames: int = 18, jump_index: int = 8) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    first_quad: Quad = [
        [42, 28],
        [116, 28],
        [116, 130],
        [42, 130],
    ]
    second_quad: Quad = [
        [118, 30],
        [192, 30],
        [192, 132],
        [118, 132],
    ]
    quads: list[Quad] = []
    for index in range(frames):
        quad = second_quad if index >= jump_index else first_quad
        quads.append(quad)
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (48, 54, 58)
        cv2.fillConvexPoly(frame, np.array(quad, dtype=np.int32), (0, 245, 0))
        cv2.polylines(frame, [np.array(quad, dtype=np.int32)], True, (8, 8, 8), 3)
        writer.write(frame)
    writer.release()
    return quads


def _write_textureless_manual_keyframe_video(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    quads: list[Quad] = []
    for index in range(frames):
        t = index / max(1, frames - 1)
        quad: Quad = [
            [42 + 54 * t, 28 + 4 * t],
            [116 + 54 * t, 28 + 4 * t],
            [116 + 54 * t, 130 + 4 * t],
            [42 + 54 * t, 130 + 4 * t],
        ]
        quads.append(quad)
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (48, 54, 58)
        writer.write(frame)
    writer.release()
    return quads


def _write_video_with_moving_inner_content(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (220, 160),
    )
    quads: list[Quad] = []
    for index in range(frames):
        offset = index
        quad: Quad = [
            [62 + offset, 28],
            [146 + offset, 24],
            [152 + offset, 130],
            [56 + offset, 134],
        ]
        quads.append(quad)
        quad_array = np.array(quad, dtype=np.int32)
        frame = np.zeros((160, 220, 3), dtype=np.uint8)
        frame[:, :] = (42, 45, 47)
        cv2.fillConvexPoly(frame, quad_array, (28, 33, 35))
        mask = np.zeros((160, 220), dtype=np.uint8)
        cv2.fillConvexPoly(mask, quad_array, 255)
        for x in range(-80, 220, 18):
            cv2.line(frame, (x + index * 7, 20), (x + index * 7 + 80, 140), (30, 220, 80), 3)
        frame[mask == 0] = (42, 45, 47)
        cv2.polylines(frame, [quad_array], True, (230, 230, 220), 2)
        writer.write(frame)
    writer.release()
    return quads


def _write_perspective_planar_video(path: Path, frames: int = 18) -> list[Quad]:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        12,
        (240, 180),
    )
    quads: list[Quad] = []
    texture = np.zeros((120, 90, 3), dtype=np.uint8)
    texture[:, :] = (38, 42, 45)
    cv2.rectangle(texture, (2, 2), (87, 117), (225, 225, 210), 3)
    for y in range(10, 112, 16):
        cv2.line(texture, (4, y), (85, y + 8), (180, 190, 185), 1)
    for x in range(12, 82, 18):
        cv2.circle(texture, (x, 8), 3, (240, 240, 220), -1)
        cv2.circle(texture, (x, 112), 3, (240, 240, 220), -1)

    src_quad = np.array([[0, 0], [89, 0], [89, 119], [0, 119]], dtype=np.float32)
    for index in range(frames):
        offset = index * 1.5
        quad: Quad = [
            [68 + offset, 24 + index * 0.2],
            [154 + offset + index * 0.4, 30 + index * 0.5],
            [160 + offset - index * 0.15, 146 - index * 0.25],
            [58 + offset - index * 0.25, 138 + index * 0.35],
        ]
        quads.append(quad)
        frame = np.zeros((180, 240, 3), dtype=np.uint8)
        frame[:, :] = (28, 31, 34)
        matrix = cv2.getPerspectiveTransform(src_quad, np.array(quad, dtype=np.float32))
        warped = cv2.warpPerspective(texture, matrix, (240, 180), borderMode=cv2.BORDER_REPLICATE)
        mask = np.zeros((180, 240), dtype=np.uint8)
        cv2.fillConvexPoly(mask, np.array(quad, dtype=np.int32), 255)
        frame[mask > 0] = warped[mask > 0]
        cv2.circle(frame, (30 + index * 5, 90), 18, (230, 80, 80), -1)
        writer.write(frame)
    writer.release()
    return quads


def _quad_center(quad: Quad) -> tuple[float, float]:
    points = np.array(quad, dtype=np.float32)
    center = points.mean(axis=0)
    return float(center[0]), float(center[1])


def _quad_bounds(quad: Quad) -> tuple[float, float, float, float]:
    points = np.array(quad, dtype=np.float32)
    return (
        float(points[:, 0].min()),
        float(points[:, 1].min()),
        float(points[:, 0].max()),
        float(points[:, 1].max()),
    )


def test_analyze_target_without_api_returns_confirmable_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)

    result = analyze_target(str(source), "替换墙上的广告牌", api_key=None)

    assert result.frame.width == 160
    assert result.frame.height == 120
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.label == "需要确认的候选平面"
    assert len(candidate.quad) == 4
    assert 0 < candidate.confidence <= 1


def test_analyze_target_prefers_visible_green_screen_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_green_screen_video(source)

    result = analyze_target(str(source), "替换手机绿幕", api_key=None)

    candidate = next(item for item in result.candidates if item.id == "green-screen")
    expected_x, expected_y = _quad_center(expected_quads[0])
    actual_x, actual_y = _quad_center(candidate.quad)
    assert candidate.label == "绿色屏幕候选"
    assert abs(actual_x - expected_x) < 8
    assert abs(actual_y - expected_y) < 8


def test_analyze_target_adds_expanded_screen_candidate_for_green_screen(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_green_screen_video(source)

    result = analyze_target(str(source), "替换手机绿幕", api_key=None)

    green_area = cv2.contourArea(np.array(expected_quads[0], dtype=np.float32))
    expanded = next(candidate for candidate in result.candidates if candidate.id == "green-screen-expanded")
    expanded_area = cv2.contourArea(np.array(expanded.quad, dtype=np.float32))
    green_x0, green_y0, green_x1, green_y1 = _quad_bounds(expected_quads[0])
    expanded_x0, expanded_y0, expanded_x1, expanded_y1 = _quad_bounds(expanded.quad)
    green_width = green_x1 - green_x0
    green_height = green_y1 - green_y0
    expanded_width = expanded_x1 - expanded_x0
    expanded_height = expanded_y1 - expanded_y0
    assert result.candidates[0].id == "green-screen-expanded"
    assert expanded.label == "扩展屏幕区域"
    assert expanded_area > green_area * 1.45
    assert expanded_width < green_width * 1.2
    assert expanded_height > green_height * 1.4


def test_track_region_follows_translated_planar_area(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_source_video(source)

    result = track_region(str(source), expected_quads[0])

    assert result.frame_count == len(expected_quads)
    assert len(result.frames) == len(expected_quads)
    assert result.frames[-1].quad[0][0] > result.frames[0].quad[0][0] + 10
    assert result.frames[-1].status == "tracked"


def test_track_region_ignores_large_bright_distractor_near_target(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_video_with_bright_distractor(source)

    result = track_region(str(source), expected_quads[0])

    expected_x, expected_y = _quad_center(expected_quads[-1])
    actual_x, actual_y = _quad_center(result.frames[-1].quad)
    assert abs(actual_x - expected_x) < 16
    assert abs(actual_y - expected_y) < 16


def test_track_region_follows_textureless_green_screen_by_color(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_green_screen_video(source)

    result = track_region(str(source), expected_quads[0])

    expected_x, expected_y = _quad_center(expected_quads[-1])
    actual_x, actual_y = _quad_center(result.frames[-1].quad)
    assert abs(actual_x - expected_x) < 8
    assert abs(actual_y - expected_y) < 8


def test_track_region_stabilizes_green_screen_edge_jitter(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    stable_quad = _write_jittery_green_screen_video(source)

    result = track_region(str(source), stable_quad)

    centers = [_quad_center(frame.quad)[0] for frame in result.frames]
    frame_to_frame_jitter = [abs(current - previous) for previous, current in zip(centers, centers[1:])]
    assert max(frame_to_frame_jitter) < 3.0


def test_track_region_prefers_planar_edges_over_green_contour_when_available(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    stable_quad = _write_jittery_green_screen_video(source)

    result = track_region(str(source), stable_quad)

    assert result.frames[1].status == "tracked"


def test_track_region_uses_screen_edge_not_moving_inner_content(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_video_with_moving_inner_content(source)

    result = track_region(str(source), expected_quads[0])

    expected_x, expected_y = _quad_center(expected_quads[-1])
    actual_x, actual_y = _quad_center(result.frames[-1].quad)
    expected_area = cv2.contourArea(np.array(expected_quads[-1], dtype=np.float32))
    actual_area = cv2.contourArea(np.array(result.frames[-1].quad, dtype=np.float32))
    assert abs(actual_x - expected_x) < 12
    assert abs(actual_y - expected_y) < 12
    assert 0.8 <= actual_area / expected_area <= 1.2


def test_planar_tracking_mask_prefers_edges_over_dynamic_interior() -> None:
    quad = np.array([[40, 24], [150, 24], [150, 130], [40, 130]], dtype=np.float32)
    mask = _planar_tracking_mask((160, 220), quad)

    assert mask[28, 44] == 255
    assert mask[126, 146] == 255
    assert mask[78, 95] == 0


def test_planar_reference_points_track_perspective_plane(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_perspective_planar_video(source)
    capture = cv2.VideoCapture(str(source))
    ok, first_frame = capture.read()
    capture.release()
    assert ok

    result = track_region(str(source), expected_quads[0])

    expected_x, expected_y = _quad_center(expected_quads[-1])
    actual_x, actual_y = _quad_center(result.frames[-1].quad)
    expected_area = cv2.contourArea(np.array(expected_quads[-1], dtype=np.float32))
    actual_area = cv2.contourArea(np.array(result.frames[-1].quad, dtype=np.float32))
    first_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    assert len(_planar_reference_points(first_gray, np.array(expected_quads[0], dtype=np.float32))) >= 12
    assert abs(actual_x - expected_x) < 8
    assert abs(actual_y - expected_y) < 8
    assert 0.75 <= actual_area / expected_area <= 1.25


def test_feature_matching_tracker_estimates_perspective_plane(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_perspective_planar_video(source)
    capture = cv2.VideoCapture(str(source))
    ok, first_frame = capture.read()
    assert ok
    for _ in range(len(expected_quads) - 2):
        ok, current_frame = capture.read()
        assert ok
    capture.release()

    current_quad, status = _track_with_feature_matching(
        cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY),
        cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY),
        np.array(expected_quads[0], dtype=np.float32),
        np.array(expected_quads[-1], dtype=np.float32),
    )

    expected_x, expected_y = _quad_center(expected_quads[-1])
    actual_x, actual_y = _quad_center(current_quad)
    assert status == "tracked"
    assert abs(actual_x - expected_x) < 8
    assert abs(actual_y - expected_y) < 8


def test_track_region_applies_manual_keyframes_between_corrections(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_green_screen_video(source)

    result = track_region(
        str(source),
        expected_quads[0],
        keyframes=[
            {"index": 0, "quad": expected_quads[0]},
            {"index": len(expected_quads) - 1, "quad": expected_quads[-1]},
        ],
    )

    midpoint = len(expected_quads) // 2
    expected_x, expected_y = _quad_center(expected_quads[midpoint])
    actual_x, actual_y = _quad_center(result.frames[midpoint].quad)
    assert result.frames[-1].quad == expected_quads[-1]
    assert abs(actual_x - expected_x) < 2
    assert abs(actual_y - expected_y) < 2


def test_track_region_interpolates_between_manual_keyframes_when_tracking_is_lost(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_textureless_manual_keyframe_video(source)

    result = track_region(
        str(source),
        expected_quads[0],
        keyframes=[
            {"index": 0, "quad": expected_quads[0]},
            {"index": len(expected_quads) - 1, "quad": expected_quads[-1]},
        ],
    )

    midpoint = len(expected_quads) // 2
    expected_x, expected_y = _quad_center(expected_quads[midpoint])
    actual_x, actual_y = _quad_center(result.frames[midpoint].quad)
    assert result.frames[midpoint].status == "estimated"
    assert abs(actual_x - expected_x) < 2
    assert abs(actual_y - expected_y) < 2


def test_keyframe_constraints_keep_only_small_tracking_residuals() -> None:
    start: Quad = [[0, 0], [100, 0], [100, 100], [0, 100]]
    end: Quad = [[20, 0], [120, 0], [120, 100], [20, 100]]
    raw_mid: Quad = [[70, 0], [170, 0], [170, 100], [70, 100]]
    frames = [
        TrackedFrame(index=0, time=0, quad=start, status="tracked"),
        TrackedFrame(index=1, time=1 / 24, quad=raw_mid, status="tracked"),
        TrackedFrame(index=2, time=2 / 24, quad=end, status="tracked"),
    ]

    result = _apply_keyframe_constraints(
        frames,
        {0: np.array(start, dtype=np.float32), 2: np.array(end, dtype=np.float32)},
    )

    center_x, _ = _quad_center(result[1].quad)
    baseline_center_x = 60
    raw_center_x = 120
    assert result[0].quad == start
    assert result[2].quad == end
    assert result[1].status == "estimated"
    assert abs(center_x - baseline_center_x) < 6
    assert abs(center_x - baseline_center_x) < abs(raw_center_x - baseline_center_x)


def test_keyframe_constraints_ramp_into_single_manual_keyframe() -> None:
    key_quad: Quad = [[80, 0], [180, 0], [180, 100], [80, 100]]
    raw_quad: Quad = [[0, 0], [100, 0], [100, 100], [0, 100]]
    frames = [
        TrackedFrame(index=index, time=index / 24, quad=raw_quad if index != 8 else key_quad, status="tracked")
        for index in range(17)
    ]

    result = _apply_keyframe_constraints(frames, {8: np.array(key_quad, dtype=np.float32)})

    near_x, _ = _quad_center(result[7].quad)
    far_x, _ = _quad_center(result[0].quad)
    key_x, _ = _quad_center(result[8].quad)
    assert result[8].quad == key_quad
    assert near_x > far_x
    assert near_x < key_x
    assert result[7].status == "estimated"


def test_track_region_restarts_tracking_from_manual_keyframe(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    jump_index = 8
    expected_quads = _write_jump_green_screen_video(source, jump_index=jump_index)

    result = track_region(
        str(source),
        expected_quads[0],
        keyframes=[{"index": jump_index, "quad": expected_quads[jump_index]}],
    )

    first_x, first_y = _quad_center(result.frames[0].quad)
    expected_first_x, expected_first_y = _quad_center(expected_quads[0])
    before_x, _ = _quad_center(result.frames[jump_index - 1].quad)
    keyed_x, keyed_y = _quad_center(result.frames[jump_index].quad)
    expected_keyed_x, expected_keyed_y = _quad_center(expected_quads[jump_index])
    after_x, after_y = _quad_center(result.frames[jump_index + 3].quad)
    expected_after_x, expected_after_y = _quad_center(expected_quads[jump_index + 3])

    assert abs(first_x - expected_first_x) < 2
    assert abs(first_y - expected_first_y) < 2
    assert expected_first_x < before_x < expected_keyed_x
    assert abs(keyed_x - expected_keyed_x) < 2
    assert abs(keyed_y - expected_keyed_y) < 2
    assert abs(after_x - expected_after_x) < 2
    assert abs(after_y - expected_after_y) < 2


def test_read_frame_preview_returns_requested_time_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source, frames=18)

    preview = read_frame_preview(str(source), time_seconds=0.75)

    assert preview.width == 160
    assert preview.height == 120
    assert preview.fps == 12
    assert preview.frame_count == 18
    assert preview.duration == 1.5
    assert preview.index == 9
    assert preview.time == 0.75
    assert preview.image.startswith("data:image/jpeg;base64,")


def test_generate_ai_keyframes_samples_interval_frames(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    quads = _write_source_video(source, frames=18)

    result = generate_ai_keyframes(
        video_path=str(source),
        reference_quad=quads[0],
        interval_seconds=0.5,
        every_frame=False,
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="vision-model",
        detector=lambda **kwargs: {"quad": quads[kwargs["index"]], "confidence": 0.82, "reason": "ok"},
    )

    assert [frame.index for frame in result.keyframes] == [6, 12, 17]
    assert all(frame.source == "ai" for frame in result.keyframes)


def test_generate_ai_keyframes_samples_every_non_reference_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    quads = _write_source_video(source, frames=5)

    result = generate_ai_keyframes(
        video_path=str(source),
        reference_quad=quads[0],
        interval_seconds=None,
        every_frame=True,
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="vision-model",
        detector=lambda **kwargs: {"quad": quads[kwargs["index"]], "confidence": 0.82, "reason": "ok"},
    )

    assert [frame.index for frame in result.keyframes] == [1, 2, 3, 4]


def test_generate_ai_keyframes_skips_invalid_model_results(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    quads = _write_source_video(source, frames=8)

    result = generate_ai_keyframes(
        video_path=str(source),
        reference_quad=quads[0],
        interval_seconds=0.5,
        every_frame=False,
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="vision-model",
        detector=lambda **kwargs: {"quad": [[-50, -50], [999, -50], [999, 999], [-50, 999]], "confidence": 0.82},
    )

    assert result.keyframes == []


def test_ai_keyframes_can_restart_tracking(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    jump_index = 8
    expected_quads = _write_jump_green_screen_video(source, jump_index=jump_index)
    ai_result = generate_ai_keyframes(
        video_path=str(source),
        reference_quad=expected_quads[0],
        interval_seconds=jump_index / 12,
        every_frame=False,
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="vision-model",
        detector=lambda **kwargs: {"quad": expected_quads[kwargs["index"]], "confidence": 0.9},
    )

    tracking = track_region(
        str(source),
        expected_quads[0],
        keyframes=[frame.model_dump(mode="json") for frame in ai_result.keyframes],
    )

    actual_x, actual_y = _quad_center(tracking.frames[jump_index + 2].quad)
    expected_x, expected_y = _quad_center(expected_quads[jump_index + 2])
    assert abs(actual_x - expected_x) < 2
    assert abs(actual_y - expected_y) < 2


def test_chat_completions_endpoint_accepts_base_url_or_full_endpoint() -> None:
    assert _chat_completions_endpoint("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1/chat/completions"
    assert (
        _chat_completions_endpoint("http://127.0.0.1:1234/v1/chat/completions")
        == "http://127.0.0.1:1234/v1/chat/completions"
    )


def test_keyframe_auth_headers_are_optional_for_local_models() -> None:
    assert _keyframe_auth_headers("") == ["-H", "Content-Type: application/json"]
    assert _keyframe_auth_headers("sk-test") == [
        "-H",
        "Authorization: Bearer sk-test",
        "-H",
        "Content-Type: application/json",
    ]


def test_chroma_analyze_respects_roi(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    expected_quads = _write_chroma_source_with_distractor(source)

    result = pipeline.analyze_chroma_screen(
        str(source),
        roi={"x": 54, "y": 22, "width": 128, "height": 126},
    )

    expected_x, expected_y = _quad_center(expected_quads[0])
    actual_x, actual_y = _quad_center(result.screen_quad)
    assert abs(actual_x - expected_x) < 8
    assert abs(actual_y - expected_y) < 8
    assert result.green_coverage > 0.2
    assert result.roi == {"x": 54, "y": 22, "width": 128, "height": 126}


def test_compose_chroma_frame_only_replaces_green_pixels_inside_roi() -> None:
    source = np.zeros((120, 180, 3), dtype=np.uint8)
    source[:, :] = (32, 34, 38)
    cv2.rectangle(source, (8, 8), (42, 42), (0, 245, 0), -1)
    cv2.rectangle(source, (72, 24), (136, 96), (0, 245, 0), -1)
    cv2.rectangle(source, (68, 20), (140, 100), (5, 5, 5), 3)
    replacement = np.zeros((64, 64, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed, metrics = pipeline.compose_chroma_frame(
        source,
        replacement,
        roi={"x": 58, "y": 14, "width": 92, "height": 96},
        fit_mode="cover",
        feather=0,
        mask_grow=0,
    )

    assert composed[60, 100, 2] > 160
    assert composed[60, 100, 1] < 90
    assert composed[24, 68, 2] < 40
    assert composed[20, 20, 1] > 180
    assert metrics.green_coverage > 0.2


def test_compose_chroma_frame_default_settings_cover_green_edge_halo() -> None:
    source = np.zeros((140, 190, 3), dtype=np.uint8)
    source[:, :] = (32, 34, 38)
    cv2.rectangle(source, (58, 18), (142, 122), (0, 245, 0), -1)
    cv2.rectangle(source, (62, 24), (138, 116), (0, 150, 0), 2)
    replacement = np.zeros((72, 72, 3), dtype=np.uint8)
    replacement[:, :] = (36, 28, 220)

    composed, _ = pipeline.compose_chroma_frame(
        source,
        replacement,
        roi={"x": 46, "y": 10, "width": 112, "height": 122},
        fit_mode="cover",
    )

    for y, x in [(20, 60), (70, 58), (70, 142), (121, 100)]:
        b, g, r = composed[y, x]
        assert r > 120
        assert g < 90
        assert g < r * 0.75


def test_stabilize_chroma_quad_reduces_small_frame_to_frame_jitter() -> None:
    base = np.array([[60, 20], [140, 20], [140, 120], [60, 120]], dtype=np.float32)
    previous = base
    raw_centers: list[float] = []
    smooth_centers: list[float] = []

    for offset in [4, -4, 3, -3, 2, -2]:
        current = base + np.array([offset, 0], dtype=np.float32)
        raw_centers.append(float(current[:, 0].mean()))
        previous = pipeline._stabilize_chroma_quad(previous, current)
        smooth_centers.append(float(previous[:, 0].mean()))

    raw_jitter = max(abs(current - last) for last, current in zip(raw_centers, raw_centers[1:]))
    smooth_jitter = max(abs(current - last) for last, current in zip(smooth_centers, smooth_centers[1:]))
    assert smooth_jitter < raw_jitter * 0.45


def test_render_chroma_replacement_writes_video(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    replacement = tmp_path / "replacement.mp4"
    output = tmp_path / "output.mp4"
    _write_chroma_source_with_distractor(source, frames=6)
    _write_replacement_video(replacement, frames=3)

    result = pipeline.render_chroma_replacement(
        source_path=str(source),
        replacement_path=str(replacement),
        output_path=str(output),
        roi={"x": 54, "y": 22, "width": 128, "height": 126},
        audio_policy="silent",
        fit_mode="cover",
        feather=1,
        mask_grow=0,
    )

    assert output.exists()
    assert result.frame_count == 6
    assert result.duration > 0


def test_mix_audio_uses_both_volume_controls(tmp_path: Path, monkeypatch) -> None:
    video_only = tmp_path / "video-only.mp4"
    output = tmp_path / "mixed.mp4"
    video_only.write_bytes(b"video")
    commands: list[list[str]] = []

    class Completed:
        returncode = 0

    def fake_run(command, **_kwargs):
        commands.append(command)
        output.write_bytes(b"mixed")
        return Completed()

    monkeypatch.setattr(pipeline.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    assert pipeline._mux_mixed_audio(
        video_only,
        "source.mp4",
        "replacement.mp4",
        output,
        source_volume=0.76,
        replacement_volume=0.42,
    )

    command = commands[0]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "[1:a:0]volume=0.76[a0]" in filter_graph
    assert "[2:a:0]volume=0.42[a1]" in filter_graph
    assert "[a0][a1]amix=inputs=2" in filter_graph
    assert "apad[aout]" in filter_graph


def test_ffmpeg_binary_prefers_bundled_pyinstaller_binary(tmp_path: Path, monkeypatch) -> None:
    bundled = tmp_path / "ffmpeg"
    bundled.write_text("fake ffmpeg")

    monkeypatch.setattr(pipeline.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(pipeline.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    assert pipeline._ffmpeg_binary() == str(bundled)


def test_chroma_api_analyze_preview_and_render(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    replacement = tmp_path / "replacement.mp4"
    output = tmp_path / "api-output.mp4"
    _write_chroma_source_with_distractor(source, frames=6)
    _write_replacement_video(replacement, frames=3)
    client = TestClient(api_server.app)
    roi = {"x": 54, "y": 22, "width": 128, "height": 126}

    analyze_response = client.post("/chroma/analyze", json={"source_path": str(source), "roi": roi})

    assert analyze_response.status_code == 200
    analyze_data = analyze_response.json()
    assert analyze_data["roi"] == roi
    assert analyze_data["screen_quad"]
    assert analyze_data["green_coverage"] > 0.2

    preview_response = client.post(
        "/chroma/preview",
        json={
            "source_path": str(source),
            "replacement_path": str(replacement),
            "time": 0,
            "roi": roi,
            "fit_mode": "cover",
            "feather": 0,
            "mask_grow": 0,
        },
    )

    assert preview_response.status_code == 200
    preview_data = preview_response.json()
    assert preview_data["image"].startswith("data:image/jpeg;base64,")
    assert preview_data["metrics"]["green_coverage"] > 0.2

    render_response = client.post(
        "/chroma/render",
        json={
            "source_path": str(source),
            "replacement_path": str(replacement),
            "output_path": str(output),
            "roi": roi,
            "audio_policy": "silent",
            "source_audio_volume": 25,
            "replacement_audio_volume": 75,
            "fit_mode": "cover",
            "feather": 1,
            "mask_grow": 0,
        },
    )

    assert render_response.status_code == 200
    render_data = render_response.json()
    assert render_data["frame_count"] == 6
    assert render_data["source_audio_volume"] == 25
    assert render_data["replacement_audio_volume"] == 75
    assert output.exists()


def test_green_screen_composite_covers_threshold_edge_pixels() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[42, 18], [118, 18], [118, 104], [42, 104]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (0, 36, 0))
    inner_quad = np.array([[46, 22], [114, 22], [114, 100], [46, 100]], dtype=np.int32)
    cv2.fillConvexPoly(source, inner_quad, (0, 245, 0))
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[20, 44, 2] > 160
    assert composed[20, 44, 1] < 80


def test_composite_covers_skin_occlusion_when_occlusion_layer_is_disabled() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[42, 18], [118, 18], [118, 104], [42, 104]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (0, 245, 0))
    cv2.ellipse(source, (122, 62), (20, 34), 0, 0, 360, (120, 170, 220), -1)
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[62, 112, 0] < 60
    assert composed[62, 112, 2] > 160


def test_composite_replaces_full_quad_without_edge_occlusion_layer() -> None:
    source = np.zeros((140, 180, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[50, 16], [130, 16], [130, 124], [50, 124]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (0, 245, 0))
    cv2.circle(source, (50, 16), 10, (4, 4, 4), -1)
    cv2.ellipse(source, (134, 70), (18, 30), 0, 0, 360, (120, 170, 220), -1)
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[70, 90, 2] > 160
    assert composed[118, 90, 2] > 160
    assert composed[18, 52, 2] > 160
    assert composed[70, 124, 2] > 160


def test_composite_replaces_dark_screen_content_along_side_edges() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[42, 18], [118, 18], [118, 104], [42, 104]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (0, 245, 0))
    cv2.rectangle(source, (42, 28), (52, 94), (8, 8, 8), -1)
    cv2.rectangle(source, (108, 28), (118, 94), (8, 8, 8), -1)
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[60, 44, 2] > 160
    assert composed[60, 116, 2] > 160


def test_composite_replaces_skin_colored_screen_content_connected_to_edge() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[42, 18], [118, 18], [118, 104], [42, 104]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (120, 170, 220))
    cv2.rectangle(source, (118, 42), (150, 82), (120, 170, 220), -1)
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[62, 80, 2] > 160
    assert composed[62, 80, 0] < 60


def test_composite_replaces_dark_phone_corner_when_occlusion_layer_is_disabled() -> None:
    source = np.zeros((120, 160, 3), dtype=np.uint8)
    source[:, :] = (30, 30, 30)
    quad = np.array([[42, 18], [118, 18], [118, 104], [42, 104]], dtype=np.float32)
    cv2.fillConvexPoly(source, quad.astype(np.int32), (0, 245, 0))
    cv2.rectangle(source, (34, 10), (48, 26), (4, 4, 4), -1)
    cv2.circle(source, (42, 18), 10, (4, 4, 4), -1)
    replacement = np.zeros((80, 60, 3), dtype=np.uint8)
    replacement[:, :] = (20, 20, 230)

    composed = _composite_frame(source, replacement, quad, "cover")

    assert composed[20, 44, 0] < 60
    assert composed[20, 44, 2] > 160


def test_template_refinement_corrects_small_translation() -> None:
    previous = np.zeros((120, 160), dtype=np.uint8)
    current = np.zeros((120, 160), dtype=np.uint8)
    quad = np.array([[42, 36], [112, 36], [112, 88], [42, 88]], dtype=np.float32)
    shifted = quad + np.array([4, -3], dtype=np.float32)
    cv2.rectangle(previous, (42, 36), (112, 88), 180, 2)
    cv2.line(previous, (50, 48), (104, 78), 210, 2)
    cv2.rectangle(current, (46, 33), (116, 85), 180, 2)
    cv2.line(current, (54, 45), (108, 75), 210, 2)

    refined = _refine_quad_by_template(previous, current, quad, quad)

    assert abs(refined[0][0] - shifted[0][0]) <= 1
    assert abs(refined[0][1] - shifted[0][1]) <= 1


def test_fit_frame_stretch_fills_target_without_letterbox_bars() -> None:
    frame = np.zeros((40, 80, 3), dtype=np.uint8)
    frame[:, :20] = (0, 220, 0)
    frame[:, 20:60] = (220, 0, 0)
    frame[:, 60:] = (0, 0, 220)

    fitted = _fit_frame(frame, 40, 100, "stretch")

    assert fitted.shape == (100, 40, 3)
    assert fitted[0, 20].max() > 150
    assert fitted[-1, 20].max() > 150
    assert fitted[50, 0, 1] > 150
    assert fitted[50, -1, 2] > 150


def test_render_replacement_writes_silent_mp4_with_replaced_pixels(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    replacement = tmp_path / "replacement.mp4"
    output = tmp_path / "output.mp4"
    quads = _write_source_video(source)
    _write_replacement_video(replacement)
    tracking = track_region(str(source), quads[0])

    rendered = render_replacement(
        source_path=str(source),
        replacement_path=str(replacement),
        tracking=tracking,
        output_path=str(output),
        audio_policy=AudioPolicy.SILENT,
        fit_mode="cover",
    )

    assert Path(rendered.output_path).exists()
    capture = cv2.VideoCapture(rendered.output_path)
    ok, frame = capture.read()
    capture.release()
    assert ok
    assert frame[58, 72, 1] > 120
