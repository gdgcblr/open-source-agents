import json
import re
import uuid
import httpx
from typing import Dict, Any, List
from config import settings
from adk_engine.prompts.gemma_prompts import GEMMA_ACTION_EXTRACTION_SYSTEM_PROMPT

class ActionExtractorAgent:
    """
    Action Extractor Agent: Uses open-source Gemma to identify commitments,
    delegations, and action items per participant, formatted as a to-do list.
    """
    
    def __init__(self, ollama_url: str = None, model: str = None):
        self.ollama_url = ollama_url or settings.ollama_base_url
        self.model = model or settings.gemma_model
        
    async def extract_actions(self, meeting_id: str, meeting_title: str, formatted_transcript: str) -> List[Dict[str, Any]]:
        """
        Extracts action items assigned to each participant from the transcript.
        """
        user_prompt = f"Meeting Title: {meeting_title}\n\nTranscript:\n{formatted_transcript}"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "system": GEMMA_ACTION_EXTRACTION_SYSTEM_PROMPT,
                        "prompt": user_prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                
                if res.status_code == 200:
                    raw_text = res.json().get("response", "")
                    return self._parse_actions(raw_text, meeting_id, meeting_title)
        except Exception as e:
            print(f"[ActionExtractorAgent] LLM connection error: {e}. Using rule-based extraction fallback.")
            
        return self._extract_fallback(meeting_id, meeting_title, formatted_transcript)
        
    def _parse_actions(self, raw_text: str, meeting_id: str, meeting_title: str) -> List[Dict[str, Any]]:
        cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)
        
        try:
            data = json.loads(cleaned)
            raw_items = data.get("action_items") or data.get("actionItems") or []
            
            normalized = []
            for item in raw_items:
                normalized.append({
                    "id": f"task_{uuid.uuid4().hex[:8]}",
                    "meetingId": meeting_id,
                    "meetingTitle": meeting_title,
                    "owner": item.get("owner", "Unassigned"),
                    "ownerEmail": item.get("owner_email"),
                    "task": item.get("task", ""),
                    "deadline": item.get("deadline"),  # Can be ISO string or None
                    "priority": item.get("priority", "medium").lower(),
                    "status": "pending",
                    "nudgeCount": 0,
                    "createdAt": "now"
                })
            return normalized
        except Exception as e:
            print(f"[ActionExtractorAgent] JSON parse error: {e}")
            return self._extract_fallback(meeting_id, meeting_title, raw_text)
            
    def _extract_fallback(self, meeting_id: str, meeting_title: str, transcript: str) -> List[Dict[str, Any]]:
        action_keywords = re.compile(
            r"\b(will|should|must|action|assigned to|takes care of|follow up|prepare|finalize|send|schedule|review)\b",
            re.IGNORECASE
        )
        
        items = []
        for line in transcript.split("\n"):
            if not line.strip() or ":" not in line:
                continue
            speaker, content = line.split(":", 1)
            speaker = speaker.strip()
            content = content.strip()
            
            if action_keywords.search(content):
                items.append({
                    "id": f"task_{uuid.uuid4().hex[:8]}",
                    "meetingId": meeting_id,
                    "meetingTitle": meeting_title,
                    "owner": speaker,
                    "ownerEmail": None,
                    "task": content,
                    "deadline": None,  # Missing deadline will trigger prompt & nudge loop
                    "priority": "medium",
                    "status": "pending",
                    "nudgeCount": 0,
                    "createdAt": "now"
                })
        return items

