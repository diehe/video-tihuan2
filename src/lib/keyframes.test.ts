import { describe, expect, it } from "vitest";
import { mergeAiKeyframes } from "./keyframes";
import type { TrackingKeyframe } from "./types";

describe("keyframe merging", () => {
  it("does not let AI overwrite manual keyframes", () => {
    const manual: TrackingKeyframe = {
      index: 12,
      time: 1,
      source: "manual",
      quad: [
        [1, 1],
        [11, 1],
        [11, 11],
        [1, 11],
      ],
    };
    const ai: TrackingKeyframe = {
      index: 12,
      time: 1,
      source: "ai",
      confidence: 0.9,
      quad: [
        [2, 2],
        [12, 2],
        [12, 12],
        [2, 12],
      ],
    };

    expect(mergeAiKeyframes([manual], [ai])).toEqual([manual]);
  });

  it("replaces older AI keyframes with newer AI keyframes", () => {
    const olderAi: TrackingKeyframe = {
      index: 6,
      time: 0.5,
      source: "ai",
      confidence: 0.5,
      quad: [
        [1, 1],
        [11, 1],
        [11, 11],
        [1, 11],
      ],
    };
    const newerAi: TrackingKeyframe = {
      index: 6,
      time: 0.5,
      source: "ai",
      confidence: 0.8,
      quad: [
        [2, 2],
        [12, 2],
        [12, 12],
        [2, 12],
      ],
    };

    expect(mergeAiKeyframes([olderAi], [newerAi])).toEqual([newerAi]);
  });
});
