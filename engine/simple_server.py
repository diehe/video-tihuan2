from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from .file_dialog import select_local_path
from .pipeline import EngineError, analyze_target, generate_ai_keyframes, read_frame_preview, render_replacement, track_region
from .schemas import AudioPolicy, TrackingResult


class RenderRequest(BaseModel):
    source_path: str
    replacement_path: str
    tracking: TrackingResult
    output_path: str | None = None
    audio_policy: AudioPolicy = AudioPolicy.ORIGINAL
    fit_mode: str = "stretch"


class Handler(BaseHTTPRequestHandler):
    server_version = "VideoTihuanEngine/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/select-path":
            kind = parse_qs(parsed.query).get("kind", ["video"])[0]
            self._guard(lambda: {"path": select_local_path("output" if kind == "output" else "video")})
            return
        self._send_json({"detail": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/analyze":
            self._guard(
                lambda: analyze_target(
                    payload["video_path"],
                    payload.get("prompt") or "手动框选替换区域",
                    api_key=payload.get("api_key"),
                    base_url=payload.get("base_url"),
                    model=payload.get("model"),
                )
            )
            return
        if parsed.path == "/track":
            self._guard(lambda: track_region(payload["video_path"], payload["initial_quad"], payload.get("keyframes")))
            return
        if parsed.path == "/frame":
            self._guard(lambda: read_frame_preview(payload["video_path"], float(payload.get("time", 0))))
            return
        if parsed.path == "/ai-keyframes":
            self._guard(
                lambda: generate_ai_keyframes(
                    video_path=payload["video_path"],
                    reference_quad=payload["reference_quad"],
                    interval_seconds=payload.get("interval_seconds"),
                    every_frame=bool(payload.get("every_frame", False)),
                    api_key=payload.get("api_key"),
                    base_url=payload.get("base_url"),
                    model=payload.get("model"),
                )
            )
            return
        if parsed.path == "/render":
            request = RenderRequest.model_validate(payload)
            output_path = request.output_path or str(Path(request.source_path).with_name("video-tihuan-output.mp4"))
            self._guard(
                lambda: render_replacement(
                    source_path=request.source_path,
                    replacement_path=request.replacement_path,
                    tracking=request.tracking,
                    output_path=output_path,
                    audio_policy=request.audio_policy,
                    fit_mode=request.fit_mode,
                )
            )
            return
        self._send_json({"detail": "Not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _guard(self, operation) -> None:
        try:
            result = operation()
            if hasattr(result, "model_dump"):
                result = result.model_dump(mode="json")
            self._send_json(result)
        except EngineError as exc:
            self._send_json({"detail": str(exc)}, status=400)
        except Exception as exc:
            self._send_json({"detail": f"处理失败: {exc}"}, status=500)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Video Tihuan Python engine")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
