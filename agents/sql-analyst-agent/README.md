# SQLite AI Analyst Agent

An autonomous text-to-SQL data analyst agent powered by the Google GenAI SDK (\gemini-3.8-flash\) and an embedded SQLite database. It inspects schema structures dynamically, translates natural language inquiries into validated SQL queries, enforces read-only execution guardrails, and returns natural-language analytical summaries.

## Architecture & Technology Stack
- **Model & SDK:** Gemini 3.8 Flash via \google-genai\ SDK
- **Runtime:** Python 3.10+
- **Database:** SQLite (embedded, provisions sample tables on startup)
- **Safety:** Read-only statement prefix validation preventing mutating operations (\INSERT\, \UPDATE\, \DELETE\, \DROP\, \ALTER\)

## Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- Gemini API Key from Google AI Studio

### 2. Setup & Installation
\\\ash
cd agents/sql-analyst-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
\\\

### 3. API Key Configuration
Create a \.env\ file from \.env.example\:
\\\env
GEMINI_API_KEY="your_api_key_here"
\\\

### 4. Running the Agent
\\\ash
python agent.py
\\\

## Example Run

**User Prompt:**
\Who is the highest paid engineer and what is their salary?\

**Generated SQL:**
\\\sql
SELECT name, salary 
FROM employees 
WHERE department = 'Engineering' 
ORDER BY salary DESC 
LIMIT 1;
\\\

**Analysis Output:**
\The highest-paid engineer is Elena Rostova, with a salary of ,000.\

## Safety Guardrails
- **Read-Only Enforcement:** Queries starting with non-query prefixes (\UPDATE\, \DROP\, \DELETE\, \INSERT\) are blocked.
- **Zero Secrets Tracked:** Git ignores local \.env\ and \.db\ files.
