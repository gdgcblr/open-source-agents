"""Serve the reviewer over A2A. Agent card: http://localhost:8001/.well-known/agent-card.json"""
import os

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from reviewer.agent import root_agent

PORT = int(os.environ.get("PORT", "8001"))
HOST = os.environ.get("HOST", "127.0.0.1")
app = to_a2a(root_agent, host="localhost", port=PORT)

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
