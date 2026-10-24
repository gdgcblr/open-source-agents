from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import json
import os
from google import genai
from google.genai import types

st.set_page_config(page_title="The Illustrated Primer", page_icon="📖", layout="wide")

# ----------------- LIVE STATE MANAGEMENT -----------------
STATE_FILE = "student_profile.json"

DEFAULT_STATE = {
    "name": "Nell",
    "reading_level": "Phonics (CVC words, short vowels)",
    "math_level": "Basic Counting & Addition under 10",
    "interests": ["clocks", "turtles", "mysterious gardens"],
    "current_arc": "Searching for the Great Clock tower in the forest",
    "struggles": ["the 'th' blend", "subtraction from 10"],
    "mastered": [],
    "last_observation": "Initial profile initialized."
}

def get_or_create_profile():
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f:
            json.dump(DEFAULT_STATE, f, indent=2)
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_profile(profile_data):
    with open(STATE_FILE, "w") as f:
        json.dump(profile_data, f, indent=2)

profile = get_or_create_profile()

# ----------------- SIDEBAR: Primer Memory -----------------
with st.sidebar:
    st.title("🧠 Primer Memory")
    st.caption("Live Epistemic State & ZPD")
    
    st.subheader(f"👧 Student: {profile.get('name', 'Nell')}")
    st.write(f"**📖 Reading:** {profile.get('reading_level')}")
    st.write(f"**🔢 Math:** {profile.get('math_level')}")
    st.write(f"**🧭 Current Arc:** {profile.get('current_arc')}")
    
    st.divider()
    st.markdown("**⚠️ Active Struggles:**")
    for s in profile.get("struggles", []):
        st.markdown(f"- 🔴 `{s}`")
        
    st.markdown("**🏆 Mastered Skills:**")
    for m in profile.get("mastered", []):
        st.markdown(f"- 🟢 `{m}`")
        
    st.info(f"**Audit Note:**\n{profile.get('last_observation', 'None')}")

# ----------------- MAIN UI -----------------
st.title("📖 A Young Lady's Illustrated Primer")
st.caption("“It continually reshaped itself around who she was becoming.” — The Diamond Age")

# Initialize client
client = genai.Client()

# Tool definitions
def update_learning_ledger(skill: str, success: bool, note: str) -> str:
    """Updates learner progress when they demonstrate mastery or struggle."""
    curr = get_or_create_profile()
    if success:
        if skill in curr["struggles"]:
            curr["struggles"].remove(skill)
        if skill not in curr["mastered"]:
            curr["mastered"].append(skill)
    else:
        if skill not in curr["struggles"]:
            curr["struggles"].append(skill)
    curr["last_observation"] = note
    save_profile(curr)
    return f"Updated {skill}. Struggles: {curr['struggles']}. Mastered: {curr['mastered']}"

# Chat history initialization
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Welcome back, Nell. The Clockwork Valley is quiet today, but the forest gears are turning. What shall we explore together?"}
    ]

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# User Chat Input
if user_prompt := st.chat_input("Speak to the Primer..."):
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.write(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("The Primer turns its pages..."):
            system_instruction = f"""
            You are A Young Lady's Illustrated Primer from Neal Stephenson's The Diamond Age.
            You are an adaptive Socratic tutor for {profile['name']}.
            
            Current Profile:
            - Reading: {profile['reading_level']}
            - Math: {profile['math_level']}
            - Interests: {', '.join(profile['interests'])}
            - Active Struggles: {', '.join(profile['struggles'])}
            
            Directives:
            1. Never give answers directly. Guide the child with questions, sensory clues, and micro-stories.
            2. If the child gets an answer right or shows mastery, call `update_learning_ledger`.
            3. Tone: Warm, literary, patient, and curious.
            """
            
            # Format history for Gemini
            contents = []
            for m in st.session_state.messages:
                contents.append(m["content"])

            try:
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[update_learning_ledger]
                    )
                )

                # Check if model wants to call the tool
                reply_text = ""
                if response.function_calls:
                    for call in response.function_calls:
                        args = call.args
                        tool_res = update_learning_ledger(
                            skill=args.get("skill", ""),
                            success=args.get("success", False),
                            note=args.get("note", "")
                        )
                    # Get final conversational reply following the tool call
                    followup = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=contents + [f"System: Tool execution completed. {tool_res}. Now respond to the child Socraticly."]
                    )
                    reply_text = followup.text
                else:
                    reply_text = response.text

                st.write(reply_text)
                st.session_state.messages.append({"role": "assistant", "content": reply_text})
                st.rerun()

            except Exception as e:
                st.error(f"Error communicating with the Primer: {e}")