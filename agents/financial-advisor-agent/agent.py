"""
Autonomous Portfolio & Rebalancing Advisor Agent
================================================
Orchestrates Gemini 2.5 Flash with deterministic Python financial tools.
Enforces that all mathematical calculations (valuations, percentages, drift,
share orders) are executed through deterministic Python tools, while providing
risk-adjusted, tax-aware insights tailored for Indian resident investors.
"""

from __future__ import annotations
import os
import json
import warnings
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Suppress harmless OpenSSL warnings
warnings.filterwarnings("ignore")

from portfolio_tools import (
    fetch_live_prices,
    calculate_portfolio_drift,
    calculate_rebalance_orders,
    format_inr,
    parse_holdings_shorthand,
    normalize_indian_ticker,
    parse_conversational_text,
    parse_indian_currency_expression
)

# Load environment variables
load_dotenv()

COMPLIANCE_BANNER = """================================================================================
⚠️  COMPLIANCE DISCLAIMER
For educational and informational purposes only. Not certified financial advice.
Investments in securities market are subject to market risks. Read all scheme-
related documents carefully. Consult a SEBI-registered Investment Adviser (RIA)
before executing any financial or rebalancing transactions.
================================================================================
"""

SYSTEM_INSTRUCTION = f"""
You are the "Autonomous Portfolio & Rebalancing Advisor", an expert institutional-grade portfolio analyst specialized for Indian resident individual investors.

CORE DIRECTIVES & COMPLIANCE:
1. DETERMINISTIC CALCULATIONS ONLY:
   - You must NEVER calculate or estimate percentages, portfolio valuations, drift numbers, or share trade quantities yourself.
   - You MUST call the deterministic Python tools (`fetch_live_prices`, `calculate_portfolio_drift`, `calculate_rebalance_orders`) to compute all financial figures.
   - Quote exact figures directly from tool responses.

2. MANDATORY COMPLIANCE BANNER:
   - Every single response you produce MUST begin and conclude with the clear disclaimer:
   "{COMPLIANCE_BANNER}"

3. INDIAN RESIDENT TAX & REGULATORY AWARENESS:
   - **Equity Taxation**:
     * Long-Term Capital Gains (LTCG) under Section 112A: Taxed at 12.5% for gains exceeding ₹1.25 Lakh per financial year (holding period > 12 months).
     * Short-Term Capital Gains (STCG) under Section 111A: Taxed at 20% (holding period <= 12 months).
   - **Fixed Income / Debt**:
     * Gains from specified debt funds / market debt instruments are taxed as per the investor's applicable marginal income tax slab.
   - **Gold & Commodities**:
     * Sovereign Gold Bonds (SGB) held to maturity are tax-exempt on capital gains; Gold ETFs/Funds taxed as per applicable capital gains rules.
   - **Cash-Inflow Rebalancing Preference**:
     * ALWAYS evaluate whether drift can be mitigated by directing fresh capital (cash infusion, SIPs, bonuses) into underweighted asset classes before recommending selling appreciated holdings, which would trigger avoidable capital gains tax and transaction friction (STT, stamp duty, brokerage).

4. MANDATORY TRADE RATIONALE (EXPLAIN WHY BUY OR SELL):
   - For every recommended BUY or SELL order, you MUST provide an explicit, analytical rationale explaining WHY the investor should execute it:
     * WHY SELL: Detail asset class overweight drift, single-stock concentration de-risking, re-aligning with target model, locking in gains, or deploying surplus cash.
     * WHY BUY: Detail closing underweight asset class gaps, macro inflation/currency hedging with Gold, fixed income volatility dampening, or global secular tech growth.

5. COMMUNICATION STYLE:
   - Highly professional, analytical, objective, and risk-aware.
   - Break down analysis into:
     1. Executive Portfolio Health Check
     2. Asset Class Drift Breakdown
     3. Actionable Rebalancing Plan (with Buy/Sell/Hold orders)
     4. Strategic Trade Rationales (Why Buy or Sell Each Stock)
     5. Indian Tax Efficiency & Execution Strategy
"""


class FinancialAdvisorAgent:
    """
    Financial Advisor Agent powered by Google Gemini SDK (gemini-2.5-flash)
    with automatic tool calling and deterministic fallback.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash").strip()
        self.has_valid_api_key = bool(self.api_key and not self.api_key.startswith("your_"))
        self.client = None

        if self.has_valid_api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                warnings.warn(f"Failed to initialize Gemini Client: {e}. Falling back to deterministic mode.")
                self.has_valid_api_key = False

    def parse_user_holdings(self, user_input: str) -> List[Dict[str, Any]]:
        """
        Parses user input describing their invested stocks into structured holdings.
        Supports free-form text ('I hold 50 shares of Reliance, 100 TCS, 200 GoldBeES')
        via Gemini semantic extraction with regex/shorthand fallback.
        """
        user_input = user_input.strip()
        if not user_input:
            return []

        # Attempt Gemini semantic extraction if API key is active
        if self.has_valid_api_key and self.client:
            try:
                extract_prompt = (
                    f"Extract all stock, ETF, bond, and cash holdings from this user's text:\n"
                    f"\"{user_input}\"\n\n"
                    f"Rules:\n"
                    f"1. Convert company/stock names to standard Indian NSE tickers with .NS suffix (e.g. Reliance -> RELIANCE.NS, TCS -> TCS.NS, Infosys -> INFY.NS, HDFC Bank -> HDFCBANK.NS, GoldBees -> GOLDBEES.NS, LiquidBees -> LIQUIDBEES.NS, Nasdaq ETF -> MON100.NS).\n"
                    f"2. For cash/savings/FD, use ticker 'INR_CASH'.\n"
                    f"3. Classify each asset_class as exactly one of: 'Indian Equity', 'International Equity', 'Fixed Income / Debt', 'Gold / Commodities', 'Cash & Equivalents'.\n"
                    f"4. Format response strictly as a JSON array of objects with keys: ticker, name, shares, asset_class, sector.\n"
                    f"Output ONLY valid JSON."
                )
                resp = self.client.models.generate_content(
                    model=self.model_name,
                    contents=extract_prompt
                )
                text = resp.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(text)
                if isinstance(parsed, list) and len(parsed) > 0:
                    for h in parsed:
                        h["ticker"] = normalize_indian_ticker(h.get("ticker", ""))
                        h["shares"] = float(h.get("shares", 0))
                    return parsed
            except Exception as e:
                warnings.warn(f"Gemini holdings parsing fallback: {e}")

        # Deterministic fallback parser
        return parse_holdings_shorthand(user_input)

    def run_deterministic_analysis(
        self,
        current_holdings: List[Dict[str, Any]],
        target_allocations: Dict[str, float],
        cash_infusion: float = 0.0,
        user_query: Optional[str] = None
    ) -> str:
        """
        Runs a comprehensive deterministic portfolio review and rebalance plan
        without requiring an external LLM API call.
        """
        # Execute tools deterministically
        drift_data = calculate_portfolio_drift(current_holdings, target_allocations)
        rebalance_data = calculate_rebalance_orders(current_holdings, target_allocations, cash_infusion)

        total_val_str = drift_data.get("total_portfolio_value_formatted", "N/A")
        rebal_rec = drift_data.get("rebalance_recommended", False)
        new_total_str = rebalance_data.get("new_total_value_formatted", total_val_str)

        lines = [
            COMPLIANCE_BANNER,
            "## 1. Executive Portfolio Health Check",
            f"- **Current Portfolio Value**: {total_val_str}",
            f"- **Rebalance Status**: {'⚠️ ACTION RECOMMENDED (Significant Asset Drift Detected)' if rebal_rec else '✅ BALANCED (Holdings within ±1.5% target tolerance)'}",
        ]

        if cash_infusion > 0:
            lines.extend([
                f"- **Fresh Cash Infusion**: {format_inr(cash_infusion)}",
                f"- **Expanded Portfolio Value**: {new_total_str}",
                "- **Rebalancing Strategy**: **Cash Inflow Prioritization** (Directing fresh capital into underweighted assets to minimize taxable sales)"
            ])

        lines.extend([
            "",
            "## 2. Asset Class Allocation & Drift Analysis",
            "| Asset Class | Current Value | Current % | Target % | Drift % | Valuation Delta | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ])

        for ac in drift_data.get("asset_class_drift", []):
            status_emoji = "🔴" if ac["status"] == "OVERWEIGHT" else ("🔵" if ac["status"] == "UNDERWEIGHT" else "🟢")
            lines.append(
                f"| {ac['asset_class']} | {ac['current_value_formatted']} | {ac['current_pct']:.2f}% | "
                f"{ac['target_pct']:.2f}% | {ac['drift_pct']:+.2f}% | {ac['value_drift_formatted']} | "
                f"{status_emoji} {ac['status']} |"
            )

        lines.extend([
            "",
            "## 3. Recommended Rebalancing Action Orders",
            "| Action | Ticker | Instrument Name | Shares to Trade | Unit Price | Trade Value | Post-Rebal % | Target % |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ])

        for ord_item in rebalance_data.get("orders", []):
            if ord_item["action"] == "HOLD":
                continue
            act_icon = "🟢 BUY" if ord_item["action"] == "BUY" else "🔴 SELL"
            lines.append(
                f"| {act_icon} | `{ord_item['ticker']}` | {ord_item['name'][:28]} | "
                f"{ord_item['shares_to_trade']:,} | {ord_item['unit_price_formatted']} | "
                f"{ord_item['order_value_formatted']} | {ord_item['post_trade_pct']:.2f}% | {ord_item['target_pct']:.2f}% |"
            )

        lines.extend([
            "",
            "### 💡 Strategic Trade Rationales (Why Buy or Sell Each Stock):"
        ])
        for ord_item in rebalance_data.get("orders", []):
            if ord_item["action"] == "HOLD":
                continue
            act_icon = "🟢 BUY" if ord_item["action"] == "BUY" else "🔴 SELL"
            rat = ord_item.get("rationale", "Rebalance to align with target asset allocation.")
            lines.append(f"- **{act_icon} `{ord_item['ticker']}`** ({ord_item['shares_to_trade']:,} shares / {ord_item['order_value_formatted']}): {rat}")

        lines.extend([
            "",
            "### Trade Summary Metrics:",
            f"- **Total Capital Required for Buys**: {rebalance_data.get('total_buy_value_formatted')}",
            f"- **Capital Generated from Sells**: {rebalance_data.get('total_sell_value_formatted')}",
            f"- **Net Additional Cash Required**: {rebalance_data.get('net_cash_required_formatted')}",
            f"- **Unallocated Cash Balance**: {rebalance_data.get('unallocated_cash_formatted')}",
            "",
            "## 4. Indian Resident Tax & Execution Guidance",
            "1. **Capital Gains Consideration**:",
            "   - **Equity Holdings (LTCG vs STCG)**: Before executing sell orders on Indian equities/ETFs, verify holding periods. Under Section 112A, LTCG (>12 months) enjoys an annual exemption of ₹1.25 Lakh (taxed at 12.5% thereafter), whereas STCG is taxed at 20% under Section 111A.",
            "   - **Tax Harvesting**: If unrealized losses exist in other holdings, consider tax-loss harvesting to offset gains.",
            "2. **Inflow Rebalancing Advantage**:",
            "   - By channeling fresh capital or ongoing SIPs directly into underweighted assets (e.g. Indian Large Cap & Gold), you can naturally bring the portfolio back into equilibrium over 2–4 months without triggering immediate capital gains tax liabilities.",
            "3. **Fixed Income Strategy**:",
            "   - Since debt mutual fund capital gains are now taxed at marginal income tax slab rates, hold core sovereign allocations (like GOI bonds or Arbitrage/Liquid funds) according to your tax bracket.",
            "",
            COMPLIANCE_BANNER
        ])

        return "\n".join(lines)

    def analyze_portfolio(
        self,
        current_holdings: List[Dict[str, Any]],
        target_allocations: Dict[str, float],
        cash_infusion: float = 0.0,
        user_query: Optional[str] = None
    ) -> str:
        """
        Analyzes the portfolio using Gemini 2.5 Flash with tool calling if API key is present;
        otherwise runs the deterministic financial evaluation engine directly.
        """
        if not self.has_valid_api_key or self.client is None:
            # Deterministic execution mode
            return self.run_deterministic_analysis(
                current_holdings=current_holdings,
                target_allocations=target_allocations,
                cash_infusion=cash_infusion,
                user_query=user_query
            )

        try:
            from google.genai import types

            # Define tool bindings
            tools = [fetch_live_prices, calculate_portfolio_drift, calculate_rebalance_orders]

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools,
                temperature=0.2,
            )

            prompt = (
                f"Please conduct an autonomous portfolio drift and rebalancing review for an Indian resident investor.\n\n"
                f"### Current Portfolio Holdings:\n```json\n{json.dumps(current_holdings, indent=2)}\n```\n\n"
                f"### Target Asset Allocation Model:\n```json\n{json.dumps(target_allocations, indent=2)}\n```\n\n"
                f"### New Cash Infusion: ₹{cash_infusion:,.2f}\n"
            )

            if user_query:
                prompt += f"\n### Specific Investor Query / Instructions:\n{user_query}\n"

            prompt += (
                "\nINSTRUCTIONS:\n"
                "1. Invoke `calculate_portfolio_drift` and `calculate_rebalance_orders` to get deterministic calculations.\n"
                "2. Present the findings clearly with markdown tables.\n"
                "3. Provide Indian resident tax-aware rebalancing advice.\n"
                "4. Include the compliance disclaimer banner at the beginning and end."
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )

            resp_text = response.text or ""
            if COMPLIANCE_BANNER.strip() not in resp_text:
                resp_text = f"{COMPLIANCE_BANNER}\n{resp_text}\n{COMPLIANCE_BANNER}"

            return resp_text

        except Exception as e:
            # On any API error or quota limit, fall back gracefully to deterministic engine
            warnings.warn(f"Gemini API invocation encountered an issue: {e}. Executing deterministic fallback engine.")
            return self.run_deterministic_analysis(
                current_holdings=current_holdings,
                target_allocations=target_allocations,
                cash_infusion=cash_infusion,
                user_query=user_query
            )

    def start_conversational_session(self) -> "ConversationalAdvisorSession":
        """Starts an interactive multi-turn conversational advisory session."""
        return ConversationalAdvisorSession(self)


class ConversationalAdvisorSession:
    """
    Maintains a multi-turn conversational session with portfolio memory.
    Understands Indian financial colloquialisms (e.g. '50k', '1 lakh', '100 stocks of TCS')
    and orchestrates Gemini 2.5 Flash function calling or deterministic fallback.
    """

    DEFAULT_TARGETS = {
        "Aggressive Growth": {
            "Indian Equity": 0.50,
            "International Equity": 0.15,
            "Fixed Income / Debt": 0.20,
            "Gold / Commodities": 0.10,
            "Cash & Equivalents": 0.05
        },
        "Moderate Balanced": {
            "Indian Equity": 0.40,
            "International Equity": 0.10,
            "Fixed Income / Debt": 0.35,
            "Gold / Commodities": 0.10,
            "Cash & Equivalents": 0.05
        },
        "Conservative Preservation": {
            "Indian Equity": 0.20,
            "International Equity": 0.05,
            "Fixed Income / Debt": 0.55,
            "Gold / Commodities": 0.15,
            "Cash & Equivalents": 0.05
        }
    }

    def __init__(self, agent: FinancialAdvisorAgent):
        self.agent = agent
        self.holdings_map: Dict[str, Dict[str, Any]] = {}
        self.target_model_name = "Aggressive Growth"
        self.target_allocations = dict(self.DEFAULT_TARGETS["Aggressive Growth"])
        self.cash_infusion = 0.0
        self.gemini_chat = None
        self.mode_selected = False

        if self.agent.has_valid_api_key and self.agent.client:
            try:
                from google.genai import types
                tools = [fetch_live_prices, calculate_portfolio_drift, calculate_rebalance_orders]
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION + (
                        "\nCONVERSATIONAL INTERACTION GUIDELINES:\n"
                        "1. You are in interactive conversational mode. Listen carefully to user messages.\n"
                        "2. Understand Indian financial terminology and numbers: '50k' = ₹50,000, '1L' / '1 lakh' = ₹1,00,000, '1 cr' = ₹1,00,00,000.\n"
                        "3. When the user mentions stocks (e.g. '100 stocks of TCS', '50 shares of Reliance'), track them with canonical tickers (TCS.NS, RELIANCE.NS).\n"
                        "4. When the user mentions cash (e.g. 'available cash is 50k'), track it under 'INR_CASH'.\n"
                        "5. Proactively call `calculate_portfolio_drift` and `calculate_rebalance_orders` when portfolio data is present.\n"
                        "6. Be welcoming, risk-aware, and provide SEBI-aligned tax-smart advice (highlighting LTCG vs STCG, and inflow rebalancing).\n"
                    ),
                    tools=tools,
                    temperature=0.3,
                )
                self.gemini_chat = self.agent.client.chats.create(
                    model=self.agent.model_name,
                    config=config
                )
            except Exception as e:
                warnings.warn(f"Failed to start Gemini chat session: {e}. Falling back to deterministic chat engine.")
                self.gemini_chat = None

    def set_target_model(self, model_name: str, custom_allocations: Optional[Dict[str, float]] = None):
        """Sets the active target asset allocation model and marks mode_selected."""
        if custom_allocations:
            self.target_model_name = model_name
            self.target_allocations = dict(custom_allocations)
            self.mode_selected = True
        elif model_name in self.DEFAULT_TARGETS:
            self.target_model_name = model_name
            self.target_allocations = dict(self.DEFAULT_TARGETS[model_name])
            self.mode_selected = True

    def get_holdings_list(self) -> List[Dict[str, Any]]:
        """Returns the current accumulated list of holdings."""
        return list(self.holdings_map.values())

    def chat(self, user_message: str) -> str:
        """
        Processes a conversational message from the user, updates the portfolio state,
        and generates an advisory response.
        """
        # Parse entities from message
        parsed_data = parse_conversational_text(user_message)

        newly_added = []
        for stock in parsed_data.get("stocks", []):
            t = stock["ticker"]
            self.holdings_map[t] = stock
            newly_added.append(f"{stock['shares']} shares of `{t}`")

        # Update cash reserve if mentioned
        if parsed_data.get("cash", 0.0) > 0:
            cash_val = parsed_data["cash"]
            self.holdings_map["INR_CASH"] = {
                "ticker": "INR_CASH",
                "name": "Liquid Savings / Bank Reserve",
                "shares": cash_val,
                "asset_class": "Cash & Equivalents"
            }
            newly_added.append(f"{format_inr(cash_val)} in liquid cash")

        # Update cash infusion if mentioned
        if parsed_data.get("cash_infusion", 0.0) > 0:
            self.cash_infusion = parsed_data["cash_infusion"]

        # Update target model if mentioned
        if parsed_data.get("target_model"):
            m_name = parsed_data["target_model"]
            self.target_model_name = m_name
            self.target_allocations = dict(self.DEFAULT_TARGETS[m_name])
            self.mode_selected = True

        current_holdings = self.get_holdings_list()

        # If Gemini chat session is active, delegate with rich portfolio state context
        if self.gemini_chat:
            try:
                context_prompt = (
                    f"User message: \"{user_message}\"\n\n"
                    f"Current Portfolio State:\n```json\n{json.dumps(current_holdings, indent=2)}\n```\n"
                    f"Target Allocation Model ({self.target_model_name}):\n```json\n{json.dumps(self.target_allocations, indent=2)}\n```\n"
                    f"Fresh Cash Infusion: {format_inr(self.cash_infusion)}\n\n"
                    f"INSTRUCTIONS: Respond naturally to the user. If holdings exist, call `calculate_portfolio_drift` "
                    f"and `calculate_rebalance_orders` to show accurate numbers. Always include the compliance disclaimer banner."
                )
                resp = self.gemini_chat.send_message(context_prompt)
                resp_text = resp.text or ""
                if COMPLIANCE_BANNER.strip() not in resp_text:
                    resp_text = f"{COMPLIANCE_BANNER}\n{resp_text}\n{COMPLIANCE_BANNER}"
                return resp_text
            except Exception as e:
                warnings.warn(f"Gemini chat turn error: {e}. Falling back to deterministic chat response.")

        # Deterministic conversational engine fallback
        return self._generate_deterministic_chat_response(user_message, newly_added)

    def _generate_deterministic_chat_response(self, user_message: str, newly_added: List[str]) -> str:
        """Builds a comprehensive, natural deterministic advisor reply."""
        holdings = self.get_holdings_list()
        lines = [COMPLIANCE_BANNER]

        if not holdings:
            lines.extend([
                "Hello! I am your Autonomous Portfolio & Rebalancing Advisor for Indian residents.",
                "",
                "I haven't recorded any holdings yet. Please tell me what you've invested in, for example:",
                "> *'I have 100 stocks of TCS and my available cash is 50k (means rs.50000)'*",
                "> *'I own 50 shares of Reliance, 100 TCS, and 200 units of Goldbees'*",
                "",
                "You can also tell me your available cash or target risk profile anytime!",
                "",
                COMPLIANCE_BANNER
            ])
            return "\n".join(lines)

        # Acknowledge what was just updated
        if newly_added:
            lines.append(f"✅ **Recognized & Updated**: {', '.join(newly_added)}.\n")

        # Compute deterministic drift and valuation
        drift_data = calculate_portfolio_drift(holdings, self.target_allocations)
        total_val = drift_data.get("total_portfolio_value", 0.0)
        total_val_fmt = drift_data.get("total_portfolio_value_formatted", "₹0.00")

        lines.extend([
            f"### 📊 Your Current Portfolio Overview (Total Value: **{total_val_fmt}**)",
            f"- **Target Model**: **{self.target_model_name}**",
            "",
            "| Instrument | Asset Class | Shares | Price | Valuation | Current Weight |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |"
        ])

        for h in drift_data.get("holdings", []):
            lines.append(
                f"| `{h['ticker']}` ({h['name'][:24]}) | {h['asset_class']} | {h['shares']:,} | "
                f"{h['current_price_formatted']} | {h['current_value_formatted']} | {h['current_pct']:.2f}% |"
            )

        # Asset Concentration & Drift Analysis
        lines.extend([
            "",
            "### ⚖️ Asset Class Drift Analysis",
            "| Asset Class | Current Weight | Target Weight | Drift % | Valuation Delta | Status |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |"
        ])

        for ac in drift_data.get("asset_class_drift", []):
            st = ac["status"]
            flag = "🔴 OVERWEIGHT" if st == "OVERWEIGHT" else ("🔵 UNDERWEIGHT" if st == "UNDERWEIGHT" else "🟢 BALANCED")
            lines.append(
                f"| {ac['asset_class']} | {ac['current_pct']:.2f}% | {ac['target_pct']:.2f}% | "
                f"{ac['drift_pct']:+.2f}% | {ac['value_drift_formatted']} | {flag} |"
            )

        # Single-stock concentration warning
        equity_holdings = [h for h in drift_data.get("holdings", []) if h["asset_class"] == "Indian Equity"]
        if len(equity_holdings) == 1 and equity_holdings[0]["current_pct"] > 40.0:
            lines.extend([
                "",
                f"⚠️ **Concentration Risk Note**: You have **{equity_holdings[0]['current_pct']:.1f}%** of your portfolio concentrated in a single stock (`{equity_holdings[0]['ticker']}`). Institutional risk guidelines for Indian retail investors suggest limiting single-stock exposure to 10%–15% to protect against company-specific downside."
            ])

        # Generate Rebalancing Plan
        rebal_data = calculate_rebalance_orders(holdings, self.target_allocations, cash_infusion=self.cash_infusion)
        action_orders = [o for o in rebal_data.get("orders", []) if o["action"] != "HOLD"]

        if action_orders:
            lines.extend([
                "",
                "### 🎯 Actionable Rebalancing Plan",
                "| Action | Instrument | Shares | Unit Price | Trade Value | Target Weight |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |"
            ])
            for o in action_orders:
                act_icon = "🟢 BUY" if o["action"] == "BUY" else "🔴 SELL"
                lines.append(
                    f"| {act_icon} | `{o['ticker']}` | {o['shares_to_trade']:,} | "
                    f"{o['unit_price_formatted']} | {o['order_value_formatted']} | {o['target_pct']:.2f}% |"
                )

            lines.extend([
                "",
                "### 💡 Strategic Trade Rationales (Why Buy or Sell Each Stock):"
            ])
            for o in action_orders:
                act_icon = "🟢 BUY" if o["action"] == "BUY" else "🔴 SELL"
                rat = o.get("rationale", "Rebalance to target allocation.")
                lines.append(f"- **{act_icon} `{o['ticker']}`** ({o['shares_to_trade']:,} shares / {o['order_value_formatted']}): {rat}")

        # Indian Tax-Aware Guidance
        has_cash = "INR_CASH" in self.holdings_map and self.holdings_map["INR_CASH"]["shares"] > 0
        lines.extend([
            "",
            "### 💡 Indian Tax Efficiency Strategy:",
            "- **Cash Inflow Prioritization**: " + (
                f"You have {format_inr(self.holdings_map['INR_CASH']['shares'])} in cash reserve. Instead of selling appreciated stocks and triggering 12.5% LTCG (Section 112A) or 20% STCG (Section 111A), prioritize deploying your liquid cash to buy underweighted asset classes (like Gold ETFs or Debt) to balance your portfolio tax-free!"
                if has_cash else
                "Consider rebalancing via your monthly SIPs into underweighted asset classes rather than booking capital gains."
            ),
            "",
            "💬 **What would you like to explore next?**",
            "- Tell me more holdings: *'Also add 50 shares of Reliance and 200 GoldBees'*",
            "- Test cash deployment: *'What if I add 25k fresh cash?'*",
            "- Change target model: *'Switch to Moderate Balanced' or 'Switch to Conservative'*",
            "",
            COMPLIANCE_BANNER
        ])

        return "\n".join(lines)

