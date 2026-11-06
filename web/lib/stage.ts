// Mutable scroll state shared by the DOM side (ScrollTrigger writes it) and the WebGL stream
// (its frame loop reads it), so scrolling never re-renders React.
export const stage = {
  cover: 0, // 0 at the top of the page, 1 once the cover has scrolled away
  p: 0, // progress through the pinned stream, 0 to 1
};

// Fired when the scene cannot run (no WebGL, lost context, too slow); the page shows the still photos.
export const NO_SCENE = "siftbase:no-scene";
