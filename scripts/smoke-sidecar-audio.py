from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the packaged sidecar audio mux path.")
    parser.add_argument("--sidecar", default=None, help="Path to the packaged sidecar executable.")
    parser.add_argument("--port", default=8876, type=int)
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("ffmpeg and ffprobe are required for the sidecar audio smoke test.")

    sidecar = Path(args.sidecar) if args.sidecar else _default_sidecar_path()
    if not sidecar.exists():
        raise SystemExit(f"sidecar executable not found: {sidecar}")

    with tempfile.TemporaryDirectory(prefix="video-tihuan-sidecar-smoke-") as temp_dir:
        temp = Path(temp_dir)
        source = temp / "source.mp4"
        replacement = temp / "replacement.mp4"
        output = temp / "output.mp4"
        _create_source_video(ffmpeg, source)
        _create_replacement_video(ffmpeg, replacement)

        process = subprocess.Popen(
            [str(sidecar), "--host", "127.0.0.1", "--port", str(args.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_health(args.port)
            _post_json(
                args.port,
                "/chroma/render",
                {
                    "source_path": str(source),
                    "replacement_path": str(replacement),
                    "output_path": str(output),
                    "roi": {"x": 90, "y": 40, "width": 130, "height": 180},
                    "audio_policy": "mixed",
                    "source_audio_volume": 100,
                    "replacement_audio_volume": 100,
                    "fit_mode": "cover",
                    "feather": 3,
                    "mask_grow": 3,
                },
            )
            _assert_audio_stream(ffprobe, output)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            stdout, stderr = process.communicate()
            if process.returncode not in (0, -15, 1):
                print(stdout, file=sys.stdout)
                print(stderr, file=sys.stderr)

    print("Packaged sidecar audio smoke test passed.")
    return 0


def _default_sidecar_path() -> Path:
    if sys.platform == "win32":
        return Path("sidecars/video-tihuan-engine-x86_64-pc-windows-msvc.exe")
    if sys.platform == "darwin" and _machine() == "arm64":
        return Path("sidecars/video-tihuan-engine-aarch64-apple-darwin")
    if sys.platform == "darwin":
        return Path("sidecars/video-tihuan-engine-x86_64-apple-darwin")
    return Path("sidecars/video-tihuan-engine-x86_64-unknown-linux-gnu")


def _machine() -> str:
    import platform

    return platform.machine()


def _create_source_video(ffmpeg: str, path: Path) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=12:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-vf",
            "drawbox=x=110:y=60:w=90:h=140:color=0x00ff00:t=fill",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _create_replacement_video(ffmpeg: str, path: Path) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x240:r=12:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _wait_for_health(port: int) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)
    raise RuntimeError("sidecar health check timed out")


def _post_json(port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _assert_audio_stream(ffprobe: str, output: Path) -> None:
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"rendered output has no audio stream: {output}")


if __name__ == "__main__":
    raise SystemExit(main())
