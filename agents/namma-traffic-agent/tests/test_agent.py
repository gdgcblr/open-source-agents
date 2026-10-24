"""
test_agent.py - Unit tests for NammaTrafficAgent execution and reproducibility
"""

import pytest
from agent.core import NammaTrafficAgent


def test_agent_initialization():
    agent = NammaTrafficAgent()
    assert agent is not None


def test_agent_route_query():
    agent = NammaTrafficAgent()
    res = agent.query("How is traffic from Indiranagar to Whitefield at 6pm?")
    assert res is not None
    assert "response" in res
    assert len(res["tools_used"]) > 0
    assert "Indiranagar" in res["response"] or "Whitefield" in res["response"]


def test_agent_chokepoint_query():
    agent = NammaTrafficAgent()
    res = agent.query("Is Silk Board jammed?")
    assert res is not None
    assert "Silk Board" in res["response"]


def test_agent_rain_query():
    agent = NammaTrafficAgent()
    res = agent.query("Any waterlogging in underpasses due to rain?")
    assert res is not None
    assert "Waterlogging" in res["response"] or "Rain" in res["response"]
