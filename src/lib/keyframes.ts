import type { TrackingKeyframe } from "./types";

export function mergeAiKeyframes(existing: TrackingKeyframe[], aiKeyframes: TrackingKeyframe[]): TrackingKeyframe[] {
  const byIndex = new Map<number, TrackingKeyframe>();
  for (const keyframe of existing) {
    byIndex.set(keyframe.index, keyframe);
  }

  for (const keyframe of aiKeyframes) {
    const current = byIndex.get(keyframe.index);
    if (current && current.source !== "ai") continue;
    byIndex.set(keyframe.index, { ...keyframe, source: "ai" });
  }

  return [...byIndex.values()].sort((left, right) => left.index - right.index);
}
