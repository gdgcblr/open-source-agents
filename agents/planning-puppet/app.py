"""app.py – Planning Puppet: Streamlit Web UI.

Run this file to start the interactive web interface for Planning Puppet.
Uses the same Google ADK agent, tools (including Google Maps venue search),
and LLM-as-a-Judge quality evaluator.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

# Configure UTF-8 for terminal/logging safety
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
import streamlit as st
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent
from evaluator import evaluate_plan, format_evaluation_report

load_dotenv()

# ---------------------------------------------------------------------------
# Streamlit Page Setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Planning Puppet 🎉",
    page_icon="🎉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎉 Planning Puppet")
st.caption(
    "Your AI-powered event concierge for weddings, birthdays & celebrations — "
    "powered by Google ADK & Google Maps Places API."
)

APP_NAME = "planning-puppet-web"
USER_ID = "host-user"

# Guard: verify Gemini API key
gemini_key = os.getenv("GEMINI_API_KEY")
if not gemini_key or gemini_key == "your_gemini_api_key_here":
    st.error("Missing `GEMINI_API_KEY`. Please add your key to `.env` before running.")
    st.stop()


# ---------------------------------------------------------------------------
# ADK Async Runner Helpers
# ---------------------------------------------------------------------------


async def _init_adk():
    service = InMemorySessionService()
    session = await service.create_session(app_name=APP_NAME, user_id=USER_ID, state={})
    runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=service)
    return session, runner


async def _execute_turn(runner: Runner, session_id: str, prompt: str) -> str:
    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    response_text = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=content):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    response_text = part.text
    return response_text


# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------

if "runner_ready" not in st.session_state:
    session, runner = asyncio.run(_init_adk())
    st.session_state.session = session
    st.session_state.runner = runner
    st.session_state.runner_ready = True

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Hello! I am **Planning Puppet** 🎉 your personal event planning concierge!\n\n"
                "Tell me about your upcoming celebration — the event type, approximate date, "
                "guest count, budget, and destination city — and I'll generate a complete plan "
                "with budget breakdowns, timelines, checklists, mood boards, and venue map locations!"
            ),
            "evaluation": None,
        }
    ]


# ---------------------------------------------------------------------------
# Sidebar Controls & Presets
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Controls")

    eval_enabled = st.toggle(
        "Enable Quality Evaluator",
        value=os.getenv("ENABLE_EVALUATOR", "false").lower() == "true",
        help="Runs LLM-as-a-Judge evaluation after each response to score plan quality.",
    )

    st.markdown("---")
    st.subheader("💡 Quick Demo Prompts")

    if st.button("💍 Boho Wedding in Bangalore", use_container_width=True):
        st.session_state.preset_prompt = (
            "I'm planning a garden wedding for 80 guests on June 15, 2027, with a budget of "
            "$24,000 and a romantic boho aesthetic in Bangalore. Give me a budget breakdown, "
            "timeline, vendor checklist, and top venue recommendations with map locations."
        )
        st.rerun()

    if st.button("🎂 30th Birthday Dinner (15 guests)", use_container_width=True):
        st.session_state.preset_prompt = (
            "Plan an evening 30th birthday dinner for 15 people in Bangalore with a "
            "budget of Rs. 25,000. Provide decor suggestions, timeline, and venue options with map links."
        )
        st.rerun()

    if st.button("🏕️ Team Offsite in Goa", use_container_width=True):
        st.session_state.preset_prompt = (
            "Plan a 2-day team offsite for 20 people in Goa with a budget of Rs. 1,50,000. "
            "Suggest beachside venues, activities, and logistics checklist."
        )
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset Chat", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Conversation reset. What celebration are we planning next?",
                "evaluation": None,
            }
        ]
        st.rerun()


# ---------------------------------------------------------------------------
# Render Message History
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("evaluation"):
            with st.expander("📊 Quality Evaluation Report"):
                st.markdown(msg["evaluation"])


# ---------------------------------------------------------------------------
# Input Handling
# ---------------------------------------------------------------------------

user_input = None
if st.session_state.get("preset_prompt"):
    user_input = st.session_state.preset_prompt
    st.session_state.preset_prompt = None
else:
    user_input = st.chat_input("E.g., Plan a boho wedding for 80 guests in Bangalore...")

if user_input:
    # 1. Show user message
    st.session_state.messages.append({"role": "user", "content": user_input, "evaluation": None})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Execute agent response
    with st.chat_message("assistant"):
        with st.spinner("Planning Puppet is crafting your plan & curating venues…"):
            try:
                response_text = asyncio.run(
                    _execute_turn(st.session_state.runner, st.session_state.session.id, user_input)
                )

                if not response_text:
                    response_text = "*(No text response received — the agent may have processed internal tool operations.)*"

                st.markdown(response_text)

                # 3. Optional Evaluator
                eval_report_str = None
                if eval_enabled:
                    with st.status("Grading plan with LLM-as-a-Judge…", expanded=False):
                        eval_result = evaluate_plan(response_text)
                        raw_report = format_evaluation_report(eval_result)
                        # Strip Rich terminal tags for clean markdown rendering
                        eval_report_str = re.sub(
                            r"\[/?(?:bold|cyan|green|yellow|red|magenta|dim|#\w+)[^\]]*\]",
                            "",
                            str(raw_report),
                        )
                    with st.expander("📊 Quality Evaluation Report"):
                        st.markdown(eval_report_str)

                # 4. Save to history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "evaluation": eval_report_str,
                })

            except Exception as e:
                st.error(f"Execution Error: {e}")
