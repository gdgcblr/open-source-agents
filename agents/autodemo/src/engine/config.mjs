// Load, validate and normalise an autodemo config file (YAML or JSON).
//
// Validation is a hard gate: a typo in a step name should fail in under a
// second, not thirty seconds into a render. Defaults are applied *after*
// validation so the schema only ever sees what the user actually wrote.

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import YAML from 'yaml'
import Ajv from 'ajv'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SCHEMA = JSON.parse(readFileSync(path.join(HERE, '..', 'schema', 'scenes.schema.json'), 'utf8'))

export const DEFAULTS = {
  app: { viewport: { width: 1600, height: 900 }, chromePath: 'auto', headless: true },
  voice: { engine: 'edge-tts', voice: 'en-US-AriaNeural', rate: '+0%', tailMs: 750 },
  theme: { accent: '#7dd3fc', font: 'Inter, Segoe UI, system-ui, sans-serif', position: 'bottom', eyebrow: '' },
  output: { dir: './autodemo-out', file: 'demo.mp4', crf: 20, preset: 'medium', thumbnail: false },
  outro: { holdMs: 0 },
}

/** Validate a plain config object against the JSON Schema. Returns {valid, errors[]}. */
export function validateConfig(obj) {
  const ajv = new Ajv({ allErrors: true, strict: false })
  const validate = ajv.compile(SCHEMA)
  const valid = validate(obj)
  const errors = (validate.errors || []).map(e => `${e.instancePath || '/'} ${e.message}`)
  if (valid) {
    // Scene ids must be unique: they key the audio files and the ffmpeg inputs.
    const seen = new Set()
    for (const s of obj.scenes || []) {
      if (seen.has(s.id)) errors.push(`/scenes duplicate scene id "${s.id}"`)
      seen.add(s.id)
    }
  }
  return { valid: valid && errors.length === 0, errors }
}

/** Deep-merge defaults under a user object (user wins; arrays are replaced). */
function withDefaults(user, defaults) {
  const out = { ...defaults }
  for (const [k, v] of Object.entries(user || {})) {
    out[k] = v && typeof v === 'object' && !Array.isArray(v) && defaults?.[k] && typeof defaults[k] === 'object'
      ? withDefaults(v, defaults[k])
      : v
  }
  return out
}

/** Apply defaults to a validated config object. */
export function normaliseConfig(obj, { configDir = process.cwd() } = {}) {
  const cfg = {
    app: withDefaults(obj.app, DEFAULTS.app),
    voice: withDefaults(obj.voice, DEFAULTS.voice),
    theme: withDefaults(obj.theme, DEFAULTS.theme),
    output: withDefaults(obj.output, DEFAULTS.output),
    outro: withDefaults(obj.outro, DEFAULTS.outro),
    scenes: (obj.scenes || []).map(s => ({
      layout: s.narration || s.title ? 'caption' : 'none',
      title: '', subtitle: '', narration: '', steps: [],
      ...s,
    })),
  }
  // A relative output dir is relative to the config file, not the shell's cwd —
  // otherwise `autodemo render -c examples/x/c.yaml` scatters output wherever
  // you happened to be standing.
  cfg.output.dir = path.resolve(configDir, cfg.output.dir)
  cfg.configDir = configDir
  return cfg
}

/** Read a .yaml/.yml/.json config from disk, validate it, and apply defaults. */
export function loadConfig(file) {
  const abs = path.resolve(file)
  let raw
  try {
    raw = readFileSync(abs, 'utf8')
  } catch {
    throw new Error(`Config not found: ${abs}\nRun \`autodemo init\` to scaffold one.`)
  }
  let parsed
  try {
    parsed = abs.endsWith('.json') ? JSON.parse(raw) : YAML.parse(raw)
  } catch (e) {
    throw new Error(`Could not parse ${abs}:\n  ${e.message}`)
  }
  const { valid, errors } = validateConfig(parsed)
  if (!valid) {
    throw new Error(`Invalid config ${abs}:\n` + errors.map(e => `  ✗ ${e}`).join('\n'))
  }
  return normaliseConfig(parsed, { configDir: path.dirname(abs) })
}
