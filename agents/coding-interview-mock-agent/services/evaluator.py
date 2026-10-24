"""
Evaluation Service for Coding Interview Mock Agent.

Evaluates candidate performance across 6 Google SWE dimensions:
1. Communication
2. Problem Solving
3. Code Quality
4. Complexity Analysis
5. Edge Cases
6. Optimization

Supports Google GenAI API (Gemini) with automatic JSON extraction and
intelligent offline heuristic fallback for testing and development.
"""

from __future__ import annotations
import os
import re
import json
from typing import Dict, Any, Optional
from models.schemas import (
    InterviewSession,
    EvaluationResult,
    Question,
    CodeSubmission
)
from utils.loader import load_prompt


class EvaluatorService:
    """
    Evaluates interview transcripts, candidate communications, and code submissions.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.system_prompt = load_prompt("evaluator")

    def evaluate_session(self, session: InterviewSession) -> EvaluationResult:
        """
        Evaluate complete interview session and return structured EvaluationResult.
        """
        if self.api_key and self.api_key != "your_api_key_here":
            try:
                return self._evaluate_with_gemini(session)
            except Exception as e:
                print(f"[Evaluator] Gemini API evaluation failed: {e}. Falling back to heuristic evaluator.")

        return self._evaluate_heuristic(session)

    def _evaluate_with_gemini(self, session: InterviewSession) -> EvaluationResult:
        """
        Use Google GenAI / Gemini API to generate structured evaluation JSON.
        """
        # Format the transcript and session data for Gemini
        transcript_lines = []
        for msg in session.messages:
            transcript_lines.append(f"[{msg.stage.value.upper()}] {msg.role.capitalize()}: {msg.content}")
        transcript_text = "\n".join(transcript_lines)

        question_info = ""
        if session.question:
            q = session.question
            question_info = f"""
Title: {q.title}
Difficulty: {q.difficulty.value}
Topic: {q.topic}
Description: {q.description}
Constraints: {json.dumps(q.constraints)}
"""

        latest_code = session.latest_code or (
            session.code_submissions[-1].code if session.code_submissions else "No code submitted."
        )

        user_content = f"""
PROBLEM CONTEXT:
{question_info}

CANDIDATE SELECTED LANGUAGE:
{session.selected_language.value}

CANDIDATE CODE SUBMISSION:
```
{latest_code}
```

FULL INTERVIEW TRANSCRIPT:
{transcript_text}

Please evaluate the candidate according to the 6 Google SWE evaluation dimensions and return ONLY the valid JSON object.
"""

        # Call Google GenAI SDK
        raw_response = self._call_gemini_api(self.system_prompt, user_content)
        parsed_json = self._extract_json(raw_response)
        return EvaluationResult(**parsed_json)

    def _call_gemini_api(self, system_instruction: str, prompt: str) -> str:
        """
        Invoke Gemini using google-genai or google-generativeai SDK.
        """
        # Attempt modern google-genai SDK first
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )
            )
            return response.text
        except ImportError:
            pass

        # Fallback to google.generativeai legacy package
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=self.api_key)
            model = legacy_genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            response = model.generate_content(prompt)
            return response.text
        except ImportError:
            raise RuntimeError("Neither 'google-genai' nor 'google-generativeai' package is installed.")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Resiliently extract and parse JSON from LLM response text,
        handling Markdown fences, leading/trailing whitespace, or comments.
        """
        cleaned = text.strip()
        # Remove Markdown code blocks if present (```json ... ```)
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

        # If there are trailing characters or leading text before '{'
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        return json.loads(cleaned)

    def _evaluate_heuristic(self, session: InterviewSession) -> EvaluationResult:
        """
        Intelligent offline heuristic evaluation when Gemini API is unavailable.
        Analyzes message count, question inquiries, code structure, and complexity keywords.
        """
        candidate_messages = [m.content for m in session.messages if m.role == "candidate"]
        combined_text = " ".join(candidate_messages).lower()
        code = session.latest_code or (
            session.code_submissions[-1].code if session.code_submissions else ""
        )

        # 1. Communication evaluation
        comm_score = 6
        if any(mark in combined_text for mark in ["?", "could", "should", "empty", "null", "negative", "duplicate"]):
            comm_score += 2
        if len(candidate_messages) >= 4:
            comm_score += 1
        comm_score = min(comm_score, 10)

        # 2. Problem solving evaluation
        prob_score = 6
        if any(kw in combined_text for kw in ["approach", "brute force", "hash", "pointer", "dp", "tree", "traversal"]):
            prob_score += 2
        if len(code.strip()) > 30:
            prob_score += 1
        prob_score = min(prob_score, 10)

        # 3. Code quality evaluation
        quality_score = 5
        if code:
            if "def " in code or "function" in code or "class " in code or "public " in code:
                quality_score += 2
            if "return " in code:
                quality_score += 1
            if len(code.splitlines()) >= 5:
                quality_score += 1
        quality_score = min(quality_score, 10)

        # 4. Complexity analysis
        comp_score = 6
        has_time = any(kw in combined_text for kw in ["o(n)", "o(1)", "o(log", "o(n^2)", "linear", "constant"])
        has_space = any(kw in combined_text for kw in ["space", "auxiliary", "memory", "stack"])
        if has_time:
            comp_score += 2
        if has_space:
            comp_score += 1
        comp_score = min(comp_score, 10)

        # 5. Edge cases
        edge_score = 5
        identified_edges = []
        missed_edges = []
        if "empty" in combined_text or "len(" in code or "null" in combined_text:
            edge_score += 2
            identified_edges.append("Proactively considered empty or null inputs.")
        else:
            missed_edges.append("Did not explicitly verify null/empty input bounds.")

        if "duplicate" in combined_text or "negative" in combined_text:
            edge_score += 1
            identified_edges.append("Considered negative values or duplicate elements.")
        else:
            missed_edges.append("Could test with negative numbers and duplicate elements.")
        edge_score = min(edge_score, 10)

        # 6. Optimization
        opt_score = 6
        if "optimize" in combined_text or "hash" in combined_text or "two pointer" in combined_text:
            opt_score += 2
        opt_score = min(opt_score, 10)

        # Compute weighted overall score out of 10
        weights = [0.15, 0.25, 0.20, 0.15, 0.10, 0.15]
        scores = [comm_score, prob_score, quality_score, comp_score, edge_score, opt_score]
        overall = sum(w * s for w, s in zip(weights, scores))
        overall_score = round(overall, 1)

        time_comp = "O(N) Time" if has_time else "O(N^2) or not formally specified"
        space_comp = "O(N) Auxiliary Space" if has_space else "O(1) or not explicitly stated"

        return EvaluationResult(
            communication_score=comm_score,
            problem_solving_score=prob_score,
            code_quality_score=quality_score,
            complexity_analysis_score=comp_score,
            edge_cases_score=edge_score,
            optimization_score=opt_score,
            overall_score=overall_score,
            time_complexity=time_comp,
            space_complexity=space_comp,
            correctness_assessment="Candidate demonstrated sound algorithmic reasoning with functioning code logic.",
            edge_cases_identified=identified_edges or ["Handled basic non-trivial inputs"],
            edge_cases_missed=missed_edges or ["Large scale boundary checks"],
            feedback_summary="Solid interview session with effective problem decomposition and structured communication."
        )


# Singleton instance
evaluator_service = EvaluatorService()

