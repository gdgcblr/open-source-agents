// Narration synthesis, cross-platform.
//
//   edge-tts  -> neural voices, any OS, needs `pip install edge-tts`
//   sapi      -> Windows System.Speech, always present on Windows
//   none      -> a silent clip of an estimated reading length, so a render
//                still has correct pacing with no TTS installed at all
//                (this is what CI uses).
//
// Every engine returns a real audio file on disk, because stage 3 probes each
// clip's duration with ffprobe and uses it to pace the walkthrough.

import { execFileSync } from 'node:child_process'
import { existsSync, statSync, writeFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'

const IS_WIN = process.platform === 'win32'

/** Duration of a media file in seconds, via ffprobe. */
export function ffprobeDur(file) {
  const out = execFileSync('ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nk=1:nw=1', file],
    { encoding: 'utf8' })
  const n = parseFloat(out.trim())
  if (!Number.isFinite(n)) throw new Error(`ffprobe could not read a duration from ${file}`)
  return n
}

/**
 * Estimated spoken length of a line, in seconds.
 * ~165 words per minute is a comfortable narration pace; the floor keeps a
 * two-word caption on screen long enough to read.
 */
export function estimateSpokenSeconds(text, wpm = 165) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean).length
  if (!words) return 0
  return Math.max(1.5, (words / wpm) * 60)
}

/** True if `python -m edge_tts` is importable. */
export function hasEdgeTts() {
  for (const py of ['python', 'python3']) {
    try {
      execFileSync(py, ['-m', 'edge_tts', '--list-voices'], { stdio: 'pipe', timeout: 30000 })
      return py
    } catch { /* try the next interpreter */ }
  }
  return false
}

function synthEdge(text, outFile, { voice, rate }) {
  const py = hasEdgeTts.cached ?? (hasEdgeTts.cached = hasEdgeTts())
  if (!py) throw new Error('edge-tts not available')
  execFileSync(py, ['-m', 'edge_tts', '--voice', voice, '--rate', rate,
    '--text', text, '--write-media', outFile], { stdio: 'pipe' })
  if (!existsSync(outFile) || statSync(outFile).size < 1500) throw new Error('edge-tts produced an empty clip')
  return outFile
}

function synthSapi(text, outFile, { voice }) {
  if (!IS_WIN) throw new Error('SAPI is Windows-only')
  // The text goes via a file, not the command line: narration contains quotes,
  // em-dashes and newlines that do not survive PowerShell argument quoting.
  const txt = outFile.replace(/\.wav$/, '.txt')
  writeFileSync(txt, text, 'utf8')
  const p = s => s.replace(/\\/g, '/').replace(/'/g, "''")
  execFileSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
    `Add-Type -AssemblyName System.Speech;` +
    `$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;` +
    (voice ? `try{$s.SelectVoice('${p(voice)}')}catch{};` : '') +
    `$s.Rate=-1;$s.SetOutputToWaveFile('${p(outFile)}');` +
    `$s.Speak([IO.File]::ReadAllText('${p(txt)}'));$s.Dispose()`,
  ], { stdio: 'pipe' })
  return outFile
}

/** A silent clip of `seconds`, so pacing still works with voice.engine: none. */
function synthSilence(seconds, outFile) {
  execFileSync('ffmpeg', ['-y', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono',
    '-t', seconds.toFixed(3), '-c:a', 'aac', '-b:a', '64k', outFile], { stdio: 'pipe' })
  return outFile
}

/**
 * Synthesize every scene's narration up front.
 * Returns { files: {id: path}, seconds: {id: number}, engineUsed }.
 */
export function synthesizeAll(scenes, { engine, voice, rate }, audioDir, log = console.log) {
  mkdirSync(audioDir, { recursive: true })
  const files = {}, seconds = {}
  let engineUsed = engine

  for (const scene of scenes) {
    const text = (scene.narration || '').trim()
    // A scene with no narration still gets a clip, so its index lines up with
    // the ffmpeg input list and its on-screen hold has a defined length.
    if (!text) {
      files[scene.id] = synthSilence(1.2, path.join(audioDir, `${scene.id}.m4a`))
      seconds[scene.id] = ffprobeDur(files[scene.id])
      continue
    }
    if (engine === 'none') {
      files[scene.id] = synthSilence(estimateSpokenSeconds(text), path.join(audioDir, `${scene.id}.m4a`))
      log(`  silent: ${scene.id} (${seconds[scene.id] = ffprobeDur(files[scene.id])}s estimated)`)
      continue
    }
    let made = null
    if (engine === 'edge-tts') {
      try { made = synthEdge(text, path.join(audioDir, `${scene.id}.mp3`), { voice, rate }) ; log(`  edge-tts: ${scene.id}`) }
      catch { log(`  edge-tts unavailable for ${scene.id} — falling back`) }
    }
    if (!made && (engine === 'sapi' || IS_WIN)) {
      try { made = synthSapi(text, path.join(audioDir, `${scene.id}.wav`), { voice: 'Microsoft Zira Desktop' }); log(`  sapi: ${scene.id}`); engineUsed = 'sapi' }
      catch { /* fall through to silence */ }
    }
    if (!made) {
      made = synthSilence(estimateSpokenSeconds(text), path.join(audioDir, `${scene.id}.m4a`))
      log(`  silent fallback: ${scene.id}`)
      engineUsed = 'none'
    }
    files[scene.id] = made
    seconds[scene.id] = ffprobeDur(made)
  }
  return { files, seconds, engineUsed }
}
