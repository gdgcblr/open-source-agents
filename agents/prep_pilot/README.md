# PrepPilot — Your personal AI interview coach

PrepPilot helps candidates prepare for a specific interview through a guided,
adaptive conversation. Using Gemini only, it builds a time-aware learning
roadmap from the candidate's job description and context, teaches and practices
concepts, and runs role-specific mock interviews.

The directory uses `prep_pilot` because ADK requires app names to be valid
Python identifiers; the agent is launched as `prep_pilot`.

## What it does

- Learns about the role, level, job description, deadline, available study time,
  confidence areas, and interview format through short follow-up questions.
- Uses the candidate-provided job description and Gemini's general knowledge;
  it does not browse or verify current company information.
- Clearly distinguishes candidate-provided requirements from general industry
  guidance and does not invent interview reports or citations.
- Builds a day-by-day roadmap with measurable goals, practice, resources, and
  checkpoints, then revises it based on candidate performance.
- Explains concepts, gives practice, reviews responses, adjusts difficulty, and
  conducts tailored mock interviews with follow-up questions and final feedback.

## Technical stack

- **Language & runtime:** Python 3.10+
- **Agent framework:** Google Agent Development Kit (ADK)
- **Model:** Gemini 3.5 Flash
- **Tools:** None; Gemini responses only

## How it works

```text
Candidate conversation
        |
        v
PrepPilot (ADK + Gemini)
        |
        +--> Candidate context and job-description-based coaching
        +--> Adaptive daily roadmap and practice checkpoints
        +--> Teaching, mock interview, and feedback
```

## Prerequisites

- Python 3.10 or later
- Google ADK dependencies (installed below)
- A Google AI Studio API key with access to Gemini

Candidate prompts and job-description text sent to PrepPilot are processed by
Google's Gemini API. Do not submit confidential interview materials or
unnecessary personal information. API usage may be subject to quotas or charges.

## Installation and setup

From the repository root:

```bash
cd agents
python -m venv .venv
source .venv/bin/activate
pip install -r prep_pilot/requirements.txt
[ -f prep_pilot/.env ] || cp prep_pilot/.env.example prep_pilot/.env
```

Add your `GOOGLE_API_KEY` to `prep_pilot/.env`. Do not commit that file.

## Run PrepPilot

From `open-source-agents/agents` with the virtual environment active:

```bash
adk web
```

Open the local URL printed by ADK and select `prep_pilot`. To chat in a
terminal instead:

```bash
adk run prep_pilot
```

Start with a request such as:

> I have a senior backend engineer interview at Acme in 12 days. I can study
> 90 minutes each weekday and 3 hours on weekends. I feel confident in APIs but
> need work on system design. Here's the job description: ...

You can also ask PrepPilot to explain a topic, revise your plan after a
checkpoint, or start a timed mock interview. Mock pacing is conversational and
does not use a real-time stopwatch.

## Validate

From `open-source-agents/agents`:

```bash
python -m unittest discover -s prep_pilot -p 'test_*.py'
```

These offline tests verify ADK agent loading and key coaching instructions,
including that no external tools are configured. To exercise coaching with
Gemini, configure the API key and run the agent interactively.

## Evidence and limitations

PrepPilot cannot browse the web or independently verify job listings, company
information, or interview reports. It treats a pasted job description as
candidate-provided context and labels its other advice as general knowledge.
Verify current company-specific information and suggested learning resources
with authoritative sources.

The coaching roadmap and mock interview feedback are generated guidance, not
guarantees or employer assessments. The agent cannot verify private interview
plans, and mock interviews are paced through conversation rather than a
real-time timer.
