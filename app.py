import streamlit as st
import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from jury import evaluate_turn

# Load API keys from .env
load_dotenv()

st.set_page_config(
    page_title="The Illustrated Primer",
    page_icon="📖",
    layout="wide"
)

# Custom Storybook Styling
# Custom Storybook Styling with forced dark text & message card backgrounds
st.markdown("""
<style>
    .stApp { 
        background-color: #fcfbf7; 
        color: #1a1615 !important; 
        font-family: 'Georgia', serif; 
    }
    
    /* Force all chat message bubbles and text to be clearly visible */
    [data-testid="stChatMessage"] {
        background-color: #f3efe6 !important;
        border: 1px solid #e2dacd !important;
        border-radius: 12px !important;
        padding: 12px !important;
        margin-bottom: 12px !important;
    }

    [data-testid="stChatMessage"] * {
        color: #1a1615 !important;
    }
    
    /* Ensure markdown and paragraph text in the main canvas are dark */
    .stMarkdown, p, span, li, label {
        color: #1a1615 !important;
    }

    /* Headings */
    h1, h2, h3, h4 { 
        font-family: 'Georgia', serif; 
        color: #2b1f1d !important; 
    }

    /* Preserve clean dark styling in the sidebar */
    [data-testid="stSidebar"] {
        background-color: #1a1c23 !important;
    }
    [data-testid="stSidebar"] * {
        color: #f0f0f0 !important;
    }
</style>
""", unsafe_allow_html=True)

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

def get_or_create_profile() -> dict:
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w") as f:
            json.dump(DEFAULT_STATE, f, indent=2)
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_profile(profile_data: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(profile_data, f, indent=2)

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
    return f"Updated ledger for '{skill}'. Active struggles: {curr['struggles']}. Mastered: {curr['mastered']}"

# Initialize profile
profile = get_or_create_profile()

# ----------------- SIDEBAR: MEMORY & JURY SCORECARD -----------------
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
        
    st.caption(f"**Audit Note:** {profile.get('last_observation', 'None')}")

    # --- Socratic Jury Scorecard ---
    st.divider()
    st.subheader("⚖️ Socratic Jury Scorecard")
    st.caption("Real-Time Pedagogical Alignment & Audit")

    if "latest_audit" in st.session_state and st.session_state.latest_audit:
        audit = st.session_state.latest_audit
        s_score = audit.get("socratic_score", 5)
        w_score = audit.get("warmth_score", 5)

        col1, col2 = st.columns(2)
        col1.metric("Socratic Rigor", f"{s_score}/5", delta="Guided" if s_score >= 4 else "Direct")
        col2.metric("Warmth", f"{w_score}/5", delta="Gentle" if w_score >= 4 else "Cool")

        st.write(f"**Scaffolding Quality:** `{audit.get('scaffolding_level', 'High')}`")
        
        if audit.get("mastery_detected"):
            st.success("🎯 Mastery Detected by Jury!")

        st.info(f"💡 **Jury Rationale:**\n{audit.get('feedback', 'No notes.')}")
    else:
        st.caption("Awaiting child's first question to audit...")

# ----------------- MAIN BOOK CHAT INTERFACE -----------------
st.title("📖 A Young Lady's Illustrated Primer")
st.caption("“It continually reshaped itself around who she was becoming.” — The Diamond Age")

# Initialize Gemini Client
client = genai.Client()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Welcome back, Nell. The Clockwork Valley is quiet today, but the forest gears are turning. What shall we explore together?"
        }
    ]

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# User Chat Input
if user_prompt := st.chat_input("Speak to the Primer..."):
    # 1. Render user message
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.write(user_prompt)

    # 2. Generate response from the Primer
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
            
            Core Directives:
            1. Never give answers directly to math, phonics, or logic problems.
            2. Guide the child using sensory metaphors, interactive storytelling, and breakdown questions.
            3. If the child gets an answer right or demonstrates mastery, call `update_learning_ledger`.
            4. Keep the tone warm, literary, patient, and curious.
            """

            # Build chat history for context
            contents = [m["content"] for m in st.session_state.messages]

            try:
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[update_learning_ledger]
                    )
                )

                reply_text = ""
                # Handle autonomous tool calling
                if response.function_calls:
                    tool_res_msg = ""
                    for call in response.function_calls:
                        args = call.args
                        tool_res_msg = update_learning_ledger(
                            skill=args.get("skill", ""),
                            success=args.get("success", False),
                            note=args.get("note", "")
                        )
                    
                    # Generate natural final response acknowledging the result
                    followup = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=contents + [f"System: Tool execution completed. {tool_res_msg}. Now respond to the child Socraticly."]
                    )
                    reply_text = followup.text
                else:
                    reply_text = response.text

                st.write(reply_text)
                st.session_state.messages.append({"role": "assistant", "content": reply_text})

            except Exception as e:
                reply_text = f"The pages fluttered: {e}"
                st.error(reply_text)
                st.session_state.messages.append({"role": "assistant", "content": reply_text})

    # 3. Asynchronous LLM-as-a-Jury Evaluation
    with st.spinner("Jury evaluating pedagogy & alignment..."):
        st.session_state.latest_audit = evaluate_turn(user_prompt, reply_text)

    # 4. Rerun to dynamically refresh the sidebar state and scorecard
    st.rerun()