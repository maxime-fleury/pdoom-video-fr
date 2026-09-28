// Output resolution multiplier, read once from the page URL (`?scale=2` renders 3840x2160).
// Scenes keep laying out in logical 1920x1080 px; the engine renders at SCALE x that.
// Kept in its own module so glsl/common.ts can use it without an import cycle through gl.ts.
//
// SCALE does not have to be an integer: `?scale=1.3333` renders 2560x1440 natively from the
// same 1920x1080 layout, which is what a 2K master wants (the physical canvas is rounded to
// whole pixels, so the aspect ratio stays 16:9 to within a pixel).
function readScale() {
  if (typeof location === 'undefined') return 1;
  const s = Number(new URLSearchParams(location.search).get('scale') ?? '1');
  return Number.isFinite(s) && s >= 1 ? Math.min(s, 4) : 1;
}

/** Physical pixels per logical pixel of the output (1..4, default 1). */
export const SCALE = readScale();
