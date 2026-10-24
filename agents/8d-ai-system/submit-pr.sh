#!/usr/bin/env bash
# submit-pr.sh — forks gdgcblr/open-source-agents, copies the 8d-ai-system
# project into agents/8d-ai-system/, and opens a PR.
# Prerequisites: gh auth login (github.com) must already be done.

set -euo pipefail

PROJECT_SLUG="8d-ai-system"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="gdgcblr/open-source-agents"
BRANCH="add-agent-${PROJECT_SLUG}"
WORK_DIR="/tmp/open-source-agents-pr"

echo "→ Forking $UPSTREAM ..."
gh repo fork "$UPSTREAM" --clone=false --default-branch-only 2>/dev/null || true
FORK=$(gh repo view "$UPSTREAM" --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null \
  || gh api user --jq '.login' | xargs -I{} echo "{}/open-source-agents")

echo "→ Cloning fork to $WORK_DIR ..."
rm -rf "$WORK_DIR"
gh repo clone "$(gh api user --jq '.login')/open-source-agents" "$WORK_DIR"

cd "$WORK_DIR"
git checkout -b "$BRANCH"

TARGET="$WORK_DIR/agents/$PROJECT_SLUG"
mkdir -p "$TARGET"

echo "→ Copying project files ..."
rsync -a \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='dev.db' \
  --exclude='prisma/dev.db' \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='.claude' \
  --exclude='.agents' \
  --exclude='.windsurf' \
  --exclude='skills-lock.json' \
  --exclude='next-env.d.ts' \
  --exclude='*.tsbuildinfo' \
  "$SOURCE_DIR/" "$TARGET/"

echo "→ Committing ..."
git add "agents/$PROJECT_SLUG"
git commit -m "feat: add 8D AI System — AI-guided root cause analysis agent

A Next.js 16 web app that guides quality engineers through the full
8-Disciplines (8D) problem-solving methodology with AI-generated
structured suggestions for each step, human-in-the-loop approval,
Fishbone diagram rendering, and a full audit trail."

echo "→ Pushing branch ..."
git push -u origin "$BRANCH"

echo "→ Opening PR ..."
gh pr create \
  --repo "$UPSTREAM" \
  --title "feat: add agents/8d-ai-system — AI-guided 8D Root Cause Analysis" \
  --body "$(cat <<'PREOF'
## Project Overview

**Project Name:** 8D AI System

**Category:** agents/8d-ai-system

**Frameworks & Technologies Used:** Next.js 16, React 19, TypeScript 5, Tailwind CSS v4, Prisma 7, SQLite (better-sqlite3), OpenAI-compatible LLM API, Lucide React

---

## Description

An AI-assisted web application that guides quality engineers through the full **8 Disciplines (8D) problem-solving methodology** used in manufacturing quality management.

When a defect is discovered (oil leak, surface finish failure, dimensional non-conformance), teams must trace the root cause and put permanent fixes in place. This system replaces manual spreadsheet-based 8D tracking with an AI-guided, database-backed workflow:

- The **AI generates structured suggestions** for each D-step (D1 Team Formation → D8 Closure) using any OpenAI-compatible LLM
- **Engineers review, edit, and approve** each step before the case advances
- **D4 Root Cause Analysis** includes a live-rendered SVG Ishikawa (Fishbone) diagram plus 5-Why drill-down
- Every action (AI suggestion, human edit, approval) is captured in an **immutable audit trail**
- **Similar case search** surfaces resolved cases that match keywords in the new problem

The stack is intentionally minimal: Next.js App Router for the full stack, Prisma + SQLite for zero-infrastructure persistence, and a thin LLM wrapper that works with any OpenAI-compatible endpoint (local models, OpenAI, etc.).

---

## Contribution Checklist

- [x] **Directory & Naming:** Project is under `agents/8d-ai-system/` using lowercase kebab-case
- [x] **Documentation:** Complete `README.md` present with all sections (architecture, API reference, data models, AI integration, setup)
- [x] **Reproducible Setup:** `npm install` + `npx prisma migrate dev` + `npm run dev` — verified from scratch
- [x] **Core Functionality Tested:** App runs on `localhost:3000`; cases can be created, AI suggestions generated for all 8 steps, steps approved, case closes at D8
- [x] **Example Usage:** `npm run seed` loads 2 realistic closed cases (surface finish defect + cylinder head oil leak) with full D1/D2/D4 content and Fishbone data
- [x] **Dependencies Declared:** All dependencies in `package.json` with locked versions in `package-lock.json`
- [x] **Secrets & Security:** No API keys committed; `.env.example` documents all required variables; `.env` and `.env.local` are git-ignored
- [x] **Scope Limitation:** All changes confined to `agents/8d-ai-system/`; no other repo files modified

---

## Testing & Verification Notes

**Setup tested on:** macOS (Node.js 20+)

**Steps to verify:**
1. `cd agents/8d-ai-system && npm install`
2. `npx prisma migrate dev` — creates `prisma/dev.db`
3. `npm run seed` — loads 2 sample closed cases
4. Set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `.env.local` (copy `.env.example`)
5. `npm run dev` → open `http://localhost:3000`
6. Click **New 8D Case**, fill in the form, submit
7. On the case page, click **Generate with AI** for D1 — verify structured team suggestion appears
8. Click **Approve & Continue** — verify case advances to D2
9. Repeat through D4 — verify Fishbone diagram renders in the D4 panel
10. Complete through D8 — verify case status becomes `CLOSED`

**Known requirement:** An LLM endpoint that supports the OpenAI `/v1/chat/completions` API is required for the AI features. The dashboard, case creation, and step approval flow all work without it.
PREOF
)"

echo ""
echo "✅ PR created. Check: https://github.com/$UPSTREAM/pulls"
