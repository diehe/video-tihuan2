import { describe, expect, it } from "vitest";
import { appReducer, canAnalyze, canRender, initialState } from "./workflow";

describe("workflow reducer", () => {
  it("defaults to stretch fit mode to avoid letterbox bars in the target area", () => {
    expect(initialState.fitMode).toBe("stretch");
  });

  it("requires source, replacement, and backend before loading the target frame", () => {
    let state = initialState;

    state = appReducer(state, { type: "setBackendUrl", backendUrl: "" });
    state = appReducer(state, { type: "setSourcePath", path: "/tmp/source.mp4" });
    state = appReducer(state, { type: "setReplacementPath", path: "/tmp/replacement.mp4" });

    expect(canAnalyze(state)).toBe(false);
    state = appReducer(state, { type: "setBackendUrl", backendUrl: "http://127.0.0.1:8765" });
    expect(canAnalyze(state)).toBe(true);
  });

  it("does not require a natural language prompt for manual target selection", () => {
    let state = initialState;

    state = appReducer(state, { type: "setSourcePath", path: "/tmp/source.mp4" });
    state = appReducer(state, { type: "setReplacementPath", path: "/tmp/replacement.mp4" });

    expect(canAnalyze(state)).toBe(true);
  });

  it("can render only after a confirmed quad and tracking result exist", () => {
    let state = appReducer(initialState, { type: "setSourcePath", path: "/tmp/source.mp4" });
    state = appReducer(state, { type: "setReplacementPath", path: "/tmp/replacement.mp4" });
    state = appReducer(state, {
      type: "setBaseQuad",
      quad: [
        [10, 10],
        [100, 10],
        [100, 80],
        [10, 80],
      ],
    });

    expect(canRender(state)).toBe(false);
    state = appReducer(state, {
      type: "setTracking",
      tracking: { frame_count: 2, fps: 24, frames: [] },
    });
    expect(canRender(state)).toBe(true);
  });

  it("keeps the base tracking quad separate from preview-frame edits", () => {
    let state = appReducer(initialState, {
      type: "setAnalysis",
      analysis: {
        frame: { width: 160, height: 120, fps: 24, frame_count: 24, duration: 1, image: "", index: 0, time: 0 },
        candidates: [
          {
            id: "manual",
            label: "候选区域",
            confidence: 0.5,
            reason: "默认区域",
            quad: [
              [10, 10],
              [100, 10],
              [100, 80],
              [10, 80],
            ],
          },
        ],
      },
    });

    expect(state.baseQuad).toEqual(state.confirmedQuad);
    state = appReducer(state, {
      type: "confirmQuad",
      quad: [
        [20, 20],
        [110, 20],
        [110, 90],
        [20, 90],
      ],
    });

    expect(state.baseQuad).toEqual([
      [10, 10],
      [100, 10],
      [100, 80],
      [10, 80],
    ]);
    expect(state.confirmedQuad).toEqual([
      [20, 20],
      [110, 20],
      [110, 90],
      [20, 90],
    ]);
  });
});
