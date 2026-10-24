// Scene pacing.
//
// The visuals must never out-run the voice: after a scene's steps finish we
// hold the frame for whatever is left of (narration + tail). Kept separate
// from the recorder so the arithmetic is directly testable.

/**
 * How long to sleep after a scene's steps have run.
 * @param {number} narrationSec  length of this scene's narration clip
 * @param {number} elapsedMs     wall-clock ms the steps actually took
 * @param {number} tailMs        breathing room after the voice stops
 * @returns {number} ms to sleep (never negative)
 */
export function padMs(narrationSec, elapsedMs, tailMs = 750) {
  return Math.max(0, narrationSec * 1000 + tailMs - elapsedMs)
}

/**
 * Predict the finished video's length from the narration clips alone, assuming
 * every scene's steps finish inside its narration. Used by `--dry-run` to tell
 * the user roughly how long the real render will be.
 */
export function estimateTotalSeconds(scenes, seconds, { tailMs = 750, outroMs = 0 } = {}) {
  const body = scenes.reduce((t, s) => t + (seconds[s.id] || 0) + tailMs / 1000, 0)
  return body + outroMs / 1000
}
