from typing import Dict, Any, List
from adk_engine.agents.ingestion_agent import IngestionAgent
from adk_engine.agents.summarizer_agent import SummarizerAgent
from adk_engine.agents.action_extractor_agent import ActionExtractorAgent
from adk_engine.agents.scheduler_agent import SchedulerAgent
from adk_engine.agents.nudge_agent import NudgeAgent

class A2AOrchestrator:
    """
    Agent-to-Agent (A2A) Multi-Agent Orchestrator.
    Coordinates specialized agents in a decoupled, event-driven pipeline.
    """
    
    def __init__(self):
        self.ingestion_agent = IngestionAgent()
        self.summarizer_agent = SummarizerAgent()
        self.action_extractor_agent = ActionExtractorAgent()
        self.scheduler_agent = SchedulerAgent()
        self.nudge_agent = NudgeAgent()
        
    async def run_pipeline(
        self,
        meeting_id: str,
        meeting_title: str,
        raw_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes the full end-to-end A2A pipeline:
        1. Ingestion Agent cleans and normalizes transcript
        2. Summarizer Agent creates executive overview & decisions
        3. Action Extractor Agent identifies per-person action items
        4. Scheduler Agent evaluates deadlines for Calendar sync
        """
        # Step 1: Ingestion & Diarization
        clean_chunks = self.ingestion_agent.process_transcript(raw_chunks)
        formatted_transcript = self.ingestion_agent.format_for_llm(clean_chunks)
        
        # Step 2: Summarization (Gemma)
        summary = await self.summarizer_agent.summarize(meeting_title, formatted_transcript)
        
        # Step 3: Action Items Extraction (Gemma)
        action_items = await self.action_extractor_agent.extract_actions(
            meeting_id,
            meeting_title,
            formatted_transcript
        )
        
        # Step 4: Scheduling Evaluation
        schedule_eval = self.scheduler_agent.evaluate_tasks_for_scheduling(action_items)
        
        return {
            "meeting_id": meeting_id,
            "title": meeting_title,
            "summary": summary,
            "action_items": action_items,
            "scheduling": schedule_eval,
            "transcript_count": len(clean_chunks)
        }

