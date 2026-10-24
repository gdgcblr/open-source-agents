import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from .tools import decode_upi_qr, extract_pricing_and_autopay, audit_app_permissions

# Load environment variables from both the package directory and parent directory
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

raw_model = os.getenv("MODEL_NAME", "gemini-3.8-flash").strip()

if raw_model.startswith("ollama"):
    api_base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
    active_model = LiteLlm(model=raw_model, api_base=api_base)
else:
    clean_model = raw_model.replace("gemini/", "")
    if "gemma" in clean_model.lower() or "2.5" in clean_model:
        clean_model = "gemini-3.8-flash"
    active_model = clean_model

# Step 1: Parse User Intent
intent_parser_agent = LlmAgent(
    name="intent_parser_agent",
    model=active_model,
    description="Extracts structured user intent and echoes the raw screen text for downstream analysis.",
    instruction="""
    You are Step 1 of the IntentShield Engine.
    Read the user's message and output:
    - Goal: What they want to do
    - Max Expected Cost (INR): 0 if they expect a free trial, refund, or free utility
    - Expected Recipient: Who they intend to pay (or None)
    - Raw Screen Payload: Copy the exact SCREEN text or QR URI from the user's message verbatim.
    """,
    output_key="parsed_intent"
)

# Step 2: Analyze Actual Screen / QR Consequences
consequence_analyzer_agent = LlmAgent(
    name="consequence_analyzer_agent",
    model=active_model,
    description="Uses tools to extract the actual financial or privacy consequence of a screen or QR code.",
    instruction="""
    You are Step 2 of the IntentShield Engine.
    Look at the Raw Screen Payload in {parsed_intent} and the user's original message:
    - If it contains `upi://pay`, call `decode_upi_qr` with the exact `upi://pay...` URI string.
    - If it mentions a trial, subscription, ₹, or Autopay, call `extract_pricing_and_autopay` with the screen text.
    - If it mentions permissions (Contacts, SMS, Location, Call Logs), call `audit_app_permissions`.
    
    After calling the appropriate tool, clearly state the exact real-world financial or privacy consequence of proceeding.
    """,
    tools=[decode_upi_qr, extract_pricing_and_autopay, audit_app_permissions],
    output_key="actual_consequence"
)

# Step 3: Compare Intent vs Consequence & Guide User
companion_shield_agent = LlmAgent(
    name="companion_shield_agent",
    model=active_model,
    description="Compares user intent against actual screen consequences and outputs Explain, Protect, and Guide advice.",
    instruction="""
    You are Digital Companion, helping an elderly user make safe digital decisions.
    Compare USER INTENT:
    {parsed_intent}
    
    With ACTUAL CONSEQUENCE:
    {actual_consequence}

    Format your response with these exact sections:
    ### 🛡️ Status: [⚠️ INTENT CONFLICT DETECTED or ✅ SAFE TO PROCEED]
    ### 💡 EXPLAIN (In Simple Language)
    ### 🚨 PROTECT (What You Wanted vs. What Will Actually Happen)
    ### 👉 GUIDE (Safest Next Action)
    """,
    output_key="shield_report"
)

# Root Sequential Agent pipeline required by Google ADK
root_agent = SequentialAgent(
    name="digital_companion",
    description="IntentShield Multi-Agent Pipeline that protects users when screen consequences conflict with user intent.",
    sub_agents=[intent_parser_agent, consequence_analyzer_agent, companion_shield_agent]
)