import json
import base64
import httpx
from typing import Dict, Any, List, Optional

class WorkspaceMCPServer:
    """
    Model Context Protocol (MCP) Server exposing Google Workspace Tools
    (Drive, Calendar, Gmail) to Gemma Agents and the Extension Client.
    """
    
    def __init__(self):
        self.tools = {
            "google_drive_save_meeting": self.save_meeting_to_drive,
            "google_calendar_create_reminder": self.create_calendar_reminder,
            "google_gmail_send_nudge": self.send_gmail_nudge
        }
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Returns MCP standard tool definitions.
        """
        return [
            {
                "name": "google_drive_save_meeting",
                "description": "Saves meeting transcript, summary, and action items as a markdown file in user's Google Drive /MeetingMind/ folder.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "meeting_id": {"type": "string"},
                        "title": {"type": "string"},
                        "summary": {"type": "object"},
                        "action_items": {"type": "array"},
                        "transcript": {"type": "array"}
                    },
                    "required": ["title", "action_items"]
                }
            },
            {
                "name": "google_calendar_create_reminder",
                "description": "Creates a Google Calendar reminder event with popup and email notifications for an action item.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "deadline": {"type": "string"},
                        "owner": {"type": "string"}
                    },
                    "required": ["title", "deadline"]
                }
            },
            {
                "name": "google_gmail_send_nudge",
                "description": "Dispatches a follow-up email reminder via Gmail API for missing deadlines or pending deliverables.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "recipient_email": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"}
                    },
                    "required": ["recipient_email", "subject", "body"]
                }
            }
        ]

    async def save_meeting_to_drive(
        self,
        payload: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """
        Creates or updates a Markdown document in the user's /MeetingMind/ Google Drive folder.
        """
        title = payload.get("title", "Meeting")
        folder_name = "MeetingMind"
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        async with httpx.AsyncClient() as client:
            # 1. Check/create folder
            q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            search_res = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"q": q, "fields": "files(id, name)"},
                headers=headers
            )
            folder_id = None
            if search_res.status_code == 200:
                files = search_res.json().get("files", [])
                if files:
                    folder_id = files[0]["id"]
                    
            if not folder_id:
                folder_res = await client.post(
                    "https://www.googleapis.com/drive/v3/files",
                    json={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
                    headers=headers
                )
                if folder_res.status_code in (200, 201):
                    folder_id = folder_res.json().get("id")

            # 2. Build Markdown content
            content = self._format_markdown(payload)
            file_name = f"{title.replace('/', '-')}_Notes.md"
            
            # 3. Multipart upload
            metadata = {
                "name": file_name,
                "mimeType": "text/markdown",
            }
            if folder_id:
                metadata["parents"] = [folder_id]
                
            boundary = "mcp_boundary_meetingmind"
            body = (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: text/markdown\r\n\r\n"
                f"{content}\r\n"
                f"--{boundary}--"
            )
            
            upload_res = await client.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink",
                content=body.encode("utf-8"),
                headers={
                    **headers,
                    "Content-Type": f"multipart/related; boundary={boundary}"
                }
            )
            
            if upload_res.status_code in (200, 201):
                data = upload_res.json()
                return {
                    "success": True,
                    "file_id": data.get("id"),
                    "web_view_link": data.get("webViewLink", "")
                }
            else:
                return {
                    "success": False,
                    "error": f"Drive upload failed with status {upload_res.status_code}"
                }
                
    async def create_calendar_reminder(
        self,
        payload: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """
        Creates a Google Calendar reminder event.
        """
        title = payload.get("title", "Action Item")
        description = payload.get("description", "")
        deadline = payload.get("deadline")
        
        if not deadline:
            return {"success": False, "error": "Deadline required to schedule reminder"}
            
        event_body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": deadline},
            "end": {"dateTime": deadline},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 1440},
                    {"method": "popup", "minutes": 120},
                    {"method": "email", "minutes": 60}
                ]
            }
        }
        
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                json=event_body,
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            if res.status_code in (200, 201):
                data = res.json()
                return {
                    "success": True,
                    "event_id": data.get("id"),
                    "html_link": data.get("htmlLink")
                }
            return {"success": False, "error": f"Calendar API error {res.status_code}"}

    async def send_gmail_nudge(
        self,
        payload: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """
        Sends an email reminder nudge via Gmail REST API.
        """
        recipient = payload.get("recipient_email")
        subject = payload.get("subject", "Action Item Reminder")
        body = payload.get("body", "")
        
        if not recipient:
            return {"success": False, "error": "Recipient email required"}
            
        raw_msg = (
            f"To: {recipient}\r\n"
            f"Subject: {subject}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            f"{body}"
        )
        encoded = base64.urlsafe_b64encode(raw_msg.encode("utf-8")).decode("utf-8")
        
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://www.googleapis.com/gmail/v1/users/me/messages/send",
                json={"raw": encoded},
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            if res.status_code in (200, 201):
                return {"success": True, "message_id": res.json().get("id")}
            return {"success": False, "error": f"Gmail API error {res.status_code}"}

    def _format_markdown(self, payload: Dict[str, Any]) -> str:
        title = payload.get("title", "Meeting")
        summary = payload.get("summary", {})
        actions = payload.get("action_items", [])
        transcript = payload.get("transcript", [])
        
        md = f"# {title}\n\n"
        if summary:
            md += f"## Executive Summary\n{summary.get('overview', '')}\n\n"
            if summary.get("keyPoints"):
                md += "### Key Points\n"
                for kp in summary["keyPoints"]:
                    md += f"- {kp}\n"
                md += "\n"
            if summary.get("decisions"):
                md += "### Decisions Made\n"
                for d in summary["decisions"]:
                    md += f"- ✓ {d}\n"
                md += "\n"
                
        md += "## Action Items (To-Do List)\n\n"
        for a in actions:
            check = "[x]" if a.get("status") == "completed" else "[ ]"
            due = a.get("deadline") or "No deadline set"
            md += f"- {check} **{a.get('owner')}**: {a.get('task')} *(Due: {due})*\n"
        md += "\n"
        
        if transcript:
            md += "## Transcript\n\n"
            for t in transcript:
                md += f"> **{t.get('speaker')}**: {t.get('text')}\n\n"
                
        return md

