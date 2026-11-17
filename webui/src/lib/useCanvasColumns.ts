// Number of columns the PDS grid canvas can hold at its current width. PDS lays the grid out from
// --canvas-columns (its own default is 2); measuring the canvas here makes the column count follow the screen
// width instead of a fixed guess. minCardRem is the narrowest column that still fits a card, maxColumns the cap.
import { useEffect, useState, type RefObject } from "react";

export function useCanvasColumns(canvas: RefObject<HTMLDivElement>, minCardRem: number, maxColumns: number): number {
  const [columns, setColumns] = useState(1);
  useEffect(() => {
    const host = canvas.current;
    if (!host) return;
    const measure = () => {
      const grid = host.querySelector('[data-slot="template-canvas-content"]') ?? host; // the grid element itself
      const cs = getComputedStyle(grid);
      const px = (name: string) => parseFloat(cs.getPropertyValue(name)) || 0;
      const gap = px("--canvas-gap");
      const pad = px("--canvas-padding");
      const rootSize = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const fit = Math.floor((grid.clientWidth - 2 * pad + gap) / (minCardRem * rootSize + gap));
      setColumns(Math.max(1, Math.min(maxColumns, fit || 1)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, [canvas, minCardRem, maxColumns]);
  return columns;
}
