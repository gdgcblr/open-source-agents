from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

class SchedulerAgent:
    """
    Calendar & Task Scheduler Agent: Interfaces with Google Calendar MCP tool
    to create reminders, verify deadlines, and identify missing deadlines.
    """
    
    def evaluate_tasks_for_scheduling(self, action_items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Categorizes tasks into those ready to schedule vs those needing deadline input.
        """
        ready_to_schedule = []
        needs_deadline = []
        
        for task in action_items:
            deadline = task.get("deadline")
            if deadline:
                ready_to_schedule.append(task)
            else:
                needs_deadline.append(task)
                
        return {
            "ready_to_schedule": ready_to_schedule,
            "needs_deadline": needs_deadline
        }
        
    def generate_calendar_event_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constructs a standard Google Calendar event payload with reminders.
        """
        deadline_str = task.get("deadline")
        if deadline_str:
            try:
                start_dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            except Exception:
                start_dt = datetime.utcnow() + timedelta(days=1)
        else:
            start_dt = datetime.utcnow() + timedelta(days=1)
            
        end_dt = start_dt + timedelta(minutes=30)
        
        return {
            "summary": f"[MeetingMind] {task.get('task')[:50]}",
            "description": f"Owner: {task.get('owner')}\nMeeting: {task.get('meetingTitle')}\nAction: {task.get('task')}",
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 1440}, # 24 hours
                    {"method": "popup", "minutes": 120},  # 2 hours
                    {"method": "email", "minutes": 60}    # 1 hour
                ]
            }
        }

