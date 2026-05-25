import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { trackRegion } from "./lib/api";

vi.mock("./lib/api", () => ({
  analyzeTarget: vi.fn(async () => ({
    frame: {
      width: 100,
      height: 80,
      fps: 24,
      frame_count: 24,
      duration: 1,
      image: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==",
      index: 0,
      time: 0,
    },
    candidates: [
      {
        id: "manual",
        label: "手动区域",
        quad: [
          [10, 10],
          [60, 10],
          [60, 60],
          [10, 60],
        ],
        confidence: 0.8,
        reason: "默认区域",
      },
    ],
  })),
  generateAiKeyframes: vi.fn(async () => []),
  healthCheck: vi.fn(async () => true),
  readFramePreview: vi.fn(async () => ({
    width: 100,
    height: 80,
    fps: 24,
    frame_count: 24,
    duration: 1,
    image: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==",
    index: 12,
    time: 0.5,
  })),
  renderReplacement: vi.fn(),
  selectLocalPath: vi.fn(),
  trackRegion: vi.fn(async (_backendUrl, _sourcePath, _baseQuad, keyframes = []) => ({
    frame_count: 24,
    fps: 24,
    frames: [
      {
        index: 0,
        time: 0,
        quad: keyframes[0]?.quad ?? [
          [10, 10],
          [60, 10],
          [60, 60],
          [10, 60],
        ],
        status: "estimated",
      },
    ],
  })),
}));

vi.mock("./lib/settings", () => ({
  loadAiSettings: vi.fn(() => ({
    apiBaseUrl: "https://api.openai.com/v1",
    apiKey: "",
    model: "gpt-4.1-mini",
  })),
  saveAiSettings: vi.fn(),
}));

describe("App keyframe retracking", () => {
  it("rebuilds tracking after saving and deleting manual keyframes", async () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("/Users/me/source.mp4"), {
      target: { value: "/tmp/source.mp4" },
    });
    fireEvent.change(screen.getByPlaceholderText("/Users/me/replacement.mp4"), {
      target: { value: "/tmp/replacement.mp4" },
    });

    fireEvent.click(screen.getByRole("button", { name: /载入首帧/ }));
    await screen.findByText("手动区域");

    fireEvent.click(screen.getByRole("button", { name: /开始追踪/ }));
    await waitFor(() => expect(trackRegion).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("四角坐标（左上、右上、右下、左下）"), {
      target: { value: "12,12 62,12 62,62 12,62" },
    });
    fireEvent.click(screen.getByRole("button", { name: /保存当前帧修正/ }));

    await waitFor(() => expect(trackRegion).toHaveBeenCalledTimes(2));
    expect(trackRegion).toHaveBeenLastCalledWith(
      "http://127.0.0.1:8765",
      "/tmp/source.mp4",
      [
        [12, 12],
        [62, 12],
        [62, 62],
        [12, 62],
      ],
      [
        expect.objectContaining({
          index: 0,
          source: "manual",
        }),
      ],
    );

    fireEvent.click(screen.getByRole("button", { name: "删除关键帧" }));

    await waitFor(() => expect(trackRegion).toHaveBeenCalledTimes(3));
    expect(trackRegion).toHaveBeenLastCalledWith(
      "http://127.0.0.1:8765",
      "/tmp/source.mp4",
      [
        [12, 12],
        [62, 12],
        [62, 62],
        [12, 62],
      ],
      [],
    );
  });
});
