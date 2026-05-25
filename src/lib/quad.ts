import type { Quad } from "./types";

export interface ViewTransform {
  scale: number;
  x: number;
  y: number;
}

export function parseQuadText(value: string): Quad | null {
  const numbers = value
    .split(/[\s,;]+/)
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
  if (numbers.length !== 8) return null;
  return [
    [numbers[0], numbers[1]],
    [numbers[2], numbers[3]],
    [numbers[4], numbers[5]],
    [numbers[6], numbers[7]],
  ];
}

export function clampQuad(quad: Quad, width: number, height: number): Quad {
  return quad.map(([x, y]) => [clamp(x, 0, width), clamp(y, 0, height)]) as Quad;
}

export function moveQuadPoint(quad: Quad, pointIndex: number, x: number, y: number, width: number, height: number): Quad {
  return quad.map((point, index) => {
    if (index !== pointIndex) return [...point];
    return [clamp(x, 0, width), clamp(y, 0, height)];
  }) as Quad;
}

export function moveQuad(quad: Quad, dx: number, dy: number, width: number, height: number): Quad {
  const minX = Math.min(...quad.map(([x]) => x));
  const maxX = Math.max(...quad.map(([x]) => x));
  const minY = Math.min(...quad.map(([, y]) => y));
  const maxY = Math.max(...quad.map(([, y]) => y));
  const clampedDx = clamp(dx, -minX, width - maxX);
  const clampedDy = clamp(dy, -minY, height - maxY);
  return quad.map(([x, y]) => [x + clampedDx, y + clampedDy]) as Quad;
}

export function formatQuadText(quad: Quad): string {
  return quad.map(([x, y]) => `${Math.round(x)},${Math.round(y)}`).join("  ");
}

export function formatSvgQuadPoints(quad: Quad, width: number, height: number): string {
  return quad.map(([x, y]) => `${(x / width) * 100},${(y / height) * 100}`).join(" ");
}

export function clientPointToFrame(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, "left" | "top" | "width" | "height">,
  width: number,
  height: number,
): { x: number; y: number } {
  return {
    x: ((clientX - bounds.left) / bounds.width) * width,
    y: ((clientY - bounds.top) / bounds.height) * height,
  };
}

export function zoomAtPoint(transform: ViewTransform, point: { x: number; y: number }, factor: number): ViewTransform {
  const nextScale = clamp(transform.scale * factor, 0.5, 8);
  const appliedFactor = nextScale / transform.scale;
  return {
    scale: roundForUi(nextScale),
    x: roundForUi(point.x - (point.x - transform.x) * appliedFactor),
    y: roundForUi(point.y - (point.y - transform.y) * appliedFactor),
  };
}

export function panView(transform: ViewTransform, dx: number, dy: number): ViewTransform {
  return {
    ...transform,
    x: roundForUi(transform.x + dx),
    y: roundForUi(transform.y + dy),
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function roundForUi(value: number): number {
  return Math.round(value * 10) / 10;
}
