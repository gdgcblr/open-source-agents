#!/usr/bin/env python3
"""
Simulate Meeting Script for MeetingMind AI Agent
Simulates an end-to-end Google Meet session with multiple speakers,
transcription chunks, Gemma summarization, action item extraction,
missing deadline detection, and Drive/Calendar MCP tool execution.
"""

import os
import sys
import json
import asyncio
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from adk_engine.orchestrator import A2AOrchestrator
from mcp_servers.workspace_mcp import WorkspaceMCPServer
from mcp_servers.task_store_mcp import TaskStoreMCPServer

SAMPLE_TRANSCRIPT = [
    {"speaker": "Sarah Chen", "text": "Good morning everyone. Let's kick off our Q3 Architecture and Planning sync.", "timestamp": "2026-10-24T10:00:00Z"},
    {"speaker": "Alex Rivera", "text": "Morning Sarah. We have three main items: database migration, the API gateway refactor, and security compliance.", "timestamp": "2026-10-24T10:00:15Z"},
    {"speaker": "Sarah Chen", "text": "Great. For the database migration, Alex, can you lead the benchmark tests?", "timestamp": "2026-10-24T10:00:40Z"},
    {"speaker": "Alex Rivera", "text": "Yes, I will run the PostgreSQL benchmark tests and share the performance report by this Friday at 5 PM.", "timestamp": "2026-10-24T10:01:05Z"},
    {"speaker": "Sarah Chen", "text": "Awesome. David, what about the security audit findings?", "timestamp": "2026-10-24T10:01:30Z"},
    {"speaker": "David Kim", "text": "I will review the SOC2 audit findings and patch the authorization headers.", "timestamp": "2026-10-24T10:01:50Z"},
    {"speaker": "Sarah Chen", "text": "Do you have an ETA for that David?", "timestamp": "2026-10-24T10:02:00Z"},
    {"speaker": "David Kim", "text": "I need to check the team bandwidth first, so no fixed date yet.", "timestamp": "2026-10-24T10:02:10Z"},
    {"speaker": "Sarah Chen", "text": "Alright, let's make sure that is tracked. I will schedule the demo with our executive stakeholders for next Tuesday 10 AM.", "timestamp": "2026-10-24T10:02:35Z"},
    {"speaker": "Alex Rivera", "text": "Sounds good. We agreed to proceed with the migration proposal.", "timestamp": "2026-10-24T10:02:50Z"}
]

async def run_simulation():
    print("=" * 70)
    print("🎯 MeetingMind AI — End-to-End Meeting Simulation")
    print("=" * 70)

    meeting_id = "meet-q3-planning-demo"
    meeting_title = "Q3 Architecture & Planning Sync"

    orchestrator = A2AOrchestrator()
    task_store = TaskStoreMCPServer(db_path="/tmp/simulated_meetingmind.db")
    workspace_mcp = WorkspaceMCPServer()

    print(f"\n[Step 1] Ingesting {len(SAMPLE_TRANSCRIPT)} live speech chunks from Google Meet...")
    clean_chunks = orchestrator.ingestion_agent.process_transcript(SAMPLE_TRANSCRIPT)
    formatted = orchestrator.ingestion_agent.format_for_llm(clean_chunks)
    print(f"✔ Diarized into {len(clean_chunks)} aggregated speaker segments.")

    print("\n[Step 2] Executing Gemma Summarizer Agent...")
    summary = await orchestrator.summarizer_agent.summarize(meeting_title, formatted)
    print("\n--- Executive Summary ---")
    print(f"Overview: {summary.get('overview')}")
    print("\nKey Highlights:")
    for kp in summary.get("keyPoints", []):
        print(f"  • {kp}")
    print("\nKey Decisions:")
    for d in summary.get("decisions", []):
        print(f"  ✓ {d}")

    print("\n[Step 3] Executing Gemma Action Extractor Agent...")
    action_items = await orchestrator.action_extractor_agent.extract_actions(meeting_id, meeting_title, formatted)
    print(f"\n✔ Extracted {len(action_items)} action items mapped to participants:")
    for idx, item in enumerate(action_items, 1):
        deadline_text = item.get("deadline") or "⚠️ [NO DEADLINE - Requires User Input]"
        print(f"  {idx}. [{item.get('owner')}] {item.get('task')}")
        print(f"     Due: {deadline_text} | Priority: {item.get('priority')}")
        task_store.upsert_task(item)

    print("\n[Step 4] Scheduler Agent: Evaluating Deadlines...")
    eval_res = orchestrator.scheduler_agent.evaluate_tasks_for_scheduling(action_items)
    print(f"  • Ready to sync to Google Calendar: {len(eval_res['ready_to_schedule'])} task(s)")
    print(f"  • Tasks needing user deadline input: {len(eval_res['needs_deadline'])} task(s)")
    for need in eval_res['needs_deadline']:
        print(f"    -> Action required for {need.get('owner')}: \"{need.get('task')}\"")

    print("\n[Step 5] Nudge Agent: Automated Email Nudge Evaluation...")
    for need in eval_res['needs_deadline']:
        nudge_content = await orchestrator.nudge_agent.generate_nudge_email(need, "missing_deadline")
        print(f"\n  [Draft Email to {need.get('owner')}]")
        print(f"  Subject: {nudge_content.get('subject')}")
        print(f"  Body:\n{nudge_content.get('body')}")

    print("\n[Step 6] MCP Tool: Formatting Google Drive Document...")
    drive_md = workspace_mcp._format_markdown({
        "title": meeting_title,
        "summary": summary,
        "action_items": action_items,
        "transcript": clean_chunks
    })
    print("✔ Google Drive Markdown Preview:")
    print("-" * 40)
    print("\n".join(drive_md.split("\n")[:18]))
    print("... (full transcript appended) ...")
    print("-" * 40)

    print("\n🎉 SIMULATION SUCCESSFUL! All agents, models, and MCP tools executed cleanly.")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_simulation())

