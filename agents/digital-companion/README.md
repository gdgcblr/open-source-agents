# Digital Companion (`digital-companion`)

An open-source multi-agent **IntentShield Engine** built with **Google ADK** and **Gemma** designed to protect elderly and less digitally experienced users from confusing UI patterns, subscription traps, unexpected UPI payment mandates, and overreaching app permissions.

---

## 🏛️ Multi-Agent Pipeline Architecture

Digital Companion uses a sequential 3-step agent workflow to cross-verify user intent against real-world screen realities before any irreversible action is taken:

```
[User Natural Language Input] 
       │
       ▼
1. 🧠 intent_parser_agent ──────► Extracts user goals, max cost & intended recipient
       │
       ▼
2. 🔍 consequence_analyzer_agent ──► Executes deterministic tools to inspect screens/QR payloads
       │
       ▼
3. 🛡️ companion_shield_agent ─────► Compares intent vs consequence & outputs Explain, Protect & Guide
```

### 1. `intent_parser_agent`
- **Role**: Understands what the user *thinks* they are doing.
- **Output**: Structured JSON containing the user's explicit goal, expected maximum cost (in INR), and intended recipient.

### 2. `consequence_analyzer_agent`
- **Role**: Inspects the raw screen state or QR payload using hardcoded safety tools.
- **Output**: Real-world financial cost, auto-renewal frequency, and flagged permission risks.

### 3. `companion_shield_agent`
- **Role**: Acts as the empathetic guardian. Compares intent and consequence and formats the final advisory report.
- **Output Sections**:
  - `### 🛡️ Status`: Clear safety verdict (`⚠️ INTENT CONFLICT DETECTED` or `✅ SAFE TO PROCEED`).
  - `### 💡 EXPLAIN`: Simple, jargon-free explanation.
  - `### 🚨 PROTECT`: Side-by-side comparison of user expectation vs. actual consequence.
  - `### 👉 GUIDE`: Actionable next steps.

---

## 🛠️ Built-In Deterministic Tools (`tools.py`)

- **`decode_upi_qr(qr_payload)`**: Parses `upi://pay?...` URIs to extract exact payee names, Virtual Payment Addresses (VPAs), and requested transfer amounts in INR.
- **`extract_pricing_and_autopay(screen_text)`**: Scans text using regular expressions for hidden recurring costs, subscription traps, and UPI Autopay mandates.
- **`audit_app_permissions(app_purpose, screen_text)`**: Cross-references requested device permissions (Contacts, Location, SMS, Call Logs) against the app's stated core purpose to detect overreaching behavior.

---

## 🚀 Step-by-Step Setup & Installation Guide

### Prerequisites
- **Python 3.11 or 3.12** installed on your system.
- A free **Google AI Studio API Key** ([Get your key here](https://aistudio.google.com/app/apikey)).

### Step 1: Navigate to Project Directory
Open your terminal (PowerShell on Windows, Terminal on Mac/Linux) and move into the agent folder:
```bash
cd agents/digital-companion
```

### Step 2: Create a Clean Virtual Environment
```bash
python -m venv .venv
```
- **On Windows PowerShell:**
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  .\.venv\Scripts\Activate.ps1
  ```
- **On Mac/Linux:**
  ```bash
  source .venv/bin/activate
  ```

### Step 3: Install Dependencies
Upgrade pip and install the required packages:
```bash
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy the environment template and open `.env`:
```bash
cp .env.example .env
```
Add your Google AI Studio API key inside `.env`:
```env
GOOGLE_API_KEY=AIzaSyYourActualKeyHere
GEMINI_API_KEY=AIzaSyYourActualKeyHere
MODEL_NAME=gemini/gemini-2.5-flash
```

### Step 5: Launch the Agent Web Interface
Start the Google ADK web server:
```bash
adk web .
```
Open **`http://localhost:8000`** in your browser, select **`digital_companion`** from the agent dropdown, and test your prompts!

---

## 🧪 Demo Test Scenarios

Copy and paste these sample prompts into the web UI to test the agent's defense mechanisms:

### Scenario 1: Hidden Subscription Trap
```text
MY INTENT: I want to try this utility app for free without paying anything.
SCREEN: Start your 3-day free trial! ₹0 today, ₹4,999/year after 3 days, auto-renews automatically. Tap 'Continue' to authorize UPI Autopay.
```

### Scenario 2: Suspicious UPI QR Scam
```text
MY INTENT: I am scanning a QR code to receive a cash refund of ₹500 from my electricity board.
SCREEN: UPI Payment Request: Send ₹10,000 to 'QuickRefund Services' (vpa: scammer@upi).
```

### Scenario 3: Overreaching App Permissions
```text
MY INTENT: I just want to use a simple offline flashlight utility.
SCREEN: Permission Request: FlashlightApp requires access to your Contacts list, SMS messages, and exact GPS Location.