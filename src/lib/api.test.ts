import { describe, expect, it, vi } from "vitest";
import { analyzeTarget, generateAiKeyframes, readFramePreview, selectLocalPath, trackRegion } from "./api";

describe("api client", () => {
  it("posts target-frame analysis requests without user prompt fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ candidates: [], frame: { width: 100, height: 50, image: "" } }),
    });

    const result = await analyzeTarget(
      {
        backendUrl: "http://127.0.0.1:8765",
        videoPath: "/tmp/source.mp4",
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(result.frame.width).toBe(100);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/analyze",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      video_path: "/tmp/source.mp4",
      prompt: "手动框选替换区域",
    });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("api_key");
  });

  it("requests a local file path from the backend picker", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ path: "/Users/me/source.mp4" }),
    });

    const result = await selectLocalPath("http://127.0.0.1:8765", "video", fetchMock as unknown as typeof fetch);

    expect(result).toBe("/Users/me/source.mp4");
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8765/select-path?kind=video");
  });

  it("posts tracking keyframes with track requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ frame_count: 1, fps: 24, frames: [] }),
    });

    await trackRegion(
      "http://127.0.0.1:8765",
      "/tmp/source.mp4",
      [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
      ],
      [
        {
          index: 12,
          time: 0.5,
          quad: [
            [1, 1],
            [11, 1],
            [11, 11],
            [1, 11],
          ],
        },
      ],
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      keyframes: [
        {
          index: 12,
          quad: [
            [1, 1],
            [11, 1],
            [11, 11],
            [1, 11],
          ],
        },
      ],
    });
  });

  it("requests a preview frame at a specific time", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ width: 100, height: 60, fps: 24, image: "data:image/jpeg;base64,test", index: 48, time: 2 }),
    });

    const frame = await readFramePreview("http://127.0.0.1:8765", "/tmp/source.mp4", 2, fetchMock as unknown as typeof fetch);

    expect(frame.index).toBe(48);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      video_path: "/tmp/source.mp4",
      time: 2,
    });
  });

  it("posts AI keyframe requests for every frame", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ keyframes: [] }),
    });

    await generateAiKeyframes(
      {
        backendUrl: "http://127.0.0.1:8765",
        videoPath: "/tmp/source.mp4",
        referenceQuad: [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
        ],
        mode: "every",
        apiKey: "sk-test",
        baseUrl: "https://api.example.com/v1",
        model: "vision-model",
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      video_path: "/tmp/source.mp4",
      every_frame: true,
      api_key: "sk-test",
      base_url: "https://api.example.com/v1",
      model: "vision-model",
    });
  });

  it("posts AI keyframe requests for interval modes", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ keyframes: [] }),
    });

    await generateAiKeyframes(
      {
        backendUrl: "http://127.0.0.1:8765",
        videoPath: "/tmp/source.mp4",
        referenceQuad: [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
        ],
        mode: "0.3",
        apiKey: "sk-test",
        baseUrl: "https://api.example.com/v1",
        model: "vision-model",
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      every_frame: false,
      interval_seconds: 0.3,
    });
  });

  it("posts longer AI keyframe interval modes", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ keyframes: [] }),
    });

    await generateAiKeyframes(
      {
        backendUrl: "http://127.0.0.1:8765",
        videoPath: "/tmp/source.mp4",
        referenceQuad: [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
        ],
        mode: "3",
        apiKey: "sk-test",
        baseUrl: "https://api.example.com/v1",
        model: "vision-model",
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      every_frame: false,
      interval_seconds: 3,
    });
  });

  it("omits empty API keys for local AI keyframe requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ keyframes: [] }),
    });

    await generateAiKeyframes(
      {
        backendUrl: "http://127.0.0.1:8765",
        videoPath: "/tmp/source.mp4",
        referenceQuad: [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
        ],
        mode: "0.5",
        apiKey: "",
        baseUrl: "http://127.0.0.1:1234/v1",
        model: "local-vision",
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("api_key");
  });
});
