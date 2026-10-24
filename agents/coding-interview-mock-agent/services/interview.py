"""
Interview Management Engine and Orchestration Service.

Manages:
- Interview session lifecycle across all 7 Google SWE interview stages
- Question selection by difficulty and topic
- Dynamic constraint discovery
- Multi-turn conversation tracking with Google interviewer persona
- Code submission tracking
- Session persistence (JSON storage)
"""

from __future__ import annotations
import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from models.schemas import (
    DifficultyLevel,
    InterviewStage,
    ProgrammingLanguage,
    Question,
    ChatMessage,
    CodeSubmission,
    InterviewSession,
    ChatMessageResponse
)
from utils.loader import (
    get_random_question,
    get_question_by_id,
    load_prompt
)


SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class InterviewEngine:
    """
    Engine to orchestrate an authentic Google Software Engineering interview.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.interviewer_prompt = load_prompt("interviewer")
        self.followup_prompt = load_prompt("followup")
        self.sessions: Dict[str, InterviewSession] = {}
        self._load_persisted_sessions()

    # -----------------------------------------------------------------
    # Session Management
    # -----------------------------------------------------------------

    def start_interview(
        self,
        candidate_name: str = "Candidate",
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        topic: Optional[str] = None,
        language: ProgrammingLanguage = ProgrammingLanguage.PYTHON
    ) -> InterviewSession:
        """
        Initialize a new interview session and start Stage 1 (Intro).
        """
        session_id = str(uuid.uuid4())
        question = get_random_question(difficulty=difficulty, topic=topic)
        now_iso = datetime.now().isoformat()

        session = InterviewSession(
            session_id=session_id,
            candidate_name=candidate_name,
            difficulty=difficulty,
            topic=topic or question.topic,
            current_stage=InterviewStage.INTRO,
            question=question,
            revealed_constraints=[],
            messages=[],
            code_submissions=[],
            latest_code=self._get_default_starter_code(question, language),
            selected_language=language,
            created_at=now_iso,
            updated_at=now_iso
        )

        # Stage 1 Introduction message
        intro_content = (
            f"Hi {candidate_name}, welcome to today's Google coding interview! "
            f"I will give you a problem and evaluate your approach. "
            f"Over the next 45 minutes, we'll collaborate on a coding problem. "
            f"I'm especially interested in how you think and communicate, so please think aloud. "
            f"Feel free to ask clarification questions before coding.\n\n"
            f"Whenever you are ready, let me know and we will get started with the problem!"
        )

        intro_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="interviewer",
            content=intro_content,
            timestamp=datetime.now().isoformat(),
            stage=InterviewStage.INTRO
        )
        session.messages.append(intro_msg)

        self.sessions[session_id] = session
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        """Fetch session from memory or disk."""
        if session_id in self.sessions:
            return self.sessions[session_id]

        file_path = SESSIONS_DIR / f"{session_id}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    session = InterviewSession(**data)
                    self.sessions[session_id] = session
                    return session
            except Exception as e:
                print(f"[InterviewEngine] Failed to restore session {session_id}: {e}")
        return None

    def save_session(self, session: InterviewSession) -> None:
        """Persist session state to JSON file."""
        session.updated_at = datetime.now().isoformat()
        file_path = SESSIONS_DIR / f"{session.session_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(session.model_dump_json(indent=2))
        except Exception as e:
            print(f"[InterviewEngine] Error saving session to disk: {e}")

    def _load_persisted_sessions(self) -> None:
        """Load any existing session files on startup."""
        for file in SESSIONS_DIR.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sess = InterviewSession(**data)
                    self.sessions[sess.session_id] = sess
            except Exception:
                pass

    # -----------------------------------------------------------------
    # Dialogue & Stage Progression
    # -----------------------------------------------------------------

    def process_candidate_message(self, session_id: str, candidate_text: str) -> ChatMessageResponse:
        """
        Process incoming candidate message, update interview state machine,
        and generate interviewer response.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session with ID '{session_id}' not found.")

        # Record candidate message
        c_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="candidate",
            content=candidate_text,
            timestamp=datetime.now().isoformat(),
            stage=session.current_stage
        )
        session.messages.append(c_msg)

        # Check for constraint disclosures
        newly_revealed = self._check_constraint_queries(session, candidate_text)

        # Determine stage transitions
        prev_stage = session.current_stage
        next_stage = self._determine_stage_transition(session, candidate_text)
        stage_changed = (next_stage != prev_stage)
        if stage_changed:
            session.current_stage = next_stage

        # Generate response from Gemini API or fallback interviewer logic
        response_text = self._generate_interviewer_response(session, candidate_text, newly_revealed)

        # Record interviewer message
        i_msg = ChatMessage(
            id=str(uuid.uuid4()),
            role="interviewer",
            content=response_text,
            timestamp=datetime.now().isoformat(),
            stage=session.current_stage
        )
        session.messages.append(i_msg)

        self.save_session(session)

        return ChatMessageResponse(
            response=response_text,
            stage=session.current_stage,
            stage_changed=stage_changed,
            revealed_constraints=session.revealed_constraints
        )

    def advance_stage(self, session_id: str, target_stage: Optional[InterviewStage] = None) -> InterviewSession:
        """Manually or programmatically advance to the next interview stage."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        stage_order = [
            InterviewStage.INTRO,
            InterviewStage.PROBLEM,
            InterviewStage.DISCUSSION,
            InterviewStage.CODING,
            InterviewStage.REVIEW,
            InterviewStage.FOLLOWUP,
            InterviewStage.FEEDBACK,
            InterviewStage.COMPLETED
        ]

        if target_stage:
            session.current_stage = target_stage
        else:
            curr_idx = stage_order.index(session.current_stage)
            if curr_idx < len(stage_order) - 1:
                session.current_stage = stage_order[curr_idx + 1]

        prompt_stage_msg = self._stage_transition_message(session)
        if prompt_stage_msg:
            msg = ChatMessage(
                id=str(uuid.uuid4()),
                role="interviewer",
                content=prompt_stage_msg,
                timestamp=datetime.now().isoformat(),
                stage=session.current_stage
            )
            session.messages.append(msg)

        self.save_session(session)
        return session

    def submit_code(
        self,
        session_id: str,
        code: str,
        language: ProgrammingLanguage = ProgrammingLanguage.PYTHON
    ) -> ChatMessageResponse:
        """
        Handle candidate code submission and advance to review stage.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        submission = CodeSubmission(
            language=language,
            code=code,
            submitted_at=datetime.now().isoformat()
        )
        session.code_submissions.append(submission)
        session.latest_code = code
        session.selected_language = language

        # Automatically advance to REVIEW stage if in CODING stage
        if session.current_stage in [InterviewStage.CODING, InterviewStage.DISCUSSION]:
            session.current_stage = InterviewStage.REVIEW

        return self.process_candidate_message(session_id, "I have submitted my code solution. Let's review it.")

    # -----------------------------------------------------------------
    # Helper & Persona Logic
    # -----------------------------------------------------------------

    def _check_constraint_queries(self, session: InterviewSession, text: str) -> List[str]:
        """
        Detect if candidate is asking about constraints (empty, null, negative, bounds, duplicates)
        and reveal matching constraints from question specification.
        """
        if not session.question:
            return []

        lower = text.lower()
        newly_revealed: List[str] = []

        keywords_map = {
            "empty": ["empty", "0", "null", "none"],
            "negative": ["negative", "below zero", "< 0"],
            "duplicate": ["duplicate", "repeated", "same element"],
            "size": ["size", "length", "bound", "maximum", "how big"],
            "sort": ["sorted", "order"],
        }

        for constraint in session.question.constraints:
            if constraint in session.revealed_constraints:
                continue
            c_lower = constraint.lower()
            for key, kws in keywords_map.items():
                if any(kw in lower for kw in kws) and any(kw in c_lower for kw in kws):
                    session.revealed_constraints.append(constraint)
                    newly_revealed.append(constraint)
                    break

        return newly_revealed

    def _determine_stage_transition(self, session: InterviewSession, text: str) -> InterviewStage:
        """Heuristically advance stages based on candidate cues."""
        stage = session.current_stage
        lower = text.lower()

        # Intro -> Problem
        if stage == InterviewStage.INTRO:
            if any(cue in lower for cue in ["ready", "start", "let's go", "yes", "sure", "begin"]):
                return InterviewStage.PROBLEM

        # Problem -> Discussion
        elif stage == InterviewStage.PROBLEM:
            if any(cue in lower for cue in ["approach", "brute force", "thinking", "solve", "hash map", "two pointer", "algorithm"]):
                return InterviewStage.DISCUSSION

        # Discussion -> Coding
        elif stage == InterviewStage.DISCUSSION:
            if any(cue in lower for cue in ["can i code", "ready to code", "start coding", "implement", "write code"]):
                return InterviewStage.CODING

        return stage

    def _stage_transition_message(self, session: InterviewSession) -> Optional[str]:
        """Generate transition greeting when stage changes."""
        q = session.question
        if not q:
            return None

        if session.current_stage == InterviewStage.PROBLEM:
            example_str = ""
            if q.examples:
                ex = q.examples[0]
                example_str = f"\n\nExample 1:\nInput: {ex.input}\nOutput: {ex.output}\nExplanation: {ex.explanation or 'Standard output.'}"

            return (
                f"Great! Here is the problem:\n\n"
                f"### {q.title}\n"
                f"{q.description}"
                f"{example_str}\n\n"
                f"Before writing code, feel free to ask any clarifying questions about the inputs, constraints, or expected behavior!"
            )

        elif session.current_stage == InterviewStage.DISCUSSION:
            return (
                "Excellent clarification questions! Now, let's talk about your approach. "
                "How would you break this problem down? Do you have an initial brute-force idea, and can we optimize it?"
            )

        elif session.current_stage == InterviewStage.CODING:
            return (
                "Your approach sounds well thought out! Please go ahead and write your solution in the code editor. "
                "Focus on clean variable naming, modular structure, and handling boundary conditions. Think aloud as you type!"
            )

        elif session.current_stage == InterviewStage.REVIEW:
            return (
                "Thanks for writing that out! Let's walk through your solution step by step. "
                "How does this code handle edge cases (e.g. empty inputs or extreme values)? "
                "Also, what are the final Big-O Time and Space complexities?"
            )

        elif session.current_stage == InterviewStage.FOLLOWUP:
            followup_q = q.followups[0] if q.followups else "How would your approach scale if input size increased by a factor of 100,000?"
            return (
                f"Great work discussing the implementation. Let's move to a follow-up question:\n\n"
                f"💡 **Google Follow-up:**\n{followup_q}\n\n"
                f"How would you address this in a production system?"
            )

        elif session.current_stage == InterviewStage.FEEDBACK:
            return (
                "Thank you for working through this interview with me! That concludes the technical portion. "
                "I am now consolidating my feedback and compiling your Google SWE Interview Report..."
            )

        return None

    def _generate_interviewer_response(
        self,
        session: InterviewSession,
        candidate_text: str,
        newly_revealed: List[str]
    ) -> str:
        """
        Call Gemini or run fallback interviewer response.
        """
        if self.api_key and self.api_key != "your_api_key_here":
            try:
                return self._call_gemini_interviewer(session, candidate_text)
            except Exception as e:
                print(f"[InterviewEngine] Gemini API call failed: {e}. Using intelligent fallback.")

        return self._generate_fallback_response(session, candidate_text, newly_revealed)

    def _call_gemini_interviewer(self, session: InterviewSession, candidate_text: str) -> str:
        """Invoke Gemini API with Google Interviewer Persona."""
        q = session.question
        stage = session.current_stage.value

        context = f"""
ROLE: Google Software Engineer Interviewer
CURRENT STAGE: {stage.upper()}
PROBLEM: {q.title if q else 'Unknown'}
TOPIC: {q.topic if q else 'General'}
KNOWN CONSTRAINTS: {json.dumps(q.constraints if q else [])}
REVEALED CONSTRAINTS SO FAR: {json.dumps(session.revealed_constraints)}
CANDIDATE SELECTED LANGUAGE: {session.selected_language.value}
LATEST CODE:
{session.latest_code or 'No code yet'}

Remember:
- Be encouraging, professional, and authentic to a Google SWE interview.
- Do NOT give away full answers. Use Socratic questions.
- If in STAGE 2 (Problem), answer questions about constraints naturally.
- If in STAGE 3 (Discussion), evaluate approach and ask for Time/Space complexity.
- If in STAGE 5 (Review), ask candidate to trace edge cases and verify complexity.
"""
        # Format recent history
        recent_msgs = session.messages[-6:]
        conversation_history = "\n".join([f"{m.role}: {m.content}" for m in recent_msgs])

        user_prompt = f"{context}\n\nCONVERSATION HISTORY:\n{conversation_history}\n\nGenerate your next response as the Google interviewer:"

        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key)
            resp = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.interviewer_prompt,
                    temperature=0.7,
                )
            )
            return resp.text.strip()
        except ImportError:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=self.api_key)
            model = legacy_genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=self.interviewer_prompt
            )
            resp = model.generate_content(user_prompt)
            return resp.text.strip()

    def _generate_fallback_response(
        self,
        session: InterviewSession,
        candidate_text: str,
        newly_revealed: List[str]
    ) -> str:
        """
        High quality, authentic Google interviewer simulated responses
        for offline testing and development.
        """
        stage = session.current_stage
        q = session.question

        if stage == InterviewStage.INTRO:
            return (
                "Glad to have you here! Whenever you are ready, just say 'ready' or 'let's start', "
                "and I will share the problem description."
            )

        if stage == InterviewStage.PROBLEM:
            revealed_text = ""
            if newly_revealed:
                revealed_text = "\n\nRegarding your question: " + " ".join(newly_revealed)

            return (
                f"That's a very good question to ask before jumping into an implementation!{revealed_text}\n\n"
                f"How are you thinking about approaching the solution at a high level? "
                f"Feel free to discuss a naive brute-force first, and then we can explore how to optimize it."
            )

        if stage == InterviewStage.DISCUSSION:
            lower = candidate_text.lower()
            if "o(n^2)" in lower or "nested loop" in lower or "brute" in lower:
                return (
                    "A brute force approach is a great starting baseline! That gives us a correctness reference. "
                    "Now, where is the main bottleneck in that approach? Can we trade a bit of space (like using a hash table or pointers) "
                    "to bring the runtime down to O(N) or O(N log N)?"
                )
            return (
                "That sounds like a very promising direction! What would be the expected Time Complexity "
                "and Auxiliary Space Complexity for that approach? Once you're comfortable, feel free to start coding."
            )

        if stage == InterviewStage.CODING:
            return (
                "The structure looks good so far. As you write the implementation, please keep thinking aloud. "
                "Pay special attention to pointer boundaries, empty input cases, and loop termination conditions."
            )

        if stage == InterviewStage.REVIEW:
            return (
                "Great walkthrough! Let's double check corner cases. How does this implementation behave "
                "if the input has length 0 or 1, or if all elements are identical? "
                "Could you walk me through the line-by-line execution for that scenario?"
            )

        if stage == InterviewStage.FOLLOWUP:
            followup = q.followups[0] if q and q.followups else "How would you scale this to a 100GB dataset that cannot fit into RAM?"
            return (
                f"Good insight on the complexity! Here is a classic Google follow-up:\n\n"
                f"👉 **{followup}**\n\n"
                f"What trade-offs or architecture changes would you make to solve this?"
            )

        if stage == InterviewStage.FEEDBACK:
            return (
                "Thank you for sharing your thoughts! We have wrapped up the coding portion. "
                "You can now click 'Finish Interview' or view the complete hiring report."
            )

        return "I see. Let's keep exploring this approach. What do you think the next step should be?"

    def _get_default_starter_code(self, question: Question, language: ProgrammingLanguage) -> str:
        """Provide clean starter boilerplate for the candidate's editor."""
        title_snake = question.title.lower().replace(" ", "_").replace("-", "_")

        if language == ProgrammingLanguage.PYTHON:
            return f'''class Solution:
    def {title_snake}(self, *args, **kwargs):
        """
        Problem: {question.title} ({question.topic} - {question.difficulty.value})
        Implement your solution below.
        """
        # TODO: Implement optimal solution
        pass


if __name__ == "__main__":
    solution = Solution()
    print("Solution initialized.")
'''
        elif language == ProgrammingLanguage.JAVASCRIPT:
            return f'''/**
 * Problem: {question.title} ({question.topic} - {question.difficulty.value})
 */
function {title_snake}() {{
    // TODO: Implement solution
}}

console.log("Ready to test {question.title}");
'''
        elif language == ProgrammingLanguage.CPP:
            return f'''#include <iostream>
#include <vector>
#include <string>
#include <unordered_map>
#include <algorithm>

using namespace std;

class Solution {{
public:
    // TODO: Implement solution for {question.title}
}};

int main() {{
    cout << "Ready to test {question.title}" << endl;
    return 0;
}}
'''
        elif language == ProgrammingLanguage.JAVA:
            return f'''import java.util.*;

public class Solution {{
    // Problem: {question.title} ({question.topic} - {question.difficulty.value})
    public static void main(String[] args) {{
        System.out.println("Ready to test {question.title}");
    }}
}}
'''
        return "# Write your solution here"


# Singleton instance
interview_engine = InterviewEngine()
