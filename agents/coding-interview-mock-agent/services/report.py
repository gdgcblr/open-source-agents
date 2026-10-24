"""
Interview Report Generator Service.

Synthesizes InterviewSession and EvaluationResult into a comprehensive
Google Software Engineering Hiring Committee Report.
"""

from __future__ import annotations
from typing import List, Dict, Any
from datetime import datetime
from models.schemas import (
    InterviewSession,
    EvaluationResult,
    InterviewReport,
    HiringRecommendation
)


class ReportService:
    """
    Generates structured and Markdown-formatted Google SWE Interview Reports.
    """

    def generate_report(self, session: InterviewSession) -> InterviewReport:
        """
        Generate complete InterviewReport for a session.
        """
        eval_res = session.evaluation
        if not eval_res:
            from services.evaluator import evaluator_service
            eval_res = evaluator_service.evaluate_session(session)
            session.evaluation = eval_res

        overall = eval_res.overall_score
        recommendation = self._determine_hiring_recommendation(overall)

        strengths = self._derive_strengths(eval_res, session)
        weaknesses = self._derive_weaknesses(eval_res, session)
        recommended_topics = self._suggest_topics(session, eval_res)

        rubric_breakdown = {
            "Communication": eval_res.communication_score,
            "Problem Solving": eval_res.problem_solving_score,
            "Code Quality": eval_res.code_quality_score,
            "Complexity Analysis": eval_res.complexity_analysis_score,
            "Edge Cases": eval_res.edge_cases_score,
            "Optimization": eval_res.optimization_score,
        }

        # Calculate rough duration if timestamps available
        duration_sec = 1800  # Default ~30 mins mock session
        try:
            start_dt = datetime.fromisoformat(session.created_at)
            end_dt = datetime.fromisoformat(session.updated_at)
            duration_sec = max(int((end_dt - start_dt).total_seconds()), 60)
        except Exception:
            pass

        question_title = session.question.title if session.question else "Unknown DSA Question"
        question_topic = session.question.topic if session.question else "General DSA"

        detailed_feedback = eval_res.feedback_summary
        code_notes = f"Time Complexity: {eval_res.time_complexity} | Space Complexity: {eval_res.space_complexity}"

        # Build Markdown report
        markdown_text = self._build_markdown_report(
            candidate_name=session.candidate_name,
            session_id=session.session_id,
            question_title=question_title,
            question_topic=question_topic,
            difficulty=session.difficulty.value,
            overall_score=overall,
            recommendation=recommendation,
            rubric_breakdown=rubric_breakdown,
            strengths=strengths,
            weaknesses=weaknesses,
            recommended_topics=recommended_topics,
            eval_res=eval_res
        )

        report = InterviewReport(
            session_id=session.session_id,
            candidate_name=session.candidate_name,
            difficulty=session.difficulty,
            question_title=question_title,
            question_topic=question_topic,
            duration_seconds=duration_sec,
            interview_score=overall,
            hiring_recommendation=recommendation,
            strengths=strengths,
            weaknesses=weaknesses,
            recommended_topics=recommended_topics,
            rubric_breakdown=rubric_breakdown,
            detailed_feedback=detailed_feedback,
            code_review_notes=code_notes,
            markdown_report=markdown_text
        )

        session.report = report
        return report

    def _determine_hiring_recommendation(self, score: float) -> HiringRecommendation:
        if score >= 8.5:
            return HiringRecommendation.STRONG_HIRE
        elif score >= 7.0:
            return HiringRecommendation.HIRE
        elif score >= 5.5:
            return HiringRecommendation.LEANING_HIRE
        elif score >= 4.0:
            return HiringRecommendation.LEANING_NO_HIRE
        else:
            return HiringRecommendation.NO_HIRE

    def _derive_strengths(self, eval_res: EvaluationResult, session: InterviewSession) -> List[str]:
        strengths: List[str] = []
        if eval_res.communication_score >= 8:
            strengths.append("Proactive and articulate communication; consistently thought aloud during problem breakdown.")
        if eval_res.problem_solving_score >= 8:
            strengths.append("Strong algorithmic intuition and clear logical problem decomposition.")
        if eval_res.optimization_score >= 8:
            strengths.append("Successfully transitioned from baseline brute-force to an optimal algorithmic approach.")
        if eval_res.code_quality_score >= 8:
            strengths.append("Clean, readable, and idiomatic code structure with descriptive naming.")
        if eval_res.edge_cases_score >= 8:
            strengths.append("Thorough coverage of edge cases, boundary values, and constraint validation.")

        if not strengths:
            strengths.append("Demonstrated fundamental understanding of core data structures.")
            strengths.append("Collaborative attitude and receptive to interviewer feedback.")

        return strengths

    def _derive_weaknesses(self, eval_res: EvaluationResult, session: InterviewSession) -> List[str]:
        weaknesses: List[str] = []
        if eval_res.edge_cases_score < 7:
            weaknesses.append("Overlooked several critical corner cases (e.g., empty collection, single item, integer bounds).")
        if eval_res.complexity_analysis_score < 7:
            weaknesses.append("Initial time and space complexity estimates were incomplete or imprecise.")
        if eval_res.code_quality_score < 7:
            weaknesses.append("Code could be improved with better modularity, separation of concerns, and variable naming.")
        if eval_res.communication_score < 7:
            weaknesses.append("Could ask more clarifying questions before diving directly into coding.")
        if eval_res.optimization_score < 7:
            weaknesses.append("Could explore further asymptotic improvements before committing to the final implementation.")

        if not weaknesses:
            weaknesses.append("Minor polish needed on handling ultra-large scale edge cases.")

        return weaknesses

    def _suggest_topics(self, session: InterviewSession, eval_res: EvaluationResult) -> List[str]:
        pool = [
            "Dynamic Programming (State Transitions & Memoization)",
            "Graph Traversal (BFS / DFS & Cycle Detection)",
            "Two Pointers & Sliding Window Patterns",
            "Monotonic Queue / Stack Optimization",
            "Trie and Prefix Search",
            "Heap / Priority Queue Patterns",
            "Amortized Complexity & Asymptotic Analysis"
        ]

        # Prioritize based on current question topic
        topic = session.question.topic if session.question else ""
        suggestions: List[str] = []
        for item in pool:
            if topic.lower() not in item.lower():
                suggestions.append(item)
            if len(suggestions) >= 3:
                break
        return suggestions

    def _build_markdown_report(
        self,
        candidate_name: str,
        session_id: str,
        question_title: str,
        question_topic: str,
        difficulty: str,
        overall_score: float,
        recommendation: HiringRecommendation,
        rubric_breakdown: Dict[str, int],
        strengths: List[str],
        weaknesses: List[str],
        recommended_topics: List[str],
        eval_res: EvaluationResult
    ) -> str:
        """Render clean, GitHub Flavored Markdown report."""
        badge_emoji = {
            HiringRecommendation.STRONG_HIRE: "🟢 **STRONG HIRE**",
            HiringRecommendation.HIRE: "🟢 **HIRE**",
            HiringRecommendation.LEANING_HIRE: "🟡 **LEANING HIRE**",
            HiringRecommendation.LEANING_NO_HIRE: "🟠 **LEANING NO HIRE**",
            HiringRecommendation.NO_HIRE: "🔴 **NO HIRE**"
        }.get(recommendation, str(recommendation.value))

        rubric_table = "| Competency | Score (out of 10) | Evaluation Rating |\n| :--- | :---: | :--- |\n"
        for comp, sc in rubric_breakdown.items():
            rating = "Exceptional" if sc >= 9 else "Good" if sc >= 7 else "Acceptable" if sc >= 5 else "Needs Work"
            rubric_table += f"| {comp} | **{sc}/10** | {rating} |\n"

        strengths_md = "\n".join([f"- ✅ {s}" for s in strengths])
        weaknesses_md = "\n".join([f"- ⚠️ {w}" for w in weaknesses])
        topics_md = "\n".join([f"- 📚 {t}" for t in recommended_topics])

        return f"""# 🏛️ Google SWE Coding Interview Feedback Report

**Candidate:** {candidate_name}  
**Session ID:** `{session_id}`  
**Question:** {question_title} ({question_topic} - {difficulty.capitalize()})  

---

## 🎯 Overall Interview Score: {overall_score} / 10
### Hiring Recommendation: {badge_emoji}

---

## 📊 Rubric Evaluation Breakdown
{rubric_table}

---

## ⏱️ Complexity & Technical Assessment
- **Time Complexity:** `{eval_res.time_complexity}`
- **Space Complexity:** `{eval_res.space_complexity}`
- **Correctness:** {eval_res.correctness_assessment}

---

## 💪 Key Strengths
{strengths_md}

## 🔍 Areas for Growth
{weaknesses_md}

## 🎯 Recommended Practice Topics
{topics_md}

---
*Generated by Google Coding Interview Mock Agent*
"""


# Singleton instance
report_service = ReportService()

