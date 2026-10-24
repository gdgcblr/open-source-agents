# Civic Road & Infrastructure Safety Agent

An AI-powered civic infrastructure triage agent that evaluates citizen-reported road hazards (such as potholes, water-filled craters, failed asphalt patches, and debris blockages), assesses commuter risk, suggests civil engineering repairs, and routes dispatch to the appropriate municipal department.

## Overview

Road hazards like deep potholes and structural degradations cause significant vehicular damage and severe road accidents worldwide. This agent provides a fast, structured triage layer for municipal maintenance teams to process citizen complaints and prioritize road repairs efficiently.

## Architecture

- **Model**: `gemini-3.8-flash`
- **SDK**: `google-genai` (v0.1.0+)
- **Structured Validation**: Pydantic schemas enforcing typed outputs (`RoadIssueAssessment`)
- **Runtime**: Python 3.10+

## Prerequisites & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/gemini-researcher