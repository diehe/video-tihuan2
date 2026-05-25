import { describe, expect, it, vi } from "vitest";
import { analyzeChroma, previewChroma, renderChromaReplacement, selectLocalPath } from "./api";

const roi = { x: 54, y: 22, width: 128, height: 126 };

describe("api client", () => {
  it("requests a local file path from the backend picker", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ path: "/Users/me/source.mp4" }),
    });

    const result = await selectLocalPath("http://127.0.0.1:8765", "video", fetchMock as unknown as typeof fetch);

    expect(result).toBe("/Users/me/source.mp4");
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8765/select-path?kind=video");
  });

  it("posts chroma analysis requests with an optional ROI", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ roi, screen_quad: [], green_coverage: 0.42 }),
    });

    const result = await analyzeChroma(
      {
        backendUrl: "http://127.0.0.1:8765",
        sourcePath: "/tmp/source.mp4",
        roi,
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(result.green_coverage).toBe(0.42);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/chroma/analyze",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      source_path: "/tmp/source.mp4",
      roi,
    });
  });

  it("posts chroma preview requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        width: 100,
        height: 60,
        fps: 24,
        image: "data:image/jpeg;base64,test",
        index: 0,
        time: 0,
        metrics: { roi, green_coverage: 0.5 },
      }),
    });

    const preview = await previewChroma(
      {
        backendUrl: "http://127.0.0.1:8765",
        sourcePath: "/tmp/source.mp4",
        replacementPath: "/tmp/replacement.mp4",
        time: 0.5,
        roi,
        fitMode: "cover",
        feather: 2,
        maskGrow: -1,
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(preview.image).toContain("data:image");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      source_path: "/tmp/source.mp4",
      replacement_path: "/tmp/replacement.mp4",
      time: 0.5,
      roi,
      fit_mode: "cover",
      feather: 2,
      mask_grow: -1,
    });
  });

  it("posts chroma render requests without tracking data", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ output_path: "/tmp/out.mp4", frame_count: 12, duration: 1, audio_policy: "original" }),
    });

    const result = await renderChromaReplacement(
      "http://127.0.0.1:8765",
      {
        sourcePath: "/tmp/source.mp4",
        replacementPath: "/tmp/replacement.mp4",
        outputPath: "/tmp/out.mp4",
        roi,
        audioPolicy: "original",
        fitMode: "cover",
        feather: 2,
        maskGrow: -1,
      },
      fetchMock as unknown as typeof fetch,
    );

    expect(result.frame_count).toBe(12);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8765/chroma/render", expect.any(Object));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("tracking");
  });
});
