import { describe, expect, it } from "vitest";
import { appReducer, canAnalyze, canPreview, canRender, initialState } from "./workflow";

describe("workflow reducer", () => {
  it("defaults to cover fit mode for phone-screen green-screen replacement", () => {
    expect(initialState.fitMode).toBe("cover");
  });

  it("requires source, replacement, and backend before chroma analysis", () => {
    let state = initialState;

    state = appReducer(state, { type: "setBackendUrl", backendUrl: "" });
    state = appReducer(state, { type: "setSourcePath", path: "/tmp/source.mp4" });
    state = appReducer(state, { type: "setReplacementPath", path: "/tmp/replacement.mp4" });

    expect(canAnalyze(state)).toBe(false);
    state = appReducer(state, { type: "setBackendUrl", backendUrl: "http://127.0.0.1:8765" });
    expect(canAnalyze(state)).toBe(true);
  });

  it("can preview and render after chroma analysis without tracking", () => {
    let state = appReducer(initialState, { type: "setSourcePath", path: "/tmp/source.mp4" });
    state = appReducer(state, { type: "setReplacementPath", path: "/tmp/replacement.mp4" });

    expect(canPreview(state)).toBe(false);
    expect(canRender(state)).toBe(false);

    state = appReducer(state, {
      type: "setChromaAnalysis",
      analysis: {
        frame: { width: 160, height: 120, fps: 24, frame_count: 24, duration: 1, image: "", index: 0, time: 0 },
        mask_image: "",
        roi: { x: 20, y: 10, width: 100, height: 90 },
        screen_quad: [
          [20, 10],
          [120, 10],
          [120, 100],
          [20, 100],
        ],
        green_coverage: 0.45,
      },
    });

    expect(canPreview(state)).toBe(true);
    expect(canRender(state)).toBe(true);
  });

  it("resets chroma output when input video changes", () => {
    let state = appReducer(initialState, {
      type: "setChromaAnalysis",
      analysis: {
        frame: { width: 160, height: 120, fps: 24, frame_count: 24, duration: 1, image: "", index: 0, time: 0 },
        mask_image: "",
        roi: { x: 20, y: 10, width: 100, height: 90 },
        screen_quad: null,
        green_coverage: 0.45,
      },
    });
    state = appReducer(state, {
      type: "setChromaPreview",
      preview: {
        width: 160,
        height: 120,
        fps: 24,
        frame_count: 24,
        duration: 1,
        image: "",
        index: 0,
        time: 0,
        metrics: { roi: { x: 20, y: 10, width: 100, height: 90 }, screen_quad: null, green_coverage: 0.45 },
      },
    });

    state = appReducer(state, { type: "setSourcePath", path: "/tmp/next.mp4" });

    expect(state.chromaAnalysis).toBeNull();
    expect(state.chromaPreview).toBeNull();
  });
});
