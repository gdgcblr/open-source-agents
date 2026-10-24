"""Enterprise core reasoning engine and ReAct execution loop with audit telemetry."""

import datetime
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .exceptions import InvalidTopicError
from .prompts import RESEARCH_SYSTEM_PROMPT, SYNTHESIS_PROMPT_TEMPLATE
from .mock_provider import MockLLMProvider
from .schema import ResearchMetrics
from .tools.search import search_web
from .tools.scraper import scrape_webpage
from .tools.reporter import save_markdown_report, save_research_artifacts

logger = logging.getLogger(__name__)


class ResearchAgent:
    """Enterprise-grade Autonomous Research Agent with telemetry, guardrails, and error recovery."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        max_steps: int = 5,
        mock_mode: bool = False,
        output_dir: str = "reports",
        step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.max_steps = max(1, min(int(max_steps or os.getenv("MAX_RESEARCH_STEPS", 5)), 15))
        self.output_dir = output_dir or os.getenv("OUTPUT_DIR", "reports")
        self.step_callback = step_callback

        # Determine if running in mock mode
        if mock_mode or not self.api_key or self.api_key == "your_gemini_api_key_here":
            self.mock_mode = True
            self.client = None
            logger.info("ResearchAgent initialized in MOCK mode (zero API key needed).")
        else:
            self.mock_mode = False
            self.client = self._init_gemini_client()
            logger.info(f"ResearchAgent initialized with live Gemini model: {self.model_name}")

    def _init_gemini_client(self):
        """Initializes the official Google GenAI or GenerativeAI client."""
        try:
            from google import genai
            return genai.Client(api_key=self.api_key)
        except ImportError:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=self.api_key)
                return legacy_genai.GenerativeModel(self.model_name)
            except ImportError:
                logger.warning("Neither 'google-genai' nor 'google-generativeai' is installed. Switching to MOCK mode.")
                self.mock_mode = True
                return None

    def _call_llm(self, prompt: str, mock_engine: Optional[MockLLMProvider], history: List[Dict[str, Any]]) -> str:
        """Invokes either the Mock engine or the live Gemini API with error boundaries."""
        if self.mock_mode or not self.client:
            return mock_engine.generate_step(history)

        try:
            if hasattr(self.client, "models"):
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                return response.text
            else:
                response = self.client.generate_content(prompt)
                return response.text
        except Exception as e:
            logger.error(f"Live Gemini API call failed: {e}. Falling back to mock engine for this step.")
            return mock_engine.generate_step(history)

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Strips markdown code blocks, cleans whitespace, and safely parses JSON."""
        if not text:
            raise ValueError("Empty response received from model.")

        cleaned = text.strip()
        # Remove markdown ```json ... ``` wrapper
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: extract outer JSON block using regex
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not parse valid JSON from model response: {cleaned[:200]}...")

    def run(self, topic: str) -> Dict[str, Any]:
        """Executes the full research loop on the given topic.

        Args:
            topic: The research subject, query, or problem statement.

        Returns:
            Dictionary containing final report, report path, execution metrics, and history.

        Raises:
            InvalidTopicError: If topic is empty or whitespace.
        """
        if not topic or not str(topic).strip():
            raise InvalidTopicError("Research topic cannot be empty.")

        clean_topic = str(topic).strip()
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.datetime.now()
        start_perf = time.perf_counter()

        logger.info(f"[{run_id}] Starting research run for topic: '{clean_topic}'")
        mock_engine = MockLLMProvider(topic=clean_topic)
        history: List[Dict[str, Any]] = []
        observations_log: List[str] = []

        searches_performed = 0
        pages_scraped = 0
        total_chars_analyzed = 0

        final_report = ""
        report_path = ""
        status = "completed"
        steps_taken = 0

        for step_idx in range(1, self.max_steps + 1):
            steps_taken = step_idx
            history_str = "\n".join([
                f"- [{h['role'].upper()}]: {json.dumps(h['content'])}" for h in history
            ])
            full_prompt = (
                f"{RESEARCH_SYSTEM_PROMPT}\n\n"
                f"Topic: \"{clean_topic}\"\n"
                f"Current Turn: {step_idx}/{self.max_steps}\n\n"
                f"History:\n{history_str or '(No actions taken yet. Start by planning and calling search_web.)'}\n\n"
                "Provide your next action in JSON format:"
            )

            raw_response = self._call_llm(full_prompt, mock_engine, history)

            try:
                parsed = self._clean_json_response(raw_response)
            except Exception as e:
                logger.warning(f"[{run_id}] Step {step_idx} parse error: {e}. Forcing synthesis.")
                parsed = {
                    "thought": "I encountered an unparseable response; synthesizing current observations.",
                    "action": "finish_research",
                    "action_input": {"final_report": f"# Research Summary: {clean_topic}\n\nSynthesized from {searches_performed} searches."}
                }

            thought = parsed.get("thought", "")
            action = parsed.get("action", "")
            action_input = parsed.get("action_input", {})

            # Dispatch progress callback
            step_record = {
                "run_id": run_id,
                "step": step_idx,
                "thought": thought,
                "action": action,
                "action_input": action_input,
                "mock_mode": self.mock_mode
            }
            if self.step_callback:
                try:
                    self.step_callback(step_record)
                except Exception as cb_err:
                    logger.warning(f"Step callback raised error: {cb_err}")

            history.append({"role": "assistant", "content": parsed})

            # Action: Web Search
            if action == "search_web":
                query = action_input.get("query", clean_topic)
                max_res = int(action_input.get("max_results", 3))
                results = search_web(query, max_results=max_res)
                searches_performed += 1
                history.append({"role": "observation", "content": results})
                observations_log.append(f"Search '{query}': Found {len(results)} items.")

                if self.step_callback:
                    try:
                        self.step_callback({"role": "observation", "content": results})
                    except Exception:
                        pass

            # Action: Scrape Webpage
            elif action == "scrape_webpage":
                url = action_input.get("url", "")
                max_chars = int(action_input.get("max_chars", 2500))
                scraped = scrape_webpage(url, max_chars=max_chars)
                pages_scraped += 1
                char_count = scraped.get("char_count", len(scraped.get("content", "")))
                total_chars_analyzed += char_count

                history.append({"role": "observation", "content": scraped})
                observations_log.append(f"Scraped '{url}': {scraped.get('title', '')} ({char_count} chars).")

                if self.step_callback:
                    try:
                        self.step_callback({"role": "observation", "content": scraped})
                    except Exception:
                        pass

            # Action: Finish Research
            elif action == "finish_research":
                final_report = action_input.get("final_report", "")
                break

        # If loop ended without explicit finish_research, auto-synthesize
        if not final_report:
            status = "completed_at_max_steps"
            logger.info(f"[{run_id}] Reached max steps limit ({self.max_steps}). Assembling final synthesis.")
            synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
                topic=clean_topic,
                observations="\n".join(observations_log)
            )
            synthesis_text = self._call_llm(synthesis_prompt, mock_engine, history)
            if isinstance(synthesis_text, str) and "finish_research" in synthesis_text:
                try:
                    parsed = self._clean_json_response(synthesis_text)
                    final_report = parsed.get("action_input", {}).get("final_report", synthesis_text)
                except Exception:
                    final_report = synthesis_text
            else:
                final_report = synthesis_text

        duration = round(time.perf_counter() - start_perf, 2)
        completed_at = datetime.datetime.now()

        metrics = ResearchMetrics(
            run_id=run_id,
            topic=clean_topic,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            steps_taken=steps_taken,
            searches_performed=searches_performed,
            pages_scraped=pages_scraped,
            total_chars_analyzed=total_chars_analyzed,
            mock_mode=self.mock_mode
        )

        artifacts = save_research_artifacts(
            topic=clean_topic,
            content=final_report,
            output_dir=self.output_dir,
            metrics=metrics.model_dump(),
            history=history,
        )

        return {
            "status": status,
            "topic": clean_topic,
            "final_report": final_report,
            "report_path": artifacts["markdown_path"],
            "html_path": artifacts["html_path"],
            "steps_taken": steps_taken,
            "mock_mode": self.mock_mode,
            "metrics": metrics.model_dump(),
            "history": history
        }
