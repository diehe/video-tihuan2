import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Mock } from "vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { analyzeChroma, previewChroma, renderChromaReplacement } from "./lib/api";

const transparentImage = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
const roi = { x: 10, y: 8, width: 80, height: 64 };

function dispatchPointer(target: Element, type: string, init: { clientX?: number; clientY?: number; pointerId: number }) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperties(event, {
    clientX: { value: init.clientX ?? 0 },
    clientY: { value: init.clientY ?? 0 },
    pointerId: { value: init.pointerId },
  });
  target.dispatchEvent(event);
}

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
  beforeEach(() => {
    vi.clearAllMocks();
  });

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
    expect(screen.getAllByLabelText(/缩放限定区域/)).toHaveLength(4);
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

  it("resizes the ROI from a corner handle before previewing", async () => {
    Element.prototype.setPointerCapture = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
    render(<App />);

    fireEvent.change(screen.getByLabelText("主体视频"), {
      target: { value: "/tmp/source.mp4" },
    });
    fireEvent.change(screen.getByLabelText("替换视频"), {
      target: { value: "/tmp/replacement.mp4" },
    });
    fireEvent.click(screen.getByRole("button", { name: /识别绿幕/ }));
    await screen.findByText(/已识别绿幕/);

    const stage = document.querySelector(".roi-stage") as HTMLElement;
    const handle = screen.getByLabelText("缩放限定区域 nw");
    (stage.getBoundingClientRect as Mock | undefined) = vi.fn(() => ({
      x: 100,
      y: 100,
      width: 200,
      height: 160,
      top: 100,
      left: 100,
      right: 300,
      bottom: 260,
      toJSON: () => ({}),
    }));
    (handle.getBoundingClientRect as Mock | undefined) = vi.fn(() => ({
      x: 110,
      y: 106,
      width: 18,
      height: 18,
      top: 106,
      left: 110,
      right: 128,
      bottom: 124,
      toJSON: () => ({}),
    }));

    act(() => {
      dispatchPointer(handle, "pointerdown", { clientX: 119, clientY: 115, pointerId: 9 });
      dispatchPointer(stage, "pointermove", { clientX: 140, clientY: 132, pointerId: 9 });
      dispatchPointer(stage, "pointerup", { pointerId: 9 });
    });

    fireEvent.click(screen.getByRole("button", { name: /生成预览/ }));
    await waitFor(() => expect(previewChroma).toHaveBeenCalledTimes(1));
    expect(previewChroma).toHaveBeenCalledWith(
      expect.objectContaining({
        roi: expect.objectContaining({
          x: 21,
          y: 17,
          width: 70,
          height: 56,
        }),
      }),
    );
  });
});
