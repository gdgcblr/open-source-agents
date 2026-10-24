# Shared by the demo scripts (sourced). Starts apfel and Ollama if they are not already up.
# apfel:  `apfel --serve` on :11435 (the Apple Foundation Model), unless one is answering.
# Ollama: `ollama serve` on :11436 (11434 is often taken by apfel's launch agent).
APFEL_PORT="${APFEL_PORT:-11435}"
OLLAMA_PORT="${OLLAMA_PORT:-11436}"
APFEL_PID=""
OLLAMA_PID=""

models_cleanup() {
  [ -n "$APFEL_PID" ] && kill "$APFEL_PID" 2>/dev/null
  [ -n "$OLLAMA_PID" ] && kill "$OLLAMA_PID" 2>/dev/null
  return 0
}

start_apfel() {
  command -v apfel >/dev/null 2>&1 || { echo "apfel not installed (brew install apfel)"; return 1; }
  if [ -n "${APFEL_BASE_URL:-}" ]; then
    root="${APFEL_BASE_URL%/v1}"
  else
    apfel --serve --port "$APFEL_PORT" --permissive >"${LOG_PREFIX:-/tmp/rce-sentinel}.apfel.log" 2>&1 &
    APFEL_PID=$!
    export APFEL_BASE_URL="http://127.0.0.1:$APFEL_PORT/v1"
    root="http://127.0.0.1:$APFEL_PORT"
  fi
  for _ in $(seq 1 40); do
    health="$(curl -s -m 1 "$root/health" || true)"
    case "$health" in
      *'"model_available":true'*) echo "apfel up: apple-foundationmodel at $root"; return 0 ;;
      *'"model_available":false'*)
        echo "apfel is running but Apple Intelligence is off (System Settings > Apple Intelligence & Siri)"
        return 1 ;;
    esac
    sleep 0.25
  done
  echo "apfel did not answer at $root"; return 1
}

start_ollama() {
  command -v ollama >/dev/null 2>&1 || { echo "ollama not installed"; return 1; }
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:$OLLAMA_PORT/v1}"
  base="${OLLAMA_BASE_URL%/v1}"
  if ! curl -s -m 1 "$base/api/version" >/dev/null; then
    OLLAMA_HOST="${base#http://}" ollama serve >"${LOG_PREFIX:-/tmp/rce-sentinel}.ollama.log" 2>&1 &
    OLLAMA_PID=$!
    for _ in $(seq 1 40); do
      curl -s -m 1 "$base/api/version" >/dev/null && break
      sleep 0.25
    done
  fi
  models="$(curl -s -m 2 "$base/v1/models")"
  case "$models" in *'"qwen2.5:3b"'*) echo "ollama up at $base with qwen2.5:3b" ;;
    *) echo "ollama is up but qwen2.5:3b is not pulled (ollama pull qwen2.5:3b)"; return 1 ;; esac
  case "$models" in *'"gemma4:31b-cloud"'*) echo "gemma4:31b-cloud available (needs ollama signin)" ;;
    *) echo "gemma4:31b-cloud not pulled (ollama pull gemma4:31b-cloud)" ;; esac
}
