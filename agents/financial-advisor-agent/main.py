"""
Autonomous Portfolio & Rebalancing Advisor - Interactive CLI
============================================================
Command-line interface for analyzing portfolios, calculating asset allocation drift,
and generating tax-aware rebalancing plans for Indian residents.
Supports direct user input of invested stocks via step-by-step wizard, shorthand,
or natural language input.
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import warnings
from typing import Any, Dict, List, Optional, Tuple
from tabulate import tabulate

# Suppress harmless warnings
warnings.filterwarnings("ignore")

from portfolio_tools import (
    fetch_live_prices,
    calculate_portfolio_drift,
    calculate_rebalance_orders,
    format_inr,
    normalize_indian_ticker,
    infer_asset_class,
    parse_holdings_shorthand,
    parse_conversational_text
)
from agent import FinancialAdvisorAgent, COMPLIANCE_BANNER

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "sample_portfolio.json")
USER_PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "data", "user_portfolio.json")

DEFAULT_ALLOCATION_MODELS = {
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


def load_portfolio_data(filepath: str = DATA_FILE) -> Dict[str, Any]:
    """Loads sample or custom portfolio json."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Portfolio file not found at: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_user_portfolio(holdings: List[Dict[str, Any]], filepath: str = USER_PORTFOLIO_FILE):
    """Saves user-entered portfolio holdings to a local JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    payload = {
        "investor_profile": {
            "name": "Custom Investor",
            "residence": "India",
            "base_currency": "INR"
        },
        "current_holdings": holdings,
        "target_allocation_models": DEFAULT_ALLOCATION_MODELS
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\n💾 Portfolio successfully saved to: {filepath}")


def print_banner():
    """Prints the CLI application header banner."""
    print("=" * 80)
    print("  📈  AUTONOMOUS PORTFOLIO & REBALANCING ADVISOR (INDIA)  📉  ")
    print("  Deterministic Asset Allocation • Drift Math • Inflow Rebalancing  ")
    print("=" * 80)
    print(COMPLIANCE_BANNER)


def display_cli_drift_report(drift_data: Dict[str, Any]):
    """Renders formatted tabulate tables for portfolio drift."""
    print("\n" + "=" * 80)
    print("               📊 PORTFOLIO HOLDINGS & ASSET CLASS DRIFT")
    print("=" * 80)
    print(f"Total Portfolio Value: {drift_data.get('total_portfolio_value_formatted')}")
    rebal = drift_data.get("rebalance_recommended", False)
    status_msg = "⚠️  REBALANCE RECOMMENDED (Holdings drifted beyond ±1.5%)" if rebal else "✅  BALANCED"
    print(f"Status: {status_msg}")

    # Asset class drift table
    ac_rows = []
    for ac in drift_data.get("asset_class_drift", []):
        st = ac["status"]
        flag = "🔴 OVERWEIGHT" if st == "OVERWEIGHT" else ("🔵 UNDERWEIGHT" if st == "UNDERWEIGHT" else "🟢 BALANCED")
        ac_rows.append([
            ac["asset_class"],
            ac["current_value_formatted"],
            f"{ac['current_pct']:.2f}%",
            f"{ac['target_pct']:.2f}%",
            f"{ac['drift_pct']:+.2f}%",
            ac["value_drift_formatted"],
            flag
        ])

    headers = ["Asset Class", "Current Value", "Current %", "Target %", "Drift %", "Value Delta", "Status"]
    print("\n[Asset Class Allocation Summary]")
    print(tabulate(ac_rows, headers=headers, tablefmt="fancy_grid"))

    # Holdings detail table
    h_rows = []
    for h in drift_data.get("holdings", []):
        h_rows.append([
            h["ticker"],
            h["name"][:30],
            h["asset_class"],
            f"{h['shares']:,}",
            h["current_price_formatted"],
            h["current_value_formatted"],
            f"{h['current_pct']:.2f}%"
        ])
    h_headers = ["Ticker", "Instrument", "Asset Class", "Shares", "Price", "Holding Value", "Weight %"]
    print("\n[Current Holdings Breakdown]")
    print(tabulate(h_rows, headers=h_headers, tablefmt="simple"))


def display_cli_rebalance_report(rebalance_data: Dict[str, Any]):
    """Renders formatted tabulate tables for rebalancing orders."""
    print("\n" + "=" * 80)
    print("               🎯 ACTIONABLE REBALANCING ORDER BOOK")
    print("=" * 80)
    print(f"Current Value:     {rebalance_data.get('current_total_value_formatted')}")
    print(f"Cash Infusion:     {rebalance_data.get('cash_infusion_formatted')}")
    print(f"Expanded Target:   {rebalance_data.get('new_total_value_formatted')}")
    print(f"Strategy:          {rebalance_data.get('inflow_rebalancing_efficiency')} Inflow Efficiency")

    order_rows = []
    for o in rebalance_data.get("orders", []):
        if o["action"] == "HOLD":
            continue
        act = "🟢 BUY" if o["action"] == "BUY" else "🔴 SELL"
        order_rows.append([
            act,
            o["ticker"],
            o["name"][:26],
            f"{o['shares_to_trade']:,}",
            o["unit_price_formatted"],
            o["order_value_formatted"],
            f"{o['post_trade_pct']:.2f}%",
            f"{o['target_pct']:.2f}%"
        ])

    o_headers = ["Action", "Ticker", "Instrument", "Shares", "Unit Price", "Trade Value", "Post-Rebal %", "Target %"]
    print("\n[Executable Rebalancing Orders]")
    if order_rows:
        print(tabulate(order_rows, headers=o_headers, tablefmt="fancy_grid"))

        print("\n[Strategic Trade Rationales (Why Buy or Sell Each Stock)]")
        for o in rebalance_data.get("orders", []):
            if o["action"] == "HOLD":
                continue
            act = "🟢 BUY" if o["action"] == "BUY" else "🔴 SELL"
            rat = o.get("rationale", "Rebalance to target allocation.")
            print(f"  • {act} {o['ticker']} ({o['shares_to_trade']:,} shares / {o['order_value_formatted']}):")
            print(f"    ↳ {rat}")
    else:
        print("No trades needed. Portfolio is perfectly aligned with targets!")

    # Summary metrics
    print("\n[Capital Flows Summary]")
    summary_data = [
        ["Total Buy Value Required", rebalance_data.get("total_buy_value_formatted")],
        ["Total Sell Value Generated", rebalance_data.get("total_sell_value_formatted")],
        ["Net Cash Needed from External Sources", rebalance_data.get("net_cash_required_formatted")],
        ["Unallocated Cash Remaining", rebalance_data.get("unallocated_cash_formatted")]
    ]
    print(tabulate(summary_data, tablefmt="plain"))


def run_portfolio_analysis(
    holdings: List[Dict[str, Any]],
    targets: Dict[str, float],
    cash_infusion: float = 0.0,
    user_query: Optional[str] = None
):
    """Executes deterministic drift, rebalance orders, and AI advisor insights."""
    drift_data = calculate_portfolio_drift(holdings, targets)
    display_cli_drift_report(drift_data)

    rebalance_data = calculate_rebalance_orders(holdings, targets, cash_infusion=cash_infusion)
    display_cli_rebalance_report(rebalance_data)

    print("\n" + "=" * 80)
    print("            🧠 AI FINANCIAL ADVISOR INSIGHTS & TAX STRATEGY")
    print("=" * 80)
    agent = FinancialAdvisorAgent()
    advisor_report = agent.analyze_portfolio(
        current_holdings=holdings,
        target_allocations=targets,
        cash_infusion=cash_infusion,
        user_query=user_query
    )
    print(advisor_report)


def prompt_investment_mode(current_mode: str = "Aggressive Growth") -> Tuple[str, Dict[str, float]]:
    """
    Helper to select target investment mode (Aggressive, Moderate, Conservative, Custom).
    Returns (model_name, target_allocations_dict).
    """
    print("\n🎯 Select Target Investment Mode / Risk Profile:")
    print("  [1] Aggressive Growth      (50% Indian Equity, 15% Int'l, 20% Debt, 10% Gold, 5% Cash)")
    print("  [2] Moderate Balanced      (40% Indian Equity, 10% Int'l, 35% Debt, 10% Gold, 5% Cash)")
    print("  [3] Conservative Preserve  (20% Indian Equity, 5% Int'l, 55% Debt, 15% Gold, 5% Cash)")
    print("  [4] Custom Percentages")

    try:
        m_choice = input(f"Enter choice [1-4] (default 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "Aggressive Growth", DEFAULT_ALLOCATION_MODELS["Aggressive Growth"]

    if m_choice == "2":
        return "Moderate Balanced", DEFAULT_ALLOCATION_MODELS["Moderate Balanced"]
    elif m_choice == "3":
        return "Conservative Preservation", DEFAULT_ALLOCATION_MODELS["Conservative Preservation"]
    elif m_choice == "4":
        print("\nEnter custom target percentages (must sum to 100):")
        try:
            eq = float(input("  Indian Equity % (e.g. 50): "))
            intl = float(input("  International Equity % (e.g. 15): "))
            debt = float(input("  Fixed Income / Debt % (e.g. 20): "))
            gold = float(input("  Gold / Commodities % (e.g. 10): "))
            cash = float(input("  Cash & Equivalents % (e.g. 5): "))
            total = eq + intl + debt + gold + cash
            if abs(total - 100.0) > 1.0:
                print(f"Warning: Allocations sum to {total}%, normalizing to 100%.")
            custom_dict = {
                "Indian Equity": eq / total,
                "International Equity": intl / total,
                "Fixed Income / Debt": debt / total,
                "Gold / Commodities": gold / total,
                "Cash & Equivalents": cash / total
            }
            return "Custom Model", custom_dict
        except (ValueError, EOFError, KeyboardInterrupt):
            print("Invalid input. Defaulting to Aggressive Growth.")
            return "Aggressive Growth", DEFAULT_ALLOCATION_MODELS["Aggressive Growth"]
    else:
        return "Aggressive Growth", DEFAULT_ALLOCATION_MODELS["Aggressive Growth"]


def select_target_model() -> Dict[str, float]:
    """Helper to select or customize a target asset allocation model (returns target dict)."""
    _, targets = prompt_investment_mode()
    return targets


def enter_user_stocks_wizard():
    """
    Interactive wizard that takes user input about the stocks they have invested in.
    Supports:
      - Step-by-step stock & shares entry
      - Natural language / shorthand paste ('50 Reliance, 30 TCS, 200 GoldBees, 50000 cash')
    """
    print("\n" + "=" * 80)
    print("          📝 ENTER YOUR INVESTED STOCKS & HOLDINGS")
    print("=" * 80)
    print("How would you like to enter your invested stocks?")
    print("  [1] Interactive Step-by-Step (Enter each stock & shares one by one)")
    print("  [2] Quick Shorthand / Natural Language (e.g., '50 Reliance, 30 TCS, 200 GoldBeES, 50000 cash')")

    mode = input("\nEnter choice [1 or 2] (default 1): ").strip()

    holdings: List[Dict[str, Any]] = []

    if mode == "2":
        print("\nEnter your holdings description or shorthand:")
        print("Example: '100 RELIANCE, 50 TCS, 80 INFY, 500 GOLDBEES, 100000 CASH'")
        user_text = input("Your input: ").strip()
        if not user_text:
            print("No input provided. Returning to main menu.")
            return

        print("\n⏳ Parsing your holdings...")
        agent = FinancialAdvisorAgent()
        holdings = agent.parse_user_holdings(user_text)

        if not holdings:
            print("Could not parse any holdings from your input. Please try the step-by-step entry.")
            return

        print(f"\n✓ Successfully identified {len(holdings)} holdings:")
        for h in holdings:
            print(f"  - {h['ticker']}: {h['shares']} shares ({h['asset_class']})")

    else:
        # Step-by-step interactive entry
        print("\nEnter your stocks and assets (type 'done' when finished):")
        idx = 1
        while True:
            print(f"\n[Holding #{idx}]")
            symbol_in = input("  Stock Ticker or Company Name (e.g. RELIANCE, TCS, INFY, GOLDBEES, or 'done'): ").strip()
            if symbol_in.lower() in ("done", "exit", "q", ""):
                if len(holdings) == 0:
                    print("No holdings entered yet. Please enter at least one stock.")
                    continue
                break

            ticker = normalize_indian_ticker(symbol_in)

            # Prompt for shares
            shares_str = input(f"  Number of shares/units owned of {ticker}: ").strip()
            try:
                shares = float(shares_str.replace(",", ""))
                if shares <= 0:
                    print("Shares must be positive. Skipping.")
                    continue
            except ValueError:
                print("Invalid number of shares. Skipping.")
                continue

            asset_class = infer_asset_class(ticker)
            print(f"  -> Asset Class: {asset_class}")

            holdings.append({
                "ticker": ticker,
                "name": ticker,
                "shares": shares,
                "asset_class": asset_class
            })
            idx += 1

            more = input("  Add another stock? (y/n, default 'y'): ").strip().lower()
            if more in ("n", "no"):
                break

        # Ask about cash reserve
        cash_str = input("\nAny liquid savings / bank cash reserve in INR? (e.g. 50000, or press Enter for 0): ").strip()
        if cash_str:
            try:
                cash_val = float(cash_str.replace(",", "").replace("₹", ""))
                if cash_val > 0:
                    holdings.append({
                        "ticker": "INR_CASH",
                        "name": "High Yield Bank Savings / Cash",
                        "shares": cash_val,
                        "asset_class": "Cash & Equivalents"
                    })
            except ValueError:
                pass

    if not holdings:
        print("No valid holdings entered.")
        return

    # Select target model
    targets = select_target_model()

    # Optional cash infusion
    infusion_str = input("\nAny fresh cash infusion for rebalancing in INR? (e.g. 50000, or press Enter for 0): ").strip()
    cash_infusion = 0.0
    if infusion_str:
        try:
            cash_infusion = float(infusion_str.replace(",", "").replace("₹", ""))
        except ValueError:
            cash_infusion = 0.0

    # Ask if user wants to save this portfolio
    save_opt = input("\nSave this portfolio to data/user_portfolio.json for future runs? (y/n, default 'y'): ").strip().lower()
    if save_opt not in ("n", "no"):
        save_user_portfolio(holdings)

    # Run analysis
    print("\n⏳ Fetching live prices and calculating portfolio rebalancing...")
    run_portfolio_analysis(holdings, targets, cash_infusion=cash_infusion)


def run_preset(preset_num: int, custom_cash: Optional[float] = None, portfolio_path: str = DATA_FILE):
    """Executes one of the predefined presets."""
    data = load_portfolio_data(portfolio_path)
    holdings = data["current_holdings"]
    models = data.get("target_allocation_models", DEFAULT_ALLOCATION_MODELS)

    if preset_num == 1:
        print("\n▶ Running Preset 1: Analyze Portfolio against 'Aggressive Growth' Model (50/15/20/10/5)")
        targets = models["Aggressive Growth"]
        cash = custom_cash if custom_cash is not None else 0.0

    elif preset_num == 2:
        print("\n▶ Running Preset 2: Analyze Portfolio against 'Moderate Balanced' Model (40/10/35/10/5)")
        targets = models["Moderate Balanced"]
        cash = custom_cash if custom_cash is not None else 0.0

    elif preset_num == 3:
        cash = custom_cash if custom_cash is not None else 100000.0
        print(f"\n▶ Running Preset 3: Tax-Smart Inflow Rebalancing with Fresh Cash ({format_inr(cash)})")
        targets = models["Aggressive Growth"]

    elif preset_num == 4:
        print("\n▶ Running Preset 4: 'Conservative Wealth Preservation' Model (20/5/55/15/5)")
        targets = models["Conservative Preservation"]
        cash = custom_cash if custom_cash is not None else 0.0

    else:
        print(f"Unknown preset {preset_num}. Defaulting to Preset 1.")
        targets = models["Aggressive Growth"]
        cash = 0.0

    run_portfolio_analysis(holdings, targets, cash_infusion=cash)


def run_self_test() -> int:
    """Automated self-test verifying all components deterministically."""
    print("\n" + "=" * 80)
    print("               🧪 RUNNING AUTOMATED SELF-CHECK")
    print("=" * 80)

    try:
        # Test 1: Load portfolio
        data = load_portfolio_data()
        holdings = data["current_holdings"]
        targets = data["target_allocation_models"]["Aggressive Growth"]
        assert len(holdings) > 0, "Holdings list must not be empty"
        print("✓ Test 1: Portfolio data loaded successfully.")

        # Test 2: Price fetcher (with fallback safeguard)
        tickers = [h["ticker"] for h in holdings[:3]]
        prices = fetch_live_prices(tickers)
        assert prices["status"] == "success"
        assert len(prices["prices"]) == len(tickers)
        print(f"✓ Test 2: Live price lookup succeeded (Source: {prices['data_source']}).")

        # Test 3: Drift calculation
        drift = calculate_portfolio_drift(holdings, targets)
        assert drift["status"] == "success"
        assert drift["total_portfolio_value"] > 0
        assert len(drift["asset_class_drift"]) == len(targets)
        print(f"✓ Test 3: Drift math computed deterministically. Total Val: {drift['total_portfolio_value_formatted']}")

        # Test 4: Rebalance orders with cash infusion
        reb = calculate_rebalance_orders(holdings, targets, cash_infusion=50000.0)
        assert reb["status"] == "success"
        assert reb["cash_infusion"] == 50000.0
        assert len(reb["orders"]) == len(holdings)
        print(f"✓ Test 4: Rebalance orders generated successfully. Total Buys: {reb['total_buy_value_formatted']}")

        # Test 5: Shorthand user input parser
        user_test_str = "RELIANCE:50, TCS:25, INFY:40, GOLDBEES:200, CASH:50000"
        parsed_user_holdings = parse_holdings_shorthand(user_test_str)
        assert len(parsed_user_holdings) == 5
        assert parsed_user_holdings[0]["ticker"] == "RELIANCE.NS"
        print(f"✓ Test 5: User stock input parser accurately extracted {len(parsed_user_holdings)} holdings.")

        # Test 6: Advisor Agent execution
        agent = FinancialAdvisorAgent()
        report = agent.analyze_portfolio(holdings, targets, cash_infusion=50000.0)
        assert "COMPLIANCE DISCLAIMER" in report
        print("✓ Test 6: Advisor Agent synthesized report with compliance banner.")

        print("\n" + "=" * 80)
        print("              🎉 ALL 6 SELF-CHECK TESTS PASSED!")
        print("=" * 80)
        return 0

    except Exception as e:
        print(f"\n❌ Self-test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def run_conversational_chat_loop():
    """
    Runs a continuous natural-language conversational session with the AI financial advisor.
    The user can speak naturally (e.g. 'I have 100 stocks of TCS and my available cash is 50k (means rs.50000)').
    """
    print("\n" + "=" * 80)
    print("      💬 CONVERSATIONAL PORTFOLIO & REBALANCING ADVISOR (INDIA)")
    print("=" * 80)
    print("Speak naturally about your investments, cash, and rebalancing goals.")
    print("Examples:")
    print("  • 'I have 100 stocks of TCS and my available cash is 50k (means rs.50000)'")
    print("  • 'Also add 50 shares of Reliance and 200 units of Goldbees'")
    print("  • 'Rebalance my portfolio with the Moderate model'")
    print("  • 'What if I infuse 25k fresh cash?'")
    print("  • 'What is my LTCG tax liability if I sell 20 TCS shares?'")
    print("  • Type 'mode' anytime to choose or switch investment mode (Conservative / Moderate / Aggressive)")
    print("Type 'exit', 'quit', or 'back' to return to the main menu.\n")
    print(COMPLIANCE_BANNER)

    agent = FinancialAdvisorAgent()
    session = agent.start_conversational_session()

    while True:
        try:
            user_msg = input("\nYou 👤 > ").strip()
            if not user_msg:
                continue
            if user_msg.lower() in ("exit", "quit", "q", "back"):
                print("\nReturning to main menu.")
                break

            # Allow user to switch or choose investment mode anytime
            if user_msg.lower() in ("mode", "model", "investment mode", "change mode", "switch mode", "select mode"):
                name, targets = prompt_investment_mode(session.target_model_name)
                session.set_target_model(name, targets)
                print(f"\n✓ Investment mode set to: {session.target_model_name}")
                if session.get_holdings_list():
                    print("\nAdvisor 🤖 > Re-evaluating portfolio under new model...")
                    reply = session.chat(f"Rebalance my portfolio with {session.target_model_name} model")
                    print(f"\nAdvisor 🤖 >\n{reply}")
                continue

            # Detect if investment info (stocks or cash reserve) is provided in this message
            parsed = parse_conversational_text(user_msg)
            has_new_investment_info = bool(parsed.get("stocks")) or (parsed.get("cash", 0.0) > 0)

            # If user provided investment info and hasn't chosen an investment mode yet
            if has_new_investment_info and not parsed.get("target_model") and not session.mode_selected:
                print("\n💡 Investment information received!")
                name, targets = prompt_investment_mode(session.target_model_name)
                session.set_target_model(name, targets)
                print(f"✓ Target investment mode set to: {session.target_model_name}")

            print("\nAdvisor 🤖 > Processing your portfolio & market data...")
            reply = session.chat(user_msg)
            print(f"\nAdvisor 🤖 >\n{reply}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat mode.")
            break


def interactive_menu():
    """Runs interactive CLI menu for user choice."""
    print_banner()
    while True:
        print("\nPlease select an option:")
        print("  [1] 💬 Conversational Advisor Chat Mode (e.g. 'I have 100 stocks of TCS and available cash is 50k')")
        print("  [0] Exit")

        choice = input("\nEnter choice [0-1]: ").strip()
        if choice == "0":
            print("\nThank you for using Autonomous Portfolio & Rebalancing Advisor. Exiting.")
            sys.exit(0)
        elif choice == "1":
            run_conversational_chat_loop()
        else:
            print("Invalid selection. Please choose 0 or 1.")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Portfolio & Rebalancing Advisor for Indian Residents")
    parser.add_argument("--chat", action="store_true", help="Launch interactive conversational chat advisor directly")
    parser.add_argument("--preset", type=int, choices=[1, 2, 3, 4], help="Run a specific preset directly")
    parser.add_argument("--input", "--holdings", type=str, default=None, help="User holdings string, e.g. 'RELIANCE:50, TCS:30, GOLDBEES:200, CASH:50000'")
    parser.add_argument("--cash", type=float, default=None, help="Optional cash infusion amount in INR")
    parser.add_argument("--file", type=str, default=DATA_FILE, help="Path to portfolio JSON file")
    parser.add_argument("--mock", action="store_true", help="Force offline mock prices (no network calls)")
    parser.add_argument("--test", action="store_true", help="Run automated self-check tests and exit")

    args = parser.parse_args()

    if args.mock:
        os.environ["USE_MOCK_DATA"] = "1"

    if args.test:
        sys.exit(run_self_test())

    if args.chat:
        print_banner()
        run_conversational_chat_loop()
        return

    # Direct user input via CLI argument
    if args.input:
        print_banner()
        print(f"\n▶ Parsing User Holdings from command line: {args.input}")
        agent = FinancialAdvisorAgent()
        holdings = agent.parse_user_holdings(args.input)
        if not holdings:
            print("❌ Could not parse any holdings from input string.")
            sys.exit(1)
        targets = DEFAULT_ALLOCATION_MODELS["Aggressive Growth"]
        cash = args.cash if args.cash is not None else 0.0
        run_portfolio_analysis(holdings, targets, cash_infusion=cash)
        return

    if args.preset is not None:
        print_banner()
        run_preset(args.preset, custom_cash=args.cash, portfolio_path=args.file)
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
