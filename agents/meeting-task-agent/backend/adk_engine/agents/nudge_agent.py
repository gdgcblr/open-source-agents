from typing import Dict, Any, Optional
from datetime import datetime
import json
import httpx
from config import settings
from adk_engine.prompts.gemma_prompts import GEMMA_NUDGE_EMAIL_PROMPT

class NudgeAgent:
    """
    Nudge & Follow-up Agent: Evaluates task states and coordinates email nudges
    via Gmail MCP server for tasks missing deadlines or pending completion.
    """
    
    def __init__(self, ollama_url: str = None, model: str = None):
        self.ollama_url = ollama_url or settings.ollama_base_url
        self.model = model or settings.gemma_model
        
    async def generate_nudge_email(
        self,
        task: Dict[str, Any],
        reason: str
    ) -> Dict[str, str]:
        """
        Generates context-aware email subject and body for a nudge.
        """
        prompt = GEMMA_NUDGE_EMAIL_PROMPT.format(
            task_title=task.get("task", ""),
            owner=task.get("owner", "Team Member"),
            meeting_title=task.get("meetingTitle", "our recent meeting"),
            reason=reason,
            deadline=task.get("deadline") or "Not specified"
        )
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                if res.status_code == 200:
                    data = json.loads(res.json().get("response", "{}"))
                    if "subject" in data and "body" in data:
                        return data
        except Exception:
            pass
            
        # Fallback template
        if reason == "missing_deadline":
            return {
                "subject": f"[Action Required] Set deadline for: {task.get('task', '')[:40]}",
                "body": (
                    f"Hi {task.get('owner')},\n\n"
                    f"During the meeting '{task.get('meetingTitle')}', you were assigned the following action item:\n"
                    f"\"{task.get('task')}\"\n\n"
                    f"A deadline has not yet been specified. Please update the target completion date in MeetingMind so we can schedule calendar reminders.\n\n"
                    f"Best regards,\nMeetingMind AI Agent"
                )
            }
        else:
            return {
                "subject": f"Reminder: Pending Task \"{task.get('task', '')[:40]}\"",
                "body": (
                    f"Hi {task.get('owner')},\n\n"
                    f"This is a reminder regarding your action item from '{task.get('meetingTitle')}':\n"
                    f"\"{task.get('task')}\"\n"
                    f"Due: {task.get('deadline') or 'Pending'}\n\n"
                    f"Please mark this item complete or reschedule it in MeetingMind once updated.\n\n"
                    f"Best regards,\nMeetingMind AI Agent"
                )
            }

