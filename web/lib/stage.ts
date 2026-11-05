// Mutable scroll state shared by the DOM side (ScrollTrigger writes it) and the WebGL scene
// (useFrame reads it), so scrolling never re-renders React.
export const stage = {
  cover: 0, // 0 at the top of the page, 1 once the cover has scrolled away
  p: 0, // progress through the pinned pan, 0 to 1
  dim: 0, // 1 once the reader is past the pan: the scene drops to 20% behind later sections
  pool: [0, 0, 0, 0] as [number, number, number, number], // caption rectangle in CSS px: x, y, w, h
};

// Fired when the scene cannot run (no WebGL, lost context, too slow); the page shows the flat steps.
export const NO_SCENE = "siftbase:no-scene";
