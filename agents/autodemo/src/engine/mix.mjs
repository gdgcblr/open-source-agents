// Stage 3: mix the per-scene narration clips onto the single recorded video at
// their recorded timestamps, and encode a universally-playable MP4.
//
// The filter string is built by a pure function so it can be unit-tested
// without ffmpeg — it is the part of this pipeline that is subtly easy to get
// wrong (off-by-one on input indices, a missing `apad`, normalize=1 quietly
// ducking every clip once more than one overlaps).

import { execFileSync } from 'node:child_process'

/**
 * Build the ffmpeg -filter_complex string.
 * @param {number[]} marksMs  scene start offsets, in ms, in scene order
 * @returns {string}
 */
export function buildFilterComplex(marksMs) {
  if (!Array.isArray(marksMs) || marksMs.length === 0) {
    throw new Error('buildFilterComplex needs at least one mark')
  }
  // Input 0 is the video (Playwright records it with no audio track), so the
  // audio clip for scene i is ffmpeg input i+1.
  const delays = marksMs.map((ms, i) =>
    `[${i + 1}:a]adelay=${Math.max(0, Math.round(ms))}:all=1[d${i}]`)
  const chain = marksMs.map((_, i) => `[d${i}]`).join('')
  return `${delays.join(';')};${chain}amix=inputs=${marksMs.length}:normalize=0:dropout_transition=0,apad[mix]`
}

/**
 * Build the full ffmpeg argv.
 * @returns {string[]}
 */
export function buildFfmpegArgs({ videoFile, audioFiles, marksMs, videoDuration, outFile, crf = 20, preset = 'medium' }) {
  if (audioFiles.length !== marksMs.length) {
    throw new Error(`audioFiles (${audioFiles.length}) and marksMs (${marksMs.length}) must be the same length`)
  }
  const inputs = audioFiles.flatMap(f => ['-i', f])
  return [
    '-y', '-i', videoFile, ...inputs,
    '-filter_complex', buildFilterComplex(marksMs),
    '-map', '0:v:0', '-map', '[mix]',
    '-t', String(videoDuration),
    // yuv420p needs even dimensions; Playwright's recording can land on odd ones.
    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', String(crf), '-preset', preset,
    '-c:a', 'aac', '-b:a', '192k',
    '-movflags', '+faststart',
    outFile,
  ]
}

/** Run the mix. Returns the output path. */
export function mix(opts) {
  execFileSync('ffmpeg', buildFfmpegArgs(opts), { stdio: ['ignore', 'ignore', 'pipe'] })
  return opts.outFile
}
