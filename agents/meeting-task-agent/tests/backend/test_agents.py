import os
import sys
import unittest
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from adk_engine.agents.ingestion_agent import IngestionAgent
from adk_engine.agents.summarizer_agent import SummarizerAgent
from adk_engine.agents.action_extractor_agent import ActionExtractorAgent
from adk_engine.agents.scheduler_agent import SchedulerAgent
from mcp_servers.task_store_mcp import TaskStoreMCPServer

class TestMeetingMindAgents(unittest.TestCase):
    
    def setUp(self):
        self.ingestion = IngestionAgent()
        self.summarizer = SummarizerAgent()
        self.action_extractor = ActionExtractorAgent()
        self.scheduler = SchedulerAgent()
        self.test_db_path = "/tmp/test_meetingmind.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.task_store = TaskStoreMCPServer(db_path=self.test_db_path)

    def tearDown(self):
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_ingestion_merging(self):
        chunks = [
            {"speaker": "Alice", "text": "Good morning team,", "timestamp": "2026-10-24T10:00:00Z"},
            {"speaker": "Alice", "text": "let's review the sprint backlog.", "timestamp": "2026-10-24T10:00:05Z"},
            {"speaker": "Bob", "text": "I will handle the API deployment.", "timestamp": "2026-10-24T10:00:10Z"}
        ]
        merged = self.ingestion.process_transcript(chunks)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["speaker"], "Alice")
        self.assertIn("Good morning team, let's review the sprint backlog.", merged[0]["text"])
        self.assertEqual(merged[1]["speaker"], "Bob")

    def test_action_item_fallback_extraction(self):
        transcript = (
            "Alice: Let's discuss infrastructure.\n"
            "Bob: I will prepare the cloud budget proposal by Friday.\n"
            "Charlie: I will schedule the follow up meeting with the client."
        )
        actions = self.action_extractor._extract_fallback("meet_123", "Sprint Planning", transcript)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["owner"], "Bob")
        self.assertIn("prepare the cloud budget", actions[0]["task"])
        self.assertEqual(actions[1]["owner"], "Charlie")

    def test_scheduler_evaluation(self):
        tasks = [
            {"id": "t1", "owner": "Alice", "task": "Task 1", "deadline": "2026-10-30T17:00:00Z"},
            {"id": "t2", "owner": "Bob", "task": "Task 2", "deadline": None}
        ]
        eval_result = self.scheduler.evaluate_tasks_for_scheduling(tasks)
        self.assertEqual(len(eval_result["ready_to_schedule"]), 1)
        self.assertEqual(len(eval_result["needs_deadline"]), 1)
        self.assertEqual(eval_result["needs_deadline"][0]["id"], "t2")

    def test_task_store_crud(self):
        task = {
            "id": "task_abc_1",
            "meeting_id": "m1",
            "meeting_title": "Design Review",
            "owner": "David",
            "task": "Review security audit report",
            "deadline": "2026-11-01T12:00:00Z",
            "priority": "high",
            "status": "pending"
        }
        self.task_store.upsert_task(task)
        
        # Query
        all_tasks = self.task_store.get_all_tasks()
        self.assertEqual(len(all_tasks), 1)
        self.assertEqual(all_tasks[0]["owner"], "David")
        self.assertEqual(all_tasks[0]["status"], "pending")

        # Update status to completed
        success = self.task_store.update_task_status("task_abc_1", "completed", "2026-10-24T11:00:00Z")
        self.assertTrue(success)

        updated = self.task_store.get_all_tasks(status="completed")
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["id"], "task_abc_1")

if __name__ == "__main__":
    unittest.main()

