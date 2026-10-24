# PII Compliance Redaction Tool

> A secure, lightweight PII detection and redaction MCP server with comprehensive guardrails for GDPR, CCPA, and HIPAA compliance. Designed for AI agent integration.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Organizations handling sensitive data face significant challenges in detecting and redacting Personally Identifiable Information (PII) to comply with regulations like GDPR, CCPA, and HIPAA. Manual redaction is error-prone, time-consuming, and inconsistent. Existing tools often lack comprehensive guardrails, audit trails, or multi-regulatory support.
- **Intended Users**: 
  - AI agents connecting via MCP for automated PII handling
  - Developers using CLI for data processing
  - DevOps teams processing sensitive data in pipelines
  - Healthcare organizations processing patient data

### Key Features
- **MCP Server**: Model Context Protocol server for AI agent integration
- **Lightweight Detection**: Regex-based PII detection (no heavy dependencies)
- **Optional AI Enhancement**: Ollama (local AI) for context-aware detection without data leaving your computer
- **Compliance Modes**: Built-in support for GDPR, CCPA, HIPAA, and STRICT
- **Redaction Strategies**: Full, partial, hash-based, and pattern-preserving mask
- **Comprehensive Guardrails**: Input validation, rate limiting, confidence filtering, audit logging
- **Streaming Support**: Process large files efficiently
- **Docker Support**: Containerized deployment for easy setup
- **Performance Benchmarks**: Built-in performance testing suite

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Core Libraries**:
  - Pydantic (Configuration and validation)
  - Click (CLI interface)
  - Rich (Terminal UI)
- **MCP Server**: mcp (Model Context Protocol)
- **AI Model** (optional): Ollama (local AI for privacy-preserving detection)
- **Containerization**: Docker

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PII Redaction Tool                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │   CLI Mode   │  │  MCP Server  │                             │
│  │   (main.py)  │  │ (mcp_server) │                             │
│  └──────┬───────┘  └──────┬───────┘                             │
│         │                 │                                      │
│         └─────────────────┘                                      │
│                           ▼                                       │
│              ┌──────────────────────┐                           │
│              │  Core Logic Layer    │                           │
│              ├──────────────────────┤                           │
│              │ • PII Detector       │                           │
│              │ • Redaction Engine   │                           │
│              │ • Security Guardrails│                           │
│              └──────────────────────┘                           │
│                           │                                       │
│                           ▼                                       │
│              ┌──────────────────────┐                           │
│              │  Detection Layers    │                           │
│              ├──────────────────────┤                           │
│              │ • Regex (primary)    │                           │
│              │ • Ollama AI (optional, local) │
│              └──────────────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Usage Modes

This tool can be used in two ways:
1. **CLI**: Direct command-line usage for one-off redaction tasks
2. **MCP Server**: AI agents connect via MCP to use PII redaction tools

---

## Prerequisites

Before running this project, ensure you have:
- Python 3.10 or higher
- pip (Python package manager)
- Docker (optional, for containerized deployment)
- (Optional) Google AI Studio API key for AI-based detection

---

## Installation & Setup

### Option 1: Local Installation

1. **Navigate to the project directory:**
   ```bash
   cd tools/pii-redaction-tool
   ```

2. **Set up the virtual environment:**
   ```bash
   python -m venv .venv

   # Windows:
   .venv\Scripts\activate

   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `ENABLE_AI_DETECTION=true` if you want AI-based detection (requires Ollama):
   ```
   ENABLE_AI_DETECTION=true
   ```

   **Note:** To use AI detection, you need to install and run Ollama:
   1. Download Ollama from https://ollama.com
   2. Run: `ollama pull llama3.2`
   3. Run: `ollama serve` (starts Ollama server on port 11434)
   4. Set `ENABLE_AI_DETECTION=true` in `.env`

### Option 2: Docker Deployment

1. **Build the Docker image:**
   ```bash
   docker build -t pii-redaction-tool .
   ```

2. **Run the container:**
   ```bash
   docker run -p 8000:8000 pii-redaction-tool
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `OLLAMA_URL` | No | `http://localhost:11434/api/generate` | Ollama API URL for local AI detection (optional, only if ENABLE_AI_DETECTION=true) |
| `OLLAMA_MODEL` | No | `llama3.2` | Ollama model name for AI-based detection (optional, only if ENABLE_AI_DETECTION=true) |
| `CONFIDENCE_THRESHOLD` | No | `0.7` | Minimum confidence score for PII detection (0.0-1.0) |
| `ENABLE_REGEX_DETECTION` | No | `true` | Enable regex-based detection layer |
| `ENABLE_AI_DETECTION` | No | `false` | Enable AI-based detection layer (requires Ollama to be installed and running) |
| `REDACTION_STRATEGY` | No | `full` | Redaction strategy: full, partial, hash, mask |
| `REDACTION_CHAR` | No | `[REDACTED]` | Replacement text for full redaction |
| `PARTIAL_REDACTION_LENGTH` | No | `4` | Characters to show in partial redaction |
| `COMPLIANCE_MODE` | No | `GDPR` | Compliance mode: GDPR, CCPA, HIPAA, STRICT |
| `MAX_INPUT_SIZE` | No | `10000000` | Maximum input size in bytes (10MB) |
| `RATE_LIMIT_REQUESTS` | No | `100` | Rate limit: requests per period |
| `RATE_LIMIT_PERIOD` | No | `60` | Rate limit period in seconds |
| `ENABLE_AUDIT_LOGGING` | No | `true` | Enable audit logging |
| `AUDIT_LOG_PATH` | No | `audit.log` | Path to audit log file |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: DEBUG, INFO, WARNING, ERROR |

---

## How to Run

### CLI Mode

**Redact PII from text:**
```bash
python main.py redact "Contact John Smith at john.smith@example.com or 555-123-4567"
```

**Redact PII from a file:**
```bash
python main.py redact --file input.txt --output redacted.txt
```

**Use specific redaction strategy:**
```bash
python main.py redact "Email: test@example.com" --strategy partial
```

**Use specific compliance mode:**
```bash
python main.py redact "Patient data..." --compliance HIPAA
```

**Detect PII only:**
```bash
python main.py detect "Contact John Smith at john.smith@example.com"
```

**Run evaluation:**
```bash
python main.py evaluate
```

**View audit logs:**
```bash
python main.py audit
```

### MCP Server Mode (for AI Agents)

**Start MCP server:**
```bash
python main.py mcp-server
```

AI agents can now connect to this MCP server and use the following tools:
- `detect_pii`: Detect PII in text
- `redact_pii`: Redact PII from text
- `check_compliance`: Check text compliance
- `get_pii_summary`: Get PII summary statistics

**Example MCP tool call:**
```python
# Agent calls your MCP tool
result = agent.call_tool(
    server="pii-redaction",
    tool="redact_pii",
    params={
        "text": "Contact john@example.com",
        "strategy": "partial",
        "compliance_mode": "GDPR"
    }
)
# Returns: "Contact jo****@example.com"
```

### Setting Up Ollama (Optional, for AI Detection)

**Why Ollama?**
- Privacy-preserving: AI runs locally, no data leaves your computer
- Free: No API costs
- Works offline: No internet connection required
- Suitable for compliance: Meets GDPR, HIPAA requirements

**Installation Steps:**

1. **Download Ollama:**
   - Visit https://ollama.com
   - Download and install for your OS (Windows, macOS, or Linux)

2. **Pull the model:**
   ```bash
   ollama pull llama3.2
   ```

3. **Start Ollama server:**
   ```bash
   ollama serve
   ```
   (This starts the Ollama server on `http://localhost:11434`)

4. **Enable AI detection in the tool:**
   - In your `.env` file, set:
     ```
     ENABLE_AI_DETECTION=true
     ```

5. **Test AI detection:**
   ```bash
   python main.py detect "Contact John Smith at john.smith@example.com"
   ```

**Ollama Configuration Variables:**
- `OLLAMA_URL`: Ollama API URL (default: `http://localhost:11434/api/generate`)
- `OLLAMA_MODEL`: Model to use (default: `llama3.2`)

### Performance Benchmarks

**Run benchmarks:**
```bash
python benchmark.py
```

**Benchmark Results:**
- Detection: 66,608 ops/sec (avg: 0.02 ms)
- Redaction: 50,471 ops/sec (avg: 0.02 ms)
- Full pipeline: 952 ops/sec (avg: 1.06 ms)

This will test detection, redaction, and full pipeline performance across multiple text samples.

---

## Example Input & Output

### Example 1: CLI Redaction

**Input:**
```
Contact John Smith at john.smith@example.com or 555-123-4567. SSN: 123-45-6789
```

**Output (full redaction):**
```
Contact [REDACTED] at [REDACTED] or [REDACTED]. SSN: [REDACTED]
```

**Output (partial redaction):**
```
Contact Jo**** Sm*** at jo****@example.com or 555-****-4567. SSN: ***-**-6789
```

### Example 2: MCP Tool Call

**Tool:** `redact_pii`
**Parameters:**
```json
{
  "text": "Email: test@example.com",
  "strategy": "hash",
  "compliance_mode": "GDPR"
}
```

**Response:**
```json
{
  "redacted_text": "Email: [EMAIL_ADDRESS_HASH:973dfe46]",
  "compliance_report": {
    "compliance_standard": "GDPR",
    "categories_redacted": {"EMAIL_ADDRESS": 1},
    "total_entities_redacted": 1
  }
}
```



---

## How to Test

### CLI Testing

```bash
# Test basic detection
python main.py detect "Contact John Smith at john.smith@example.com"

# Test redaction with different strategies
python main.py redact "Email: test@example.com" --strategy full
python main.py redact "Email: test@example.com" --strategy partial
python main.py redact "Email: test@example.com" --strategy hash

# Test compliance modes
python main.py redact "Patient Jane Doe, DOB 01/15/1980" --compliance HIPAA
python main.py redact "Employee John Smith, Email john@company.com" --compliance GDPR

# Verify audit logging
python main.py audit
```

### MCP Server Testing

1. Start MCP server:
```bash
python main.py mcp-server
```

2. Connect your AI agent to the MCP server and test tool calls.

### Performance Testing

```bash
python benchmark.py
```

---

## Known Limitations

- **AI Detection**: Requires Ollama to be installed and running locally; without it, only regex detection works
- **Text Size Limit**: Maximum input size is 10MB by default (configurable)
- **Language Support**: Currently optimized for English text
- **False Positives**: May redact non-PII that matches patterns (e.g., invoice numbers resembling SSNs)
- **Context Awareness**: Does not understand context; may redact benign data that looks like PII
- **Real-time Processing**: Not optimized for streaming or real-time use cases
- **Platform Testing**: Tested on Windows; Linux and macOS support expected but not tested
- **Python Version**: Python 3.10-3.12 recommended for best compatibility

---

## Security & Privacy Considerations

### Secrets Handling
- All credentials are loaded from environment variables via `.env` file
- `.env` file is included in `.gitignore` to prevent accidental commits
- No secrets are hardcoded in the source code
- API keys are never logged or included in audit trails

### Data Privacy
- **Local Processing**: Regex detection runs entirely locally without external API calls
- **Optional AI Layer**: AI-based detection uses Ollama (local AI) - no data leaves your computer
- **No Data Storage**: The tool does not store input text or redacted output
- **Audit Logging**: Audit logs contain only metadata (hashes, counts, categories), not actual PII
- **Input Hashing**: Input text is hashed (SHA-256) in audit logs for traceability without content storage

### Safety
- **Input Validation**: All inputs are validated for size, encoding, and type before processing
- **Rate Limiting**: Built-in rate limiting prevents abuse and DoS attacks
- **No Code Execution**: The tool does not execute arbitrary code or shell commands
- **Read-Only Operations**: All file operations are read-only (except output file when explicitly specified)

---

## Future Improvements

- [ ] Support for additional languages (beyond English)
- [ ] Custom pattern configuration via YAML/JSON
- [ ] Integration with cloud storage (S3, GCS, Azure Blob)
- [ ] Webhook support for event-driven processing
- [ ] Advanced masking strategies based on data type
- [ ] Machine learning model for adaptive confidence thresholds
- [ ] Integration with SIEM systems for alerting
- [ ] Batch processing with parallel execution
- [ ] Support for document formats (PDF, DOCX)
- [ ] Real-time streaming API with WebSocket support

---

## License

This project is contributed under the repository's open-source license.
