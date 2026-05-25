import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { analyzeChroma, previewChroma, renderChromaReplacement } from "./lib/api";

const transparentImage = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
const roi = { x: 10, y: 8, width: 80, height: 64 };

vi.mock("./lib/api", () => ({
  analyzeChroma: vi.fn(async () => ({
    frame: {
      width: 100,
      height: 80,
      fps: 24,
      frame_count: 24,
      duration: 1,
      image: transparentImage,
      index: 0,
      time: 0,
    },
    mask_image: transparentImage,
    roi,
    screen_quad: [
      [10, 8],
      [90, 8],
      [90, 72],
      [10, 72],
    ],
    green_coverage: 0.5,
  })),
  healthCheck: vi.fn(async () => true),
  previewChroma: vi.fn(async () => ({
    width: 100,
    height: 80,
    fps: 24,
    frame_count: 24,
    duration: 1,
    image: transparentImage,
    index: 0,
    time: 0,
    metrics: { roi, screen_quad: null, green_coverage: 0.5 },
  })),
  renderChromaReplacement: vi.fn(async () => ({
    output_path: "/tmp/out.mp4",
    frame_count: 24,
    duration: 1,
    audio_policy: "original",
  })),
  selectLocalPath: vi.fn(),
}));

describe("App chroma-key wizard", () => {
  it("analyzes, previews, and renders a green-screen replacement", async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("主体视频"), {
      target: { value: "/tmp/source.mp4" },
    });
    fireEvent.change(screen.getByLabelText("替换视频"), {
      target: { value: "/tmp/replacement.mp4" },
    });

    fireEvent.click(screen.getByRole("button", { name: /识别绿幕/ }));
    await screen.findByText(/已识别绿幕/);
    expect(analyzeChroma).toHaveBeenCalledWith(
      expect.objectContaining({
        sourcePath: "/tmp/source.mp4",
        roi: null,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /生成预览/ }));
    await waitFor(() => expect(previewChroma).toHaveBeenCalledWith(expect.objectContaining({ roi })));
    await screen.findByText(/预览已生成/);

    fireEvent.click(screen.getByRole("button", { name: /导出 MP4/ }));
    await waitFor(() => expect(renderChromaReplacement).toHaveBeenCalledTimes(1));
    expect(await screen.findAllByText(/导出完成/)).toHaveLength(2);
  });
});
