# Bill Decoder Agent

> Upload a photo or PDF of any Indian utility bill and get a plain-language explanation of every charge, plus warnings about anything unusual.

**Live demo:** https://bill-decoder-00-14.streamlit.app

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Electricity, water, mobile and broadband bills are full of codes and charges (fixed charges, FAC, tax, arrears, estimated readings) that most people don't understand. So they pay without noticing mistakes, late fees or a sudden jump in usage.
- **Intended Users**: Households, students living away from home, tenants splitting bills, and elderly people who want a simple explanation of what they are paying for.

### Key Features
- **Reads the bill directly**: works with a phone photo (JPG/PNG/WEBP) or a PDF bill.
- **Explains every charge**: lists each line item with a one-line, plain-language meaning.
- **Flags red flags**: late fees, arrears, estimated meter readings, usage spikes, unknown charges or calculation mistakes.
- **Multi-language**: explanation in English, Kannada, Hindi or any language Gemini supports (`--lang`).
- **Money-saving tips**: practical tips specific to the bill type.
- **Two ways to use it**: a command-line tool (`main.py`) and a dark-mode web app (`app.py`) with large text and simple steps, designed for users of all ages.
- **Detailed web report**: due-date countdown, a "what to do now" checklist, usage and meter readings (actual vs estimated, daily average), a usage-history chart when the bill prints past months, subsidies applied, payment details, and a glossary of terms printed on the bill.
- **Tap-to-learn explanations**: every charge (e.g. Fixed Charges, FPPCA, P & G Surcharge, True-up Charges) has an **ℹ️ What does this mean?** button explaining what it is, why it's charged and whether it can be reduced. Every section has an **ℹ️ What is this section?** button too.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Agent Framework / Core Library**: Vanilla script using the `google-genai` SDK; web UI built with Streamlit
- **Models**: Gemini 3.5 Flash (multimodal: reads images and PDFs)
- **External APIs / Tools**: Google Gemini API (Google AI Studio)

---

## Architecture & Data Flow

```
[Bill photo / PDF] --> [main.py] --> reads file bytes + builds prompt
                                         |
                                         v
                                 [Gemini 3.5 Flash]
                                         |
                                         v
[Terminal output] <-- Summary, Charges Explained, Red Flags, Saving Tips
```

`main.py` reads the bill file, detects its type, and sends it along with a structured prompt to Gemini in a single request. The prompt tells the model to use only what is printed on the bill and to say so when something is unreadable, rather than guess.

`app.py` (web app) sends the uploaded bill the same way, but asks Gemini for a JSON response matching a fixed schema (amount, dates, usage, charges, subsidies, red flags, action steps, glossary, tips). The page then shows these as cards instead of one long block of text.

---

## Prerequisites

- Python 3.10 or newer
- pip
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/bill-decoder-agent
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   # Linux/macOS:
   cp .env.example .env
   # Windows (PowerShell):
   Copy-Item .env.example .env
   ```
   Open `.env` and replace `your_gemini_api_key_here` with your real key.

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | *None* | Your Google AI Studio API key |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model used to read the bill |

---

## How to Run

```bash
# Explain a bill in English
python main.py path/to/bill.jpg

# Explain a PDF bill in Kannada
python main.py path/to/bill.pdf --lang Kannada

# Show help
python main.py --help
```

### Web app

```bash
streamlit run app.py
```

Then open http://localhost:8501, upload a bill, pick a language and press **Explain my bill**.

**Deploying publicly (optional):** the app runs on [Streamlit Community Cloud](https://share.streamlit.io). Set the main file to `agents/bill-decoder-agent/app.py`, then add `GEMINI_API_KEY = "your_key"` under the app's **Secrets**. Note that every visitor then uses your API quota.

---

## Example Input & Output

### Example Input
A phone photo of a real BESCOM electricity bill (not included in the repo for privacy):
```
python main.py "bescom bill.jpeg"
```

### Example Output
Real output from a test run with `gemini-3.5-flash`:
```
Decoding bescom bill.jpeg ...

Here is a simple breakdown of your electricity bill:

### 1. BILL SUMMARY
* Type of Bill & Provider: Electricity Bill (BESCOM, Bangalore – LT1 Tariff)
* Billing Period: 01/04/2025 to 01/05/2025 (1 month)
* Total Amount to Pay: ₹ 0.00 (Your net bill shows -₹ 498.00, which means you
  have an advance balance/credit of ₹ 498.00 with the department).
* Due Date: 15/05/2025

### 2. CHARGES EXPLAINED
* Fixed Charges (₹ 145.00): A standard monthly base fee charged for maintaining
  your power connection.
* Energy Charges (₹ 133.40): The cost of the 23 units of electricity you
  consumed this month (at ₹ 5.80 per unit).
* FPPCA Charges (₹ 6.90): A variable charge for adjustments in fuel and power
  purchase costs.
* P & G Surcharge (GOK Portion) (₹ 8.28): A state government surcharge applied
  to your power usage.
* Tax @ 9.0% (₹ 12.01): Government electricity tax added to your subtotal.
* Gruha Jyothi Subsidy (-₹ 305.59): A 100% government discount covering all
  your current usage and taxes because your consumption (23 units) is within
  your free limit (60 units).
* Interest (₹ 21.15): A small interest fee charged on past delayed payments or
  outstanding dues.
* Arrears (-₹ 519.00): An advance credit from previous excess payments, which
  offsets any current minor fees and leaves you with a negative balance.

### 3. RED FLAGS
* Interest Charge: An interest amount of ₹ 21.15 is added to your bill, which
  suggests there was a delayed payment or pending balance in a previous cycle.
* Security Deposit Notice: The bill includes a note stating that an ASD
  (Additional Security Deposit) of ₹ 260 needs to be paid if you haven't paid
  it already.

### 4. MONEY-SAVING TIPS
1. Stay Within Your Entitlement Limit: Your maximum free entitlement is 60
   units. Since you used only 23 units this month, your entire electricity
   charge was subsidized under the Gruha Jyothi Scheme. Keep your monthly usage
   under 60 units to keep paying ₹ 0 for power consumption.
2. Clear Any Pending Security Deposits: Check if the ₹ 260 ASD is still pending
   and pay it on time to avoid extra interest or penal charges on future bills.
```

---

## How to Test

1. Take a clear photo of any recent utility bill (or download the PDF from your provider's website).
2. Run `python main.py <your-bill-file>`.
3. Check that the output contains all four sections and that the total amount and due date match the bill.
4. Try `--lang Kannada` (or Hindi) and confirm the output is in that language.
5. Error handling checks:
   - Run with a missing file → should print `Error: file not found`.
   - Run with a `.txt` file → should print `Unsupported file type`.
   - Run without a `.env` file → should print `GEMINI_API_KEY is not set`.

---

## Known Limitations

- Accuracy depends on photo quality; blurry, dark or cropped photos may be read incorrectly.
- Usage-spike detection only works if the bill itself prints previous months' usage.
- It explains what is printed on the bill; it does not check official tariff rates from the provider.
- The Gemini free tier allows about 20 requests per day per model (seen during testing); the app falls back to backup models, but heavy use can still exhaust the daily quota.
- Explanations of terms (the ℹ️ buttons) come from reference notes and the model's general knowledge, not from the bill itself, and may not cover every regional term.
- Free-tier Gemini API rate limits apply. During high demand Gemini may return a "model is busy" (503) error; wait a minute and retry, or set a different model with `MODEL_NAME` in `.env`.
- New Google AI Studio keys starting with `AQ.` were rejected by the Gemini API during testing (`401 ACCESS_TOKEN_TYPE_UNSUPPORTED`). A standard `AIza...` key from the Google Cloud Console **APIs & Services → Credentials** page worked.
- Tested on Windows; Linux/macOS should work but are untested.
- This is an informational aid, not financial or legal advice. Always confirm disputes with your provider.

---

## Security & Privacy Considerations

- **Secrets Handling**: The API key is loaded from a local `.env` file, which is excluded by `.gitignore`. It is never hard-coded.
- **Data Privacy**: The bill image is sent to the Google Gemini API for processing. Bills contain personal details (name, address, account number), so review [Google's Gemini API terms](https://ai.google.dev/gemini-api/terms) before use. Nothing is stored locally by this tool.
- **Safety**: The agent does not execute any code or shell commands; it only reads the given file and prints text.

---

## Guardrails

This project uses **custom guardrails** written in Python (no third-party guardrail framework). Shared checks live in [`guardrails.py`](guardrails.py).

| Guardrail | Type | How it works |
| :--- | :--- | :--- |
| File type check | Input validation | Only JPG, PNG, WEBP and PDF are accepted (CLI and web). |
| File size limit | Input validation | Files over 10 MB are rejected (`MAX_FILE_MB`, plus `server.maxUploadSize` in `.streamlit/config.toml`). |
| Prompt-injection rule | Input safety | Every prompt tells Gemini to treat text inside the bill as data and to ignore any instructions written in it. |
| Grounding rule | Anti-hallucination | Gemini must use only what is printed on the bill and write "Not shown" instead of guessing. |
| Not-a-bill check | Relevance check | The web app's schema has an `is_bill` field. Non-bill uploads get a friendly message instead of an invented explanation. |
| Structured output | Schema enforcement | The web app forces a JSON response (Pydantic `BillReport` schema), so the answer can't drift off-topic. |
| Date rule + date check | Anti-hallucination / output validation | The prompt gives Gemini today's date and tells it to copy dates exactly as printed, never "correcting" the year. Dates more than 2 years old or 1 year ahead trigger a warning, and the due-date countdown is hidden for them. |
| Term reference notes | Grounding | [`bill_terms.py`](bill_terms.py) gives Gemini correct meanings for common Indian bill terms (e.g. P & G = Pension & Gratuity surcharge, True-up charges, Gruha Jyothi), so abbreviations aren't guessed. |
| Model fallback | Reliability | If a model is busy (503) or out of free quota (429), the app automatically retries with backup models (`gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`). |
| Math check | Output validation | The app checks that the charges add up to the total (±₹2 or 2% for rounding) and warns the user if they don't. |
| Output sanitization | Output safety | All model text is HTML-escaped before it is shown on the page. |
| Usage limits | Abuse / cost protection | Web app: max 5 bills per visit, 20-second cooldown between requests, and 60 bills per day across all visitors. |
| Least privilege | Safety | The model has no tools. It can't run code, call other services or change files. |
| Secrets management | Security | The API key is read from `.env` or Streamlit Secrets and is never committed. |
| Disclaimer | User safety | The page and README state that this is informational, not financial advice. |

**Limitations of the guardrails:** the per-visit limit is stored in the browser session and resets if the page is reloaded; the daily limit resets when the app restarts. The math check only runs when every amount can be read.

---

## Future Improvements

- [ ] Compare two bills (this month vs last month) side by side.
- [ ] Simple web UI with drag-and-drop upload (Streamlit / Gradio).
- [ ] Check charges against official BESCOM/BWSSB tariff tables.
- [ ] Split a shared bill fairly among roommates.

---

## License

*This project is contributed under the repository's open-source license.*
