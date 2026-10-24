# Fix Maadi

> Show the problem. Get the right next step.

## What Fix Maadi does

If someone sees a pothole, overflowing drain, garbage dump, broken streetlight, or blocked footpath, they usually have to figure out three things themselves: what to write, who is responsible, and which official channel to use.

Fix Maadi helps with that. A resident shares a photo or a short description. The app turns it into a clear complaint, asks for only the important missing details, suggests the most relevant authority and reporting channel, and lets the resident review everything before sharing it.

The first configuration is for Bengaluru, but the project is designed so another contributor can add a different city, authority, issue type, language, or channel without rewriting the core agent.

## Main use case

**A Bengaluru resident notices one public problem and wants to report it correctly.**

Example: someone photographs a pothole near Indiranagar metro. Fix Maadi identifies the issue, checks whether the location and time are clear, prepares an English/Kannada complaint, recommends the relevant civic route, and gives the resident a safe, editable handoff. It does not log in, solve CAPTCHA, or submit anything automatically.

## Things this follows

- **It solves a real problem:** the project takes a vague civic complaint and helps turn it into something a resident can actually review and report.
- **It works without a specific AI company:** the current MVP uses local Python rules, so it can run without an API key. Gemini is an optional image-understanding provider, not a required dependency.
- **Other models can be added:** Gemini can be replaced or supplemented by an OpenAI model, an Anthropic model, a local Ollama model, or another provider, as long as it returns the same validated issue format. The routing and safety logic stays the same.
- **It is an agent, not a model wrapper:** the model or rules help understand the report, but the agent also asks follow-up questions, selects a source-backed route, prepares a complaint, applies guardrails, and waits for approval.
- **It is framework-agnostic:** the project currently uses a small Python implementation, but the same agent contract can be connected to ADK, OpenAI Agents SDK, LangGraph, CrewAI, or an MCP client.
- **It is safe by design:** guardrails check official sources, flag phone numbers and emails, reject invented promises, require resident approval, and do not bypass login, OTP, or CAPTCHA.
- **It is open for contributions:** someone can add a new city, authority registry, issue category, language, model provider, channel adapter, MCP prompt, or evaluation case without rewriting the whole project.
- **It is testable:** the repository includes offline scenarios for normal reports and unsafe or misleading inputs, so the project is not judged only by one successful demo.

This is how the project follows the repository’s standards in practical terms: another developer can run it, understand it, replace one part, test the change, and contribute it without changing unrelated projects.

## Overall flow: how and why this is an agent

This is not a static complaint form that sends every report to the same place. It makes a sequence of bounded decisions based on the resident’s input, then asks the resident to confirm them:

```text
Photo or description
        |
        v
Understand the issue
        |
        v
Check what information is missing
        |
        v
Select the relevant authority and source-backed channels
        |
        v
Prepare an editable complaint and evidence checklist
        |
        v
Apply guardrails and request resident approval
        |
        v
Copy the report or open the official service
```

### Example

**Resident input:**

> “There is a deep pothole near the Indiranagar metro entrance. Bikes are swerving around it.”

**What the agent does:**

1. Classifies it as road damage and identifies a possible safety risk.
2. Checks whether the exact location and observation time are present.
3. Recommends the relevant civic route from the verified channel registry.
4. Drafts an editable English/Kannada complaint and lists useful evidence.
5. Shows the resident the source, privacy warnings, and handoff options.
6. Waits for explicit approval before opening or copying anything.

The agent is useful because the next action changes with the issue, the evidence, the missing context, and the available official channels. The resident remains the final decision-maker; the agent does not log in, solve CAPTCHA, or submit on the resident’s behalf.

## Overview

### Problem Statement & Intended Users

Civic reporting is often not blocked by a lack of complaint forms. It is blocked by incomplete location details, the wrong department, weak evidence, duplicate submissions, and no follow-up habit. Fix Maadi is a resident-side agent that turns a WhatsApp-style description into a routed, reviewable civic casefile.

The included starter pack supports Bengaluru residents, students, apartment communities, commuters, and developer volunteers who want to report potholes, waterlogging, garbage, streetlights, and footpath issues clearly.

### Key Features

- Classifies an everyday observation into a civic issue category.
- Preserves related issues such as a pothole plus waterlogging instead of forcing a single label.
- Detects missing context such as a landmark, date, or description.
- Shows the likely responsible authority, why it was selected, and the available reporting options from a source-linked local registry.
- Uses an explicit agent state machine: `needs_information` → `ready_for_review` → `approved`.
- Creates a separate routing plan when one observation contains multiple issues.
- Produces an evidence checklist and English/Kannada complaint drafts.
- Flags likely duplicate cases when existing local case data is supplied.
- Saves a local case record, approval state, and follow-up timeline.
- Shows verified contact details and scope where an official source publishes them.
- Collects transparent, issue-specific local user feedback for every official channel. It shows counts first and only displays a percentage after five local reports, always labelled as a local sample rather than official efficiency.
- Starts with a photo-first intake, supports device geolocation, and keeps the generated description editable.
- Emits a safe decision trace so contributors can inspect the agent's observable decisions without exposing private chain-of-thought.
- Defines review-gated channel adapters and an offline evaluation suite under `evals/`.
- Includes local privacy detection for phone numbers/emails and guardrails against authentication bypass or automatic submission.
- Opens official guidance or copies a prepared message; browser form filling is a later optional adapter.
- Runs locally with no API key, account, or automatic submission.

## Why this is different from a complaint form

Bengaluru already has public complaint channels, including Sahaaya 2.0 and Fix My Street. Fix Maadi sits before submission and after the first report: it improves the quality of the case, chooses an appropriate route, prepares the format that route needs, reduces duplicate noise, and helps residents verify whether “resolved” really means fixed. The MVP deliberately requires a resident to review the case before using any official channel.

## Technical Stack

- **Language & Runtime**: Python 3.9+
- **Agent core**: A transparent, dependency-free decision engine in `fix_maadi.py`
- **Routing data**: A contribution-friendly, source-linked registry in `data/bengaluru_channels.json`
- **Interface**: Python standard-library HTTP server plus a responsive five-step HTML/CSS/JavaScript flow
- **Models**: No model is required for the deterministic MVP. An optional Gemini provider adds richer image understanding while local rules remain the fallback.
- **External services**: None. The MVP does not send reports or images to a third party.

## Architecture & Data Flow

```text
[Resident describes a problem]
                |
                v
 [classify issue + related issues]
       /       |        \
 authority  options      risk
       \       |        /
       [ask missing questions]
                |
                v
 [casefile + editable bilingual draft]
                |
                v
     [resident explicitly approves]
                |
                v
 [copy complaint or open official service]
```

The agent prepares and routes a case. The MVP can open verified official guidance or copy a channel-ready message. A future browser adapter may fill a portal, but submission remains an explicit resident action.

## Prerequisites

- Python 3.9 or newer
- A browser
- No API key or third-party package

## Installation & Setup

```bash
cd agents/fix-maadi
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows PowerShell
python -m pip install -r requirements.txt
```

The core agent uses only the Python standard library. Run it from this directory so the bundled interface and city registry remain beside the server. The optional MCP bridge has its own dependency manifest under `mcp/`.

## Configuration & Environment Variables

The MVP runs without environment variables. To use a different city or authority pack, set `FIX_MAADI_CHANNEL_FILE` to a JSON registry with the same schema as `data/bengaluru_channels.json`. To enable optional image inference, export `GEMINI_API_KEY` and optionally `GEMINI_MODEL` (default: `gemini-2.5-flash`) before starting the server. The key stays server-side and is never sent to the browser. `.env.example` documents the variables without committing secrets. Channel entries should include an official source URL, required fields, mode, and verification date.

## How to Run

From the project directory:

```bash
python fix_maadi.py --port 8000
```

Open <http://127.0.0.1:8000> and follow the five steps:

1. Describe the problem or load the single-issue example.
2. Review the detected issue, responsible authority, and reporting options.
3. Answer the route-specific missing questions.
4. Edit and approve the evidence-backed English/Kannada complaint.
5. Copy it or open the official service for final submission.

Try these demo inputs:

```text
A deep pothole is breaking up the road near the Indiranagar metro entrance. Motorbikes are swerving around it.
```

## Example Output

The casefile contains a stable local case ID, category, related issues, confidence, severity, missing confirmation, suggested authority/channel, evidence checklist, English draft, Kannada draft, privacy guidance, follow-up steps, and channel-specific handoff options. The resident can approve a handoff, open official guidance, or copy a prepared message after checking it.

## How to Test

```bash
python -m unittest discover -s tests -v
```

The tests cover classification/routing, multi-issue plans, agent states, structured missing questions, bilingual output, duplicate and false-positive detection, guardrails, vision-provider validation, and safe empty input handling.

Run the offline scenario evaluation from this directory:

```bash
python evals/run_evals.py
```

The evaluation suite checks six representative Bengaluru cases, including an illegal-dumping versus missed-collection channel decision. It uses no API key and fails with an actionable scenario name when routing behavior changes.

## Open-Source Contribution Boundary

This project is intentionally isolated to its agent directory plus the optional companion MCP tool. Contributors can extend it without changing the repository root:

- Add a parser for a new input format, such as a voice transcript or OpenStreetMap note.
- Add a transparent ward or department routing dataset with source and freshness metadata.
- Add a model adapter behind the existing analyzer interface, keeping the rule-based fallback.
- Add a `SubmissionAdapter` for a verified civic portal while keeping copy/download fallbacks.
- Add a new `ChannelAdapter` in `adapters.py`; adapters must prepare a reviewable action and must not submit, bypass login, or solve CAPTCHA.
- Extend the optional MCP bridge in `mcp/` with read/prepare-only tools that call the local agent API.
- Add an MCP prompt or resource that preserves the approval, privacy, and no-login/CAPTCHA boundary.
- Add a scenario to `evals/scenarios.json` for every new category or channel rule.
- Add or strengthen a guardrail in `guardrails.py` when introducing a new model or external action.
- Add tests with synthetic, non-personal cases.
- Add verified official-channel links only after checking their current source.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the extension contract and review checklist.

Do not add private resident data, credentials, scraped phone numbers, unverified official contacts, or code that files complaints automatically without user review.

## Known Limitations

- With `GEMINI_API_KEY`, the server sends bounded inline image bytes to Gemini's multimodal `generateContent` endpoint and validates the returned category/description. Without the key, it uses transparent local rules and an editable draft. Images are never sent to Gemini silently.
- Department suggestions are guidance, not an authoritative jurisdiction decision.
- The duplicate check treats an exact latitude/longitude match for the same category as one local case; it does not query a live civic database.
- The MVP prepares reports and handoffs but does not submit them to Sahaaya, Fix My Street, or another civic system.
- Kannada text is a concise template; richer language generation is a future adapter.

## Security & Privacy Considerations

- Rule-based processing is local in the MVP; when Gemini is configured and a resident selects an image, bounded image bytes are sent to the configured Gemini API for analysis. The server binds to `127.0.0.1` by default.
- The interface reminds users to remove faces, vehicle plates, phone numbers, and unrelated personal details.
- Images are not retained by Fix Maadi; a configured Gemini request is the only external image transfer and is explicit in the local configuration.
- Guardrails reject unsupported SLA promises, require source-backed official routes, keep resident approval mandatory, and flag likely personal data for review.
- The analyzer never executes text as code and never calls an external tool automatically.

## Future Improvements

- [x] Add a server-side Gemini vision provider with strict JSON validation and a deterministic fallback.
- [ ] Add source-versioned city packs for another municipality.
- [ ] Add a local SQLite case timeline and evidence hash.
- [ ] Add a browser adapter that fills verified portal fields without bypassing login, OTP, or CAPTCHA.
- [ ] Add a browser extension adapter that previews the prepared case inside official portals and requires a final resident click.
- [ ] Add official WhatsApp/helpline adapters where the authority publishes a supported integration.
- [ ] Add a provider conformance test suite for Gemini, local models, and future ADK/MCP adapters.
- [ ] Add Kannada voice input, transliteration, and accessibility testing.
- [ ] Add a redaction adapter for faces, vehicle plates, phone numbers, and email addresses before external handoff.
- [ ] Add a public, privacy-preserving benchmark set contributed by residents and civic volunteers.
- [ ] Add a community review mode that merges corroborating reports without exposing personal data.

## License

This project is contributed under the repository's MIT License.
