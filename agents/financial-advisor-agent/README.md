# Autonomous Portfolio & Rebalancing Advisor (Indian Markets)

> An institutional-grade autonomous financial advisor that tracks real-time portfolio holdings, calculates deterministic asset allocation drift, and generates tax-smart, risk-adjusted rebalancing recommendations for Indian resident investors using Google Gemini 2.5 Flash and Python financial tools.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Over time, market movements cause investment portfolios to drift away from their intended strategic asset allocation targets. For Indian retail and high-net-worth investors, rebalancing is complicated by complex capital gains tax rules (Section 112A LTCG with ₹1.25 Lakh threshold, Section 111A STCG at 20%, and slab-rate debt taxation post-April 2023). Most investors either fail to rebalance or incur unnecessary tax liabilities by selling profitable equities instead of utilizing smart cash-inflow rebalancing.
- **Intended Users**: Indian retail investors, wealth managers, financial planners, and developers looking for a production-ready, deterministic agentic framework for portfolio analytics.

### Key Features
- **Deterministic Financial Engine**: Strictly executes all arithmetic, valuations, drift percentages, and share order quantities in Python. The LLM never invents or approximates financial numbers.
- **Conversational Advisor & Multi-Turn Memory**: Supports continuous dialogue in natural language, understanding Indian colloquial denominations (e.g., *"I have 100 stocks of TCS and my available cash is 50k (means rs.50000)"*), persisting portfolio state across turns, and flagging asset concentration risks.
- **Real-Time Indian Market Data**: Queries Yahoo Finance (`yfinance`) for NSE/BSE equities, broad market ETFs (`NIFTYBEES.NS`), US tech ETFs (`MON100.NS`), Gold ETFs (`GOLDBEES.NS`), and Liquid debt instruments (`LIQUIDBEES.NS`), with resilient par-value handling for government bonds and cash reserves.
- **Zero-Network / Offline Fallback Guardrail**: Seamless fallback to curated mock market data whenever offline or experiencing network timeouts, ensuring zero unhandled crashes.
- **Strategic Trade Rationales (Why Buy / Sell Each Stock)**: Automatically explains the exact institutional and strategic rationale behind every single buy, sell, or hold recommendation (e.g., de-risking single-stock concentration, hedging macro inflation and currency depreciation via Gold ETFs, fixed income volatility dampening, or re-aligning overweight positions).
- **Tax-Aware Inflow Rebalancing**: Computes optimal deployment of fresh capital (lump sums, SIPs, bonuses) into underweighted assets first, curing drift without triggering taxable sell events.
- **Compliance Guardrail**: Every analysis includes a prominent, mandatory compliance disclaimer banner aligned with SEBI advisory norms.
- **Interactive CLI & Rich Presentation**: Beautiful ASCII and Unicode tables using `tabulate` with presets for Aggressive, Moderate, and Conservative asset allocation profiles.

---

## Technical Stack

- **Language & Runtime**: Python 3.9+ / 3.11+
- **Agent Framework / Core Library**: Official `google-genai` SDK (`gemini-2.5-flash`), Python function calling
- **Financial & Data Libraries**: `yfinance` (real-time market data), `pandas` (data operations), `pydantic` (validation)
- **CLI Presentation**: `tabulate` (terminal tables), `python-dotenv` (environment configuration)
- **External APIs**: Google Gemini API, Yahoo Finance

---

## Architecture & Data Flow

```
[User Request / CLI Preset]
           │
           ▼
[FinancialAdvisorAgent (Gemini 2.5 Flash)]
           │
           ├── (Function Calling) ──▶ [portfolio_tools.fetch_live_prices]
           │                                 │
           │                                 └──▶ yfinance API / Offline Fallback
           │
           ├── (Function Calling) ──▶ [portfolio_tools.calculate_portfolio_drift]
           │                                 │
           │                                 └──▶ Deterministic Allocation Math
           │
           ├── (Function Calling) ──▶ [portfolio_tools.calculate_rebalance_orders]
           │                                 │
           │                                 └──▶ Whole Share Orders & Cash Deployment
           │
           ▼
[Synthesized Advisor Report + Formatted CLI Tables + Tax & Compliance Guardrails]
```

---

## Prerequisites

Before running this project, ensure you have:
- **Python**: Python 3.9, 3.10, 3.11, or 3.12 installed.
- **Package Manager**: `pip` (or `uv`).
- **Gemini API Key** *(Optional for deterministic mode, recommended for AI advisory)*: Get a free key at [Google AI Studio](https://aistudio.google.com/).

---

## Installation & Setup

1. **Navigate to the agent directory:**
   ```bash
   cd agents/financial-advisor-agent
   ```

2. **Set up a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate       # On Linux/macOS
   # Or on Windows: .venv\Scripts\activate

   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment configuration:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to insert your Gemini API key:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   MODEL_NAME=gemini-2.5-flash
   USE_MOCK_DATA=0
   ```
   *(Note: If no API key is configured, the agent gracefully defaults to local deterministic analysis mode without errors).*

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Optional | *None* | Google AI Studio API key for Gemini 2.5 Flash reasoning |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Identifier of the Gemini model to use |
| `USE_MOCK_DATA` | No | `0` | Set to `1` to force offline mock data mode (ideal for air-gapped testing) |

---

## How to Run

### 1. Conversational Chat Mode (Interactive Natural Language)
Chat naturally with the advisor and manage your portfolio across multiple conversational turns:
```bash
python main.py --chat
```
In conversational mode, you can type natural Indian financial expressions:
* *"I have 100 stocks of TCS and my available cash is 50k (means rs.50000)"*
* *"Also add 50 shares of Reliance and 200 units of Goldbees"*
* *"What rebalancing orders do I need if I infuse 25k fresh cash?"*
* *"What is my LTCG tax liability if I sell 20 TCS shares?"*

The agent maintains portfolio state across turns, understands Indian colloquial denominations (`50k` = ₹50,000, `1L` = ₹1,00,000, `2 cr` = ₹2,00,00,000), evaluates concentration risks, and provides deterministic drift tables and rebalancing plans.

**Investment Mode Selection**:
Whenever you provide investment info (e.g., *"I have 100 stocks of TCS and available cash is 50k"*), the system prompts you to select your preferred investment mode / risk profile before calculating rebalancing:
- **[1] Aggressive Growth** (50% Indian Equity, 15% Int'l, 20% Debt, 10% Gold, 5% Cash)
- **[2] Moderate Balanced** (40% Indian Equity, 10% Int'l, 35% Debt, 10% Gold, 5% Cash)
- **[3] Conservative Preservation** (20% Indian Equity, 5% Int'l, 55% Debt, 15% Gold, 5% Cash)
- **[4] Custom Percentages**

You can also switch models anytime in chat by typing `mode` or asking naturally (e.g. *"Switch to Moderate Balanced"* or *"Rebalance with Conservative model"*).

### 2. Interactive Menu
Launch the interactive CLI menu:
```bash
python main.py
```
From the menu:
- **Select `[1]` for Conversational Advisor Chat Mode**
- **Select `[0]` to Exit**

### 3. Direct User Input via Command-Line Flags
Pass your invested holdings directly through the command line:
```bash
# Analyze your custom holdings against the Aggressive Growth model:
python main.py --input "RELIANCE:50, TCS:30, INFY:40, GOLDBEES:200, CASH:50000"

# Combine with fresh cash infusion for tax-smart rebalancing:
python main.py --input "RELIANCE:50, TCS:30, GOLDBEES:200, CASH:50000" --cash 50000

# Force offline/mock mode:
python main.py --input "RELIANCE:50, TCS:30, GOLDBEES:200, CASH:50000" --mock
```

### 4. Run Predefined Demo Presets Directly
- **Preset 1 (Aggressive Growth: 50% Equity, 15% Int'l, 20% Debt, 10% Gold, 5% Cash)**:
  ```bash
  python main.py --preset 1
  ```
- **Preset 2 (Moderate Balanced: 40% Equity, 10% Int'l, 35% Debt, 10% Gold, 5% Cash)**:
  ```bash
  python main.py --preset 2
  ```
- **Preset 3 (Cash Inflow Rebalancing with ₹1,00,000 fresh cash)**:
  ```bash
  python main.py --preset 3
  ```
- **Custom Cash Infusion**:
  ```bash
  python main.py --preset 1 --cash 75000
  ```

---

## Example Input & Output

### Example Input
Analyze the sample Indian portfolio against an Aggressive Growth model (50% Indian Equity, 15% International Equity, 20% Debt, 10% Gold, 5% Cash) with a fresh cash infusion of ₹1,00,000.

### Example Output

```text
================================================================================
               📊 PORTFOLIO HOLDINGS & ASSET CLASS DRIFT
================================================================================
Total Portfolio Value: ₹19,22,900.00
Status: ⚠️  REBALANCE RECOMMENDED (Holdings drifted beyond ±1.5%)

[Asset Class Allocation Summary]
╒══════════════════════╤═════════════════╤═════════════╤════════════╤═══════════╤═════════════════╤═════════════════╕
│ Asset Class          │ Current Value   │ Current %   │ Target %   │ Drift %   │ Value Delta     │ Status          │
╞══════════════════════╪═════════════════╪═════════════╪════════════╪═══════════╪═════════════════╪═════════════════╡
│ Indian Equity        │ ₹9,35,940.00    │ 48.67%      │ 50.00%     │ -1.33%    │ -₹25,510.00     │ 🟢 BALANCED     │
├──────────────────────┼─────────────────┼─────────────┼────────────┼───────────┼─────────────────┼─────────────────┤
│ International Equity │ ₹2,59,200.00    │ 13.48%      │ 15.00%     │ -1.52%    │ -₹29,235.00     │ 🔵 UNDERWEIGHT  │
├──────────────────────┼─────────────────┼─────────────┼────────────┼───────────┼─────────────────┼─────────────────┤
│ Fixed Income / Debt  │ ₹4,55,000.00    │ 23.66%      │ 20.00%     │ +3.66%    │ ₹70,420.00      │ 🔴 OVERWEIGHT   │
├──────────────────────┼─────────────────┼─────────────┼────────────┼───────────┼─────────────────┼─────────────────┤
│ Gold / Commodities   │ ₹1,22,760.00    │ 6.38%       │ 10.00%     │ -3.62%    │ -₹69,530.00     │ 🔵 UNDERWEIGHT  │
├──────────────────────┼─────────────────┼─────────────┼────────────┼───────────┼─────────────────┼─────────────────┤
│ Cash & Equivalents   │ ₹1,50,000.00    │ 7.80%       │ 5.00%      │ +2.80%    │ ₹53,855.00      │ 🔴 OVERWEIGHT   │
╘══════════════════════╧═════════════════╧═════════════╧════════════╧═══════════╧═════════════════╧═════════════════╛

================================================================================
               🎯 ACTIONABLE REBALANCING ORDER BOOK
================================================================================
Current Value:     ₹19,22,900.00
Cash Infusion:     ₹1,00,000.00
Expanded Target:   ₹20,22,900.00
Strategy:          High Inflow Efficiency

[Executable Rebalancing Orders]
╒══════════╤═══════════════╤════════════════════════════╤══════════╤══════════════╤═══════════════╤════════════════╤════════════╕
│ Action   │ Ticker        │ Instrument                 │ Shares   │ Unit Price   │ Trade Value   │ Post-Rebal %   │ Target %   │
╞══════════╪═══════════════╪════════════════════════════╪══════════╪══════════════╪═══════════════╪════════════════╪════════════╡
│ 🟢 BUY   │ RELIANCE.NS   │ Reliance Industries Limit  │ 9        │ ₹1,285.50    │ ₹11,569.50    │ 8.20%          │ 50.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🟢 BUY   │ TCS.NS        │ Tata Consultancy Services  │ 4        │ ₹3,520.00    │ ₹14,080.00    │ 11.14%         │ 50.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🟢 BUY   │ HDFCBANK.NS   │ HDFC Bank Limited          │ 12       │ ₹1,680.00    │ ₹20,160.00    │ 13.45%         │ 50.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🟢 BUY   │ NIFTYBEES.NS  │ Nippon India ETF Nifty 50  │ 96       │ ₹265.40      │ ₹25,478.40    │ 17.00%         │ 50.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🟢 BUY   │ MON100.NS     │ Motilal Oswal Nasdaq 100 E │ 255      │ ₹172.80      │ ₹44,064.00    │ 14.99%         │ 15.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🔴 SELL  │ LIQUIDBEES.NS │ Nippon India ETF Liquid Be │ 27       │ ₹1,000.00    │ ₹27,000.00    │ 11.02%         │ 20.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🔴 SELL  │ GOI_BONDS     │ Government of India 7.18%  │ 22       │ ₹1,025.00    │ ₹22,550.00    │ 9.02%          │ 20.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🟢 BUY   │ GOLDBEES.NS   │ Nippon India ETF Gold BeES │ 1,166    │ ₹68.20       │ ₹79,521.20    │ 10.00%         │ 10.00%     │
├──────────┼───────────────┼────────────────────────────┼──────────┼──────────────┼───────────────┼────────────────┼────────────┤
│ 🔴 SELL  │ INR_CASH      │ High Yield Bank Savings /  │ 48,855   │ ₹1.00        │ ₹48,855.00    │ 5.00%          │ 5.00%      │
╘══════════╧═══════════════╧════════════════════════════╧══════════╧══════════════╧═══════════════╧════════════════╧════════════╛

[Strategic Trade Rationales (Why Buy or Sell Each Stock)]
  • 🟢 BUY RELIANCE.NS (9 shares / ₹11,569.50):
    ↳ Underweight by -41.8%. Accumulate RELIANCE.NS to build up towards target 50.0%.
  • 🟢 BUY TCS.NS (4 shares / ₹14,080.00):
    ↳ Underweight by -38.9%. Accumulate TCS.NS to build up towards target 50.0%.
  • 🟢 BUY HDFCBANK.NS (12 shares / ₹20,160.00):
    ↳ Underweight by -36.5%. Accumulate HDFCBANK.NS to build up towards target 50.0%.
  • 🟢 BUY NIFTYBEES.NS (96 shares / ₹25,478.40):
    ↳ Underweight by -33.0%. Accumulate NIFTYBEES.NS to build up towards target 50.0%.
  • 🟢 BUY MON100.NS (255 shares / ₹44,064.00):
    ↳ Underweight by -1.5%. Add international equity units to reach target 15.0%.
  • 🔴 SELL LIQUIDBEES.NS (27 shares / ₹27,000.00):
    ↳ Trim position as Fixed Income / Debt is overweight by +3.7%. Rebalance back to strategic 20.0% model.
  • 🔴 SELL GOI_BONDS (22 shares / ₹22,550.00):
    ↳ Trim position as Fixed Income / Debt is overweight by +3.7%. Rebalance back to strategic 20.0% model.
  • 🟢 BUY GOLDBEES.NS (1,166 shares / ₹79,521.20):
    ↳ Underweight by -3.6%. Accumulate Gold ETF to reach target 10.0% for geopolitical hedging and inflation resistance.
  • 🔴 SELL INR_CASH (48,855 shares / ₹48,855.00):
    ↳ Cash reserve is overweight (7.8% vs 5.0% target). Deploy idle cash into productive assets to prevent real inflation drag (~5% CPI).

================================================================================
⚠️  COMPLIANCE DISCLAIMER
For educational and informational purposes only. Not certified financial advice.
Investments in securities market are subject to market risks. Read all scheme-
related documents carefully. Consult a SEBI-registered Investment Adviser (RIA)
before executing any financial or rebalancing transactions.
================================================================================
```

---

## How to Test

Run the built-in automated verification suite that tests JSON parsing, price fetching, drift math, order calculation, and agent reporting:

```bash
python main.py --test
```

Expected output:
```text
================================================================================
               🧪 RUNNING AUTOMATED SELF-CHECK
================================================================================
✓ Test 1: Portfolio data loaded successfully.
✓ Test 2: Live price lookup succeeded (Source: live_yfinance).
✓ Test 3: Drift math computed deterministically. Total Val: ₹19,53,194.00
✓ Test 4: Rebalance orders generated successfully. Total Buys: ₹2,90,336.38
✓ Test 5: User stock input parser accurately extracted 5 holdings.
✓ Test 6: Advisor Agent synthesized report with compliance banner.

================================================================================
              🎉 ALL 6 SELF-CHECK TESTS PASSED!
================================================================================
```

---

## Indian Regulatory & Tax Guardrails

The agent incorporates core Indian tax and regulatory rules:

1. **Equity Taxation (Section 112A & 111A)**:
   - **LTCG**: Listed equities/equity ETFs held > 12 months are subject to 12.5% tax on aggregate annual capital gains exceeding ₹1.25 Lakh.
   - **STCG**: Listed equity sold within 12 months is taxed at 20%.
2. **Specified Debt Mutual Funds & Fixed Income**:
   - Capital gains from non-equity debt mutual funds acquired after April 1, 2023, are treated as short-term capital gains and taxed at the investor's applicable marginal income tax slab.
3. **Gold ETFs & SGBs**:
   - Sovereign Gold Bonds (SGBs) held to full maturity (8 years) are capital gains tax-exempt for individuals. Gold ETFs are taxed under applicable precious metal capital gains rates.
4. **Cash Inflow Prioritization**:
   - Rather than selling appreciated equities and triggering capital gains tax and transaction costs (STT, stamp duty, brokerages), the agent prioritizes directing fresh cash infusions (SIPs, bonus, savings) to buy underweighted instruments.

---

## Known Limitations

- **Whole Share Rounding**: Equity share transactions are rounded down to integer share units. Minimal residual cash remaining (< 0.5% of trade value) is held in liquid cash.
- **Yahoo Finance Latency**: NSE/BSE prices from `yfinance` may be delayed by up to 15 minutes during live market hours.
- **Tax Status Variability**: While general Indian tax rules are provided, individual tax slabs and specific grandfathering provisions (e.g. pre-Jan 2018 equity acquisition) require personal verification.

---

## Security & Privacy Considerations

- **Zero Hardcoded Secrets**: All API keys are loaded via `.env` or system environment variables.
- **Air-Gapped Operation**: Supports full deterministic operation and mock market data (`--mock`) without making any outbound HTTP requests.
- **Data Privacy**: No portfolio data is logged to remote third-party analytics services. Only anonymized prompt payloads are transmitted to the configured Gemini endpoint when `GEMINI_API_KEY` is provided.

---

## Future Improvements

- [ ] Support direct integration with Indian broker APIs (Zerodha Kite, Groww, Upstox) for 1-click execution.
- [ ] Incorporate mutual fund NAV lookups via AMFI daily NAV feeds.
- [ ] Add Monte Carlo retirement simulation for multi-decade goal tracking.
- [ ] Export rebalance reports directly to PDF or Excel workbooks.

---

## License

This project is contributed under the repository's open-source license.
