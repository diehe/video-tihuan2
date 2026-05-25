import { describe, expect, it } from "vitest";
import {
  clampQuad,
  clientPointToFrame,
  formatSvgQuadPoints,
  moveQuad,
  moveQuadPoint,
  panView,
  parseQuadText,
  zoomAtPoint,
} from "./quad";
import type { Quad } from "./types";

const quad: Quad = [
  [10, 20],
  [110, 20],
  [110, 80],
  [10, 80],
];

describe("quad editing helpers", () => {
  it("parses four point coordinates from text", () => {
    expect(parseQuadText("10,20 110,20 110,80 10,80")).toEqual(quad);
  });

  it("moves a single corner while clamping to frame bounds", () => {
    expect(moveQuadPoint(quad, 0, -40, 200, 160, 120)).toEqual([
      [0, 120],
      [110, 20],
      [110, 80],
      [10, 80],
    ]);
  });

  it("moves the whole quad without letting any point leave the frame", () => {
    expect(moveQuad(quad, -30, -50, 160, 120)).toEqual([
      [0, 0],
      [100, 0],
      [100, 60],
      [0, 60],
    ]);
  });

  it("clamps every point to frame bounds", () => {
    expect(
      clampQuad(
        [
          [-1, -2],
          [200, 10],
          [100, 140],
          [8, 9],
        ],
        160,
        120,
      ),
    ).toEqual([
      [0, 0],
      [160, 10],
      [100, 120],
      [8, 9],
    ]);
  });

  it("formats svg points from the saved quad without shrinking the edit boundary", () => {
    expect(
      formatSvgQuadPoints(
        [
          [10, 20],
          [50, 20],
          [50, 80],
          [10, 80],
        ],
        100,
        100,
      ),
    ).toBe("10,20 50,20 50,80 10,80");
  });

  it("maps pointer coordinates through the full overlay bounds", () => {
    expect(clientPointToFrame(60, 50, { left: 10, top: 20, width: 200, height: 100 }, 1000, 500)).toEqual({
      x: 250,
      y: 150,
    });
  });

  it("zooms around the mouse position while preserving the content under cursor", () => {
    expect(zoomAtPoint({ scale: 1, x: 0, y: 0 }, { x: 100, y: 80 }, 2)).toEqual({
      scale: 2,
      x: -100,
      y: -80,
    });
  });

  it("clamps preview zoom to the supported range", () => {
    expect(zoomAtPoint({ scale: 1, x: 0, y: 0 }, { x: 100, y: 80 }, 20).scale).toBe(8);
    expect(zoomAtPoint({ scale: 1, x: 0, y: 0 }, { x: 100, y: 80 }, 0.01).scale).toBe(0.5);
  });

  it("pans the preview view by a drag delta", () => {
    expect(panView({ scale: 2, x: -100, y: -80 }, 15, -25)).toEqual({
      scale: 2,
      x: -85,
      y: -105,
    });
  });
});
