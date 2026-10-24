# Video Analysis Agent

> A command-line agent that turns a video (MP4, MOV, ...) into an evidence-backed report: summary, decisions, action items, facts and open questions, each with timestamps.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Meeting, lecture and interview recordings are long, and generic LLM summaries often invent decisions, owners or deadlines nobody actually stated.
- **Intended Users**: Anyone who needs trustworthy notes from a recording: teams, students, researchers, developers.

### Key Features
- **Terminal only**: one command, no GUI. Bring your own LLM API key (Gemini, OpenAI-compatible, or Anthropic).
- **Local transcription**: FFmpeg extracts the audio and open-source Whisper (`faster-whisper`) transcribes it on your machine with timestamps. No audio is uploaded.
- **No invented facts**: every item must carry a verbatim transcript quote. A validator checks each quote against the transcript, drops anything unsupported, and removes owners/deadlines that are not stated near the quote.
- **Confirmed vs. suggested**: *decisions* (clearly agreed), *proposals* (floated, not agreed), *open questions*, and *AI insights* (inferred, labelled as not from the video) are kept in separate sections.
- **Robust**: handles long recordings (chunked analysis), low-confidence transcription (flagged), unsupported or corrupt files, and API failures (retries with backoff; the transcript is saved so you can retry only the analysis).
- **Optional audio cleanup**: `--denoise` (FFmpeg) and `--separate-vocals` (Demucs). Both are off by default.
- **Exports** Markdown and JSON (validated with Pydantic).

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core libraries**: `faster-whisper` (Whisper), `pydantic` v2, `requests`, `python-dotenv`
- **System dependency**: FFmpeg (including `ffprobe`)
- **LLM providers**: Gemini (default `gemini-2.5-flash`), OpenAI or any OpenAI-compatible server (e.g. Ollama), Anthropic
- **Agent framework**: none; a plain, modular pipeline

---

## Architecture & Data Flow

```
video -> video.py (validate, FFmpeg audio, optional denoise / Demucs)
      -> transcribe.py (faster-whisper -> timestamped segments, low-confidence flags)
      -> analysis.py (chunk -> LLM via llm.py -> merge)
      -> validate.py (Pydantic parsing + quote/owner/deadline verification)
      -> report.py -> report.md, report.json, transcript.txt, transcript.json
```

| Module | Responsibility |
| :--- | :--- |
| `video.py` | Format check, FFmpeg/ffprobe, audio extraction, optional cleanup |
| `transcribe.py` | Local Whisper transcription |
| `llm.py` | Provider clients, retries, API key handling |
| `analysis.py` | Prompts, chunking long transcripts, merging |
| `validate.py` | Evidence verification |
| `schemas.py` | Pydantic models |
| `report.py` | Markdown/JSON output |
| `pipeline.py`, `cli.py` | Orchestration and CLI |

---

## Prerequisites

- Python 3.10+
- FFmpeg on your `PATH`:
  - Windows: `winget install Gyan.FFmpeg` (then open a new terminal)
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- An API key for one LLM provider (see below)

---

## Installation & Setup

```bash
cd agents/video-analysis-agent
python -m venv .venv
```

Install the dependencies using the virtual environment's own Python, so you do not need to "activate" it (this avoids the PowerShell *"running scripts is disabled"* error):

```bash
# Windows (PowerShell / cmd)
.venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux / macOS
.venv/bin/python -m pip install -r requirements.txt
```

Every command below uses `python`. Either activate the venv first (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on Linux/macOS) or replace `python` with the venv path shown above.

> **Windows tip:** if `Activate.ps1` is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (affects only the current window) or skip activation as described above.
> **FFmpeg not found after installing it?** Open a brand-new terminal (restart your IDE if you use its terminal) so the updated `PATH` is picked up.

### Setting your LLM API key

Pick **one** provider and set its key in your terminal. This lasts for the current terminal window only.

```bash
# Anthropic (Claude)
export ANTHROPIC_API_KEY="sk-ant-..."        # Linux / macOS
$env:ANTHROPIC_API_KEY = "sk-ant-..."        # Windows PowerShell
set ANTHROPIC_API_KEY=sk-ant-...             # Windows cmd

# Gemini:  GEMINI_API_KEY      OpenAI:  OPENAI_API_KEY
```

Alternatively copy `.env.example` to `.env` and fill it in (`.env` is git-ignored). If no key is found and you are in an interactive terminal, the agent asks for the provider and a hidden key for that run only.

**Your key stays private:** it is never printed, logged, written to the reports, or saved by the agent. It is only sent in the request header to the provider you chose. Never commit `.env` or paste a key into an issue or PR.

### Verify the setup

```bash
python -m video_analysis_agent --check     # checks FFmpeg, Whisper and API key
```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | One provider key required | *None* | Gemini key |
| `OPENAI_API_KEY` | One provider key required | *None* | OpenAI key |
| `ANTHROPIC_API_KEY` | One provider key required | *None* | Anthropic key |
| `LLM_PROVIDER` | No | auto-detected | `gemini`, `openai` or `anthropic` |
| `MODEL_NAME` | No | per provider | LLM model name |
| `OPENAI_BASE_URL` | No | OpenAI API | Any OpenAI-compatible server, e.g. `http://localhost:11434/v1` (Ollama; no key needed) |
| `WHISPER_MODEL` | No | `base` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_DEVICE` | No | `cpu` | `cpu`, `cuda`, or `auto` (tries GPU, falls back to CPU) |
| `WHISPER_COMPUTE_TYPE` | No | `int8` | CTranslate2 compute type |

---

## How to Run

```bash
python -m video_analysis_agent path/to/meeting.mp4
```

Common options:

```bash
python -m video_analysis_agent meeting.mov -o results/standup      # choose output folder
python -m video_analysis_agent talk.mp4 --provider openai --llm-model gpt-4o-mini
python -m video_analysis_agent talk.mp4 --whisper-model small --language en
python -m video_analysis_agent noisy.mp4 --denoise                 # optional FFmpeg cleanup
python -m video_analysis_agent concert-talk.mp4 --separate-vocals  # optional; pip install demucs
python -m video_analysis_agent output/meeting/transcript.json      # re-run analysis only
python -m video_analysis_agent --help
```

Outputs go to `output/<video-name>/` by default: `report.md`, `report.json`, `transcript.txt`, `transcript.json`. The report is also printed to the terminal (`--no-print` to disable).

---

## Example Input & Output

### Example Input
A 20-second recording of a team call (`meeting.mp4`):
> "OK team, let's start with the launch date. Agreed, we are launching on March 14th. That is final. Priya, can you update the pricing page? Sure, I will finish it by Wednesday. Does anyone know what the budget for ads is?"

### Example Output (`report.md`, abridged)
```
## Decisions (confirmed)
- [00:00:03] Launch on March 14
  > we are launching on March 14th

## Action items
| Time     | Task                | Owner | Deadline  |
| 00:00:12 | Update pricing page | Priya | Wednesday |

## Unresolved questions & open discussion
- [00:00:15] What is the ad budget?

## Warnings
- Dropped unsupported action_items item (quote not in transcript): ...
```
Owners and deadlines that are not stated show as `not stated`.

---

## How to Test

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a fake LLM and need no API key, FFmpeg or model download. They cover evidence validation, chunking, retries, error handling and the report pipeline. For a full manual run, record a short clip with speech and run the command above with a real key.

---

## Known Limitations

- **No speaker identification.** Owners are only filled in when a person is named in the speech. "Tom will do it" works, but a different voice answering "I'll do it" does not identify who spoke.
- **Whisper accuracy.** The default `base` model can mishear names and numbers. Use `--whisper-model small` or larger for accuracy; low-confidence segments are flagged in the report.
- **Quote checking is lexical.** It guarantees quotes exist in the transcript, not that the LLM interpreted them correctly. Insights are inference and labelled as such.
- **Speed.** Transcription runs on CPU by default. Long videos with larger models take a while. Set `WHISPER_DEVICE=cuda` if you have CUDA libraries installed.
- **`--separate-vocals`** needs Demucs (large install with PyTorch) and is slow on CPU.
- **API behavior.** Gemini, OpenAI and Anthropic requests use plain HTTPS, so they depend on those APIs' current response formats. Free-tier rate limits can still cause failures after retries.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys come from environment variables, `.env` (git-ignored) or a hidden prompt, and are only sent in request headers to the provider you chose.
- **Data Privacy**: audio never leaves your machine (Whisper runs locally). The **transcript text** is sent to the LLM provider you select. Use a local OpenAI-compatible server (`OPENAI_BASE_URL`) to keep everything offline.
- **Safety**: the agent runs only `ffmpeg`, `ffprobe` and (optionally) `demucs`, with arguments passed as a list (no shell). Treat video files from unknown sources with the usual FFmpeg caution.

---

## Future Improvements

- [ ] Speaker diarization to attribute owners and quotes to voices
- [ ] Subtitle (SRT/VTT) export and clickable timestamps
- [ ] Direct URL input (YouTube etc.) and batch folders
- [ ] Local-LLM presets (Ollama) and token/cost reporting
- [ ] LLM-based second pass to verify each extracted item against its quote
- [ ] Question answering over the transcript

---

## License

*This project is contributed under the repository's open-source license.*
