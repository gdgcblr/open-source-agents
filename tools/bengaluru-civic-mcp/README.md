# Bengaluru Civic Intelligence MCP Server (`bengaluru-civic-mcp`)

> A Model Context Protocol (MCP) server and developer utility providing hyperlocal Bengaluru municipal ward lookup, civic grievance triage, and authentic bilingual (English & Kannada) complaint generation.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Navigating municipal governance across Bengaluru's 8 zones and 198+ wards is notoriously complex for citizens, newcomers, and community volunteers. When civic emergencies occur—such as hazardous potholes, power outages (BESCOM), water pipeline leaks (BWSSB), or overflowing garbage—citizens often struggle to identify their ward number, responsible executive engineer division, correct 24x7 helpline, or how to draft a formal grievance in official administrative Kannada and English.
- **Intended Users**:
  - AI Agent developers building civic assistants, community bots, and city copilots.
  - Bengaluru citizens, Resident Welfare Associations (RWAs), and tech park commuter groups.
  - Hackathon participants at GDG Cloud Bengaluru building local community impact solutions.

### Key Features
- **Hyperlocal Bengaluru Ward & Jurisdiction Resolver**: Maps 35+ major tech and residential localities (Mahadevapura, Bellandur, HSR Layout, Koramangala, Indiranagar, Whitefield, Electronic City, Jayanagar, etc.) or 6-digit PIN codes directly to BBMP Ward number, Ward name, Zone, MLA constituency, BESCOM electricity subdivision, and BWSSB water station.
- **Smart Civic Triage & SLA Engine**: Automatically parses grievance text in English, Kannada, or mixed Kanglish (*"Current illa"*, *"Raste thumba gundi ide"*), assigns responsible authority (BBMP, BESCOM, BWSSB, BTP), and calculates expected resolution SLA.
- **Authentic Bilingual Complaint Generator**: Generates formal administrative letters in BOTH English and authentic administrative Kannada (*ದೂರು, ಮಾನ್ಯರೇ, ವಾರ್ಡ್, ವಿಷಯ, ರಸ್ತೆ ಗುಂಡಿ, ಪರಿಹಾರ ಕೋರಿಕೆ*).
- **Multi-Channel Escalation Dispatch**: Formats ready-to-post public escalation tweets under 280 characters tagged with verified handles (`@BBMPCOMM`, `@NammaBESCOM`, `@BWSSBOnline`, `@blrcitytraffic`), generates WhatsApp templates, and provides 24x7 helpline contacts (1912, 1916, 080-22660000).
- **Dual Execution Modes**: Runs as a standard Model Context Protocol (MCP) server over `stdio` for Claude Desktop, Antigravity IDE, Cursor, and custom agents, OR as a zero-dependency CLI tool.

---

## Technical Stack

- **Language & Runtime**: Node.js (v18+ / v20+ / v24+) & TypeScript
- **Protocol**: Model Context Protocol (MCP) via `@modelcontextprotocol/sdk` (v1.32+)
- **Validation**: Zod (v3.24+)
- **Data Engine**: Curated, zero-latency, offline-first Bengaluru municipal and administrative dataset

---

## Architecture & Data Flow

```
[Citizen / Agent Query] 
          │
          ▼
┌────────────────────────────────────────────────────────┐
│             bengaluru-civic-mcp Server                │
│                                                        │
│  ┌───────────────────┐        ┌─────────────────────┐  │
│  │   WardResolver    │        │    TriageEngine     │  │
│  │ (Locality/PIN ->  │        │ (Issue Classification│ │
│  │  BBMP Ward & Zone)│        │   & SLA Calculator) │  │
│  └─────────┬─────────┘        └──────────┬──────────┘  │
│            │                             │             │
│            └──────────────┬──────────────┘             │
│                           ▼                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │  BilingualFormatter & SocialDispatcher Services   │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────────┬────────────────────────────┘
                            ▼
    [Bilingual Formal Grievance & X/WhatsApp Dispatch]
```

---

## Prerequisites

- Node.js (v18.0.0 or higher; tested on Node.js v24)
- npm (v9.0.0 or higher)

---

## Installation & Setup

1. **Navigate to the tool directory:**
   ```bash
   cd tools/bengaluru-civic-mcp
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Build TypeScript source:**
   ```bash
   npm run build
   ```

4. **Environment Configuration (Optional):**
   ```bash
   cp .env.example .env
   ```
   *(Note: This MCP tool operates entirely offline with zero external paid API dependencies!)*

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | No | *stdio* | Execution mode (defaults to standard MCP stdio) |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

### 1. As an MCP Server (for AI Agents, Claude, Cursor, Antigravity)
Add this to your MCP configuration file (`claude_desktop_config.json` or `mcp_config.json`):

```json
{
  "mcpServers": {
    "bengaluru-civic": {
      "command": "node",
      "args": ["<path-to-repo>/tools/bengaluru-civic-mcp/dist/index.js"]
    }
  }
}
```

### 2. Standalone CLI Mode (for Testing & Demonstration)

```bash
# 1. Look up any locality, landmark, or PIN code
node dist/index.js --lookup "Mahadevapura"
node dist/index.js --lookup "560102"
node dist/index.js --lookup "Google Ananta"

# 2. Triage an issue and check SLA
node dist/index.js --triage "Deep dangerous pothole near 27th Main HSR Layout"

# 3. Generate bilingual English + Kannada formal complaint letter
node dist/index.js --complaint --locality "Bellandur" --desc "Sewage line overflow on service road"

# 4. Generate social media X/Twitter dispatch and WhatsApp template
node dist/index.js --dispatch --locality "Indiranagar" --desc "Streetlights not working on 12th Main"

# 5. View complete Bengaluru civic directory by zone
node dist/index.js --directory --zone "Mahadevapura"
```

---

## Example Input & Output

### Example Input (Ward Lookup)
```bash
node dist/index.js --lookup "Google Ananta"
```

### Example Output
```json
{
  "found": true,
  "query": "Google Ananta",
  "matchedWard": {
    "locality": "Mahadevapura",
    "wardNumber": 82,
    "wardName": "Garudacharpalya",
    "zone": "Mahadevapura",
    "pinCodes": ["560048", "560037"],
    "mlaConstituency": "Mahadevapura",
    "bescomSubdivision": "E-4 Whitefield Subdivision",
    "bwssbServiceStation": "KR Puram Central Sub-Division",
    "landmarkHotspots": ["Google Ananta", "Bagmane Constellation Park", "Phoenix Marketcity"]
  },
  "confidence": "alias"
}
```

### Example Input (Bilingual Complaint Generation)
```bash
node dist/index.js --complaint --locality "HSR Layout" --desc "Multiple deep potholes near Agara Lake junction causing two-wheeler skids"
```

### Example Output (Kannada Excerpt)
```
ವಿಷಯ: ತುರ್ತು ಮನವಿ: ವಾರ್ಡ್ ಸಂಖ್ಯೆ 174 (HSR Layout), HSR Layout ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ರಸ್ತೆ ಗುಂಡಿ ಮತ್ತು ಹಾಳಾದ ರಸ್ತೆ ದುರಸ್ತಿ ಕೋರಿಕೆ

ಮಾನ್ಯರೇ,
ಮೇಲ್ಕಂಡ ವಿಷಯಕ್ಕೆ ಸಂಬಂಧಿಸಿದಂತೆ, ನಾನು ತಮ್ಮ ಘನತೆವೆತ್ತ ಕಚೇರಿಯ ವ್ಯಾಪ್ತಿಯಲ್ಲಿ ಕಂಡುಬಂದಿರುವ ಸಾರ್ವಜನಿಕ ಸಮಸ್ಯೆಯ ಬಗ್ಗೆ ಈ ಮೂಲಕ ಲಿಖಿತ ದೂರು ಸಲ್ಲಿಸುತ್ತಿದ್ದೇನೆ.
ಸ್ಥಳದ ವಿವರಗಳು:
- ನಿರ್ದಿಷ್ಟ ಸ್ಥಳ / ಪ್ರಮುಖ ಗುರುತು: HSR Layout
- ವಾರ್ಡ್ ವಿವರ: ಸಂಖ್ಯೆ 174 (HSR Layout), ವಲಯ: Bommanahalli
...
ಧನ್ಯವಾದಗಳೊಂದಿಗೆ,
ತಮ್ಮ ವಿಶ್ವಾಸಿ,
ಜಾಗೃತ ಬೆಂಗಳೂರು ನಿವಾಸಿ
```

---

## How to Test

Run the automated test suite using Node's native test runner:

```bash
npm test
```

This verifies:
- Ward and jurisdiction resolution across all 8 zones and PIN codes.
- Triage accuracy for BBMP, BESCOM, BWSSB, and BTP issue categories.
- Authentic administrative Kannada and English formatting.
- Social dispatch character limits (< 280 chars) and hashtag formatting.
- MCP tool execution conforming to the Model Context Protocol specification.

---

## Known Limitations

- Covers 35+ primary residential, tech corridor, and industrial hubs across all 8 BBMP zones. Outlying panchayat regions beyond BBMP jurisdiction require manual ward lookup.
- Does not automatically post to social networks or file official tickets on live portals (generates sanitized, ready-to-submit payloads for user review).

---

## Security & Privacy Considerations

- **Zero External Secret Dependencies**: Requires no API keys, credentials, or paid cloud services.
- **Privacy First**: Operates 100% locally on the user's machine; no citizen complaint details or location data are logged or transmitted externally.
- **Safe Payload Generation**: All text generation uses strict schema validation and sanitization.

---

## Future Improvements

- [ ] Support automated filing via BBMP Sahaaya 2.0 public API endpoints.
- [ ] Add ward corporator and MLA contact phone directory.
- [ ] Add automated geotagged photo attachment extraction.

---

## License

This project is contributed under the repository's [MIT License](../../LICENSE).
