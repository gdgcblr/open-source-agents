"""
Non-Browser "Tony Stark" Interactive Terminal HUD for Project V.U.L.C.A.N.
Built with Textual and Rich with offline J.A.R.V.I.S. voice callouts.
"""

import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import os
import asyncio
import difflib
from pathlib import Path
from typing import Optional, Dict, Any

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.columns import Columns
from rich.align import Align

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, Button, RichLog, Label
from textual.binding import Binding
from textual import work

# Ensure parent directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    FORENSICS_PORT,
    FINOPS_PORT,
    MODEL_NAME,
    VOICE_ENABLED,
    TARGET_RPS,
)
from agents.vulcan_orchestrator import VulcanOrchestrator, TelemetryIncident
from hud.voice_synthesizer import VoiceSynthesizer

# --- Textual CSS Styling (Tony Stark Dark Neon HUD) ---

HUD_CSS = """
Screen {
    background: #07090e;
    color: #e2e8f0;
}

#top-banner {
    dock: top;
    height: 3;
    background: #0d121d;
    border-bottom: heavy #00f0ff;
    padding: 0 1;
}

#status-badges {
    dock: top;
    height: 3;
    background: #090e17;
    border-bottom: solid #1e293b;
    padding: 0 1;
}

#main-columns {
    height: 1fr;
    padding: 0 1;
}

.hud-panel {
    border: round #00f0ff;
    background: #090e17;
    margin: 0 1;
    height: 100%;
}

.hud-panel-alert {
    border: round #ff0055;
    background: #14080e;
}

.hud-panel-success {
    border: round #00ff88;
    background: #08140e;
}

.panel-header {
    background: #0f172a;
    color: #00f0ff;
    text-align: center;
    text-style: bold;
    height: 1;
    border-bottom: solid #1e293b;
}

RichLog {
    background: #07090e;
    color: #cbd5e1;
    scrollbar-color: #00f0ff #090e17;
    height: 1fr;
}

#footer-controls {
    dock: bottom;
    height: 5;
    background: #090e17;
    border-top: double #00f0ff;
    padding: 1 1;
    align: center middle;
}

#footer-controls Button {
    margin: 0 1;
    height: 3;
    min-width: 14;
    max-width: 26;
    text-style: bold;
    border: tall #334155;
    background: #1e293b;
    color: #e2e8f0;
}

#btn-trigger {
    background: #4c0519;
    color: #ffe4e6;
    border: tall #ff0055;
}
#btn-trigger:hover, #btn-trigger:focus {
    background: #ff0055;
    color: #ffffff;
    border: tall #ffffff;
    text-style: bold underline;
}

#btn-heal {
    background: #064e3b;
    color: #d1fae5;
    border: tall #00ff88;
}
#btn-heal:hover, #btn-heal:focus {
    background: #00ff88;
    color: #000000;
    border: tall #ffffff;
    text-style: bold underline;
}

#btn-reset {
    background: #451a03;
    color: #fef3c7;
    border: tall #ffb700;
}
#btn-reset:hover, #btn-reset:focus {
    background: #ffb700;
    color: #000000;
    border: tall #ffffff;
    text-style: bold underline;
}

#btn-voice {
    background: #2e1065;
    color: #f3e8ff;
    border: tall #b026ff;
}
#btn-voice:hover, #btn-voice:focus {
    background: #b026ff;
    color: #ffffff;
    border: tall #ffffff;
    text-style: bold underline;
}

#btn-quit {
    background: #1e293b;
    color: #cbd5e1;
    border: tall #64748b;
}
#btn-quit:hover, #btn-quit:focus {
    background: #dc2626;
    color: #ffffff;
    border: tall #ff0055;
    text-style: bold underline;
}
"""

def make_gauge(ratio: float, width: int = 16) -> str:
    ratio = min(1.0, max(0.0, ratio))
    filled = int(round(ratio * width))
    empty = width - filled
    return "█" * filled + "░" * empty

class VulcanHUDApp(App):
    """Interactive Tony Stark Terminal HUD for Project V.U.L.C.A.N."""

    CSS = HUD_CSS
    TITLE = "PROJECT V.U.L.C.A.N. // FinOps Swarm HUD"

    BINDINGS = [
        Binding("t", "trigger_traffic", "Trigger Bug (T)", priority=True),
        Binding("h", "engage_heal", "Engage Heal (H)", priority=True),
        Binding("r", "reset_state", "Reset Demo (R)", priority=True),
        Binding("v", "toggle_voice", "Toggle Voice (V)", priority=True),
        Binding("q", "quit", "Quit (Q)", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.voice = VoiceSynthesizer(enabled=VOICE_ENABLED)
        self.orchestrator = VulcanOrchestrator(event_callback=self._handle_orchestrator_event)
        self.current_incident: Optional[TelemetryIncident] = None
        self.burn_amount = "$24/mo"
        self.burn_color = "#00ff88"
        self.burn_badge = "NORMALIZED"

    def compose(self) -> ComposeResult:
        # Top Neon Banner
        yield Static(id="top-banner")
        yield Static(id="status-badges")

        # 3 Main Columns
        with Horizontal(id="main-columns"):
            # Left Column: SQL Wiretap & Blast Radius Telemetry
            with Vertical(id="col-wiretap", classes="hud-panel"):
                yield Label("⚡ LIVE SQL WIRETAP & CLOUD BLAST RADIUS", classes="panel-header")
                yield Static(id="blast-radius-box")
                yield RichLog(id="wiretap-log", wrap=True, highlight=True, markup=True)

            # Center Column: A2A Protocol & Agent Card Wiretap
            with Vertical(id="col-a2a", classes="hud-panel"):
                yield Label("🛰️ A2A PROTOCOL & AGENT REASONING MESH", classes="panel-header")
                yield RichLog(id="a2a-log", wrap=True, highlight=True, markup=True)

            # Right Column: Reforger Code Diff & Sandbox Benchmark
            with Vertical(id="col-reforger", classes="hud-panel"):
                yield Label("🛠️ THE REFORGER: CODE DIFF & SANDBOX BENCHMARK", classes="panel-header")
                yield Static(id="benchmark-summary-box")
                yield RichLog(id="reforger-diff-log", wrap=False, highlight=True, markup=True)

        # Footer Action Bar
        with Horizontal(id="footer-controls"):
            yield Button("⚡ Inject Storm (T)", id="btn-trigger")
            yield Button("🛡️ Engage Heal (H)", id="btn-heal")
            yield Button("🔄 Reset Demo (R)", id="btn-reset")
            yield Button("🎙️ Voice: ON (V)", id="btn-voice")
            yield Button("❌ Exit HUD (Q)", id="btn-quit")

    def on_mount(self):
        self._update_banner()
        self._update_badges()
        self._init_logs()
        self.run_startup_mesh_discovery()

    def _update_banner(self):
        banner_text = Text()
        banner_text.append("⚡ PROJECT V.U.L.C.A.N. ", style="bold #00f0ff")
        banner_text.append("// AUTONOMOUS PRE-PROD FINOPS & QUERY INTERCEPTOR SWARM", style="bold #cbd5e1")
        banner_text.append(" [MARK VII]", style="bold #ffb700")
        self.query_one("#top-banner", Static).update(Align.center(banner_text))

    def _update_badges(self):
        badges = Text()
        badges.append("[ WIRETAP: ", style="bold #64748b")
        badges.append("ONLINE", style="bold #00ff88")
        badges.append(" ]   ", style="bold #64748b")

        badges.append("[ A2A MESH: ", style="bold #64748b")
        badges.append("2 NODES ACTIVE (:8001, :8002)", style="bold #00f0ff")
        badges.append(" ]   ", style="bold #64748b")

        badges.append("[ MODEL: ", style="bold #64748b")
        badges.append(f"{MODEL_NAME.upper()}", style="bold #b026ff")
        badges.append(" ]   ", style="bold #64748b")

        badges.append("[ PROJECTED CLOUD BURN: ", style="bold #64748b")
        badges.append(f"{self.burn_amount} ({self.burn_badge})", style=f"bold {self.burn_color}")
        badges.append(" ]", style="bold #64748b")

        self.query_one("#status-badges", Static).update(Align.center(badges))

    def _init_logs(self):
        wlog = self.query_one("#wiretap-log", RichLog)
        wlog.write("[bold #00f0ff]>>> SQL WIRETAP ARMED & LISTENING ON TARGET REPOSITORY[/bold #00f0ff]")
        wlog.write("[#64748b]Monitoring sqlite3 set_trace_callback hooks for query storm threshold breach (>5 queries, >20ms)...[/#64748b]\n")

        alog = self.query_one("#a2a-log", RichLog)
        alog.write("[bold #00f0ff]>>> AGENT2AGENT (A2A) MESH CONTROLLER INITIALIZED[/bold #00f0ff]")
        alog.write(f"[#64748b]Node-Alpha: Forensics Profiler (Port {FORENSICS_PORT}) | Node-Beta: FinOps Actuary (Port {FINOPS_PORT})[/#64748b]\n")

        rlog = self.query_one("#reforger-diff-log", RichLog)
        rlog.write("[bold #00f0ff]>>> THE REFORGER & SANDBOX VERIFIER STANDING BY[/bold #00f0ff]")
        rlog.write("[#64748b]Ready to construct covering SQL indexes, hot-patch repository functions, and verify latency drops.[/#64748b]\n")

        self._render_blast_box(is_storm=False, aurora_cost=24.50, azure_cost=23.50, query_count=1)

    def _render_blast_box(self, is_storm: bool, aurora_cost: float, azure_cost: float, query_count: int):
        box = self.query_one("#blast-radius-box", Static)
        
        ratio = 1.0 if is_storm else 0.05
        color = "#ff0055" if is_storm else "#00ff88"
        status_label = "CRITICAL BURST DETECTED" if is_storm else "IDLE / OPTIMIZED"

        gauge_aurora = make_gauge(ratio, width=16)
        gauge_azure = make_gauge(ratio, width=16)

        t = Table(box=None, expand=True, padding=(0, 1))
        t.add_column("Cloud Target", style="bold #cbd5e1", width=14)
        t.add_column("Load Meter", style=f"bold {color}", width=18)
        t.add_column("Projected Burn", style=f"bold {color}", justify="right")

        t.add_row("AWS Aurora", f"[{color}]{gauge_aurora}[/{color}]", f"${aurora_cost:,.2f}/mo")
        t.add_row("Azure SQL", f"[{color}]{gauge_azure}[/{color}]", f"${azure_cost:,.2f}/mo")

        p = Panel(
            t,
            title=f"[{color} bold]BLAST RADIUS: {status_label} ({query_count} queries/req)[/{color} bold]",
            border_style=color
        )
        box.update(p)

    # --- Async Actions ---

    @work(exclusive=True)
    async def run_startup_mesh_discovery(self):
        alog = self.query_one("#a2a-log", RichLog)
        alog.write("[bold #ffb700]>>> Probing A2A Mesh Nodes for Agent Cards (/.well-known/agent.json)...[/bold #ffb700]")
        cards = await self.orchestrator.discover_mesh()
        alog.write(f"[bold #00ff88]✓ Discovery handshake successful across ports {FORENSICS_PORT} and {FINOPS_PORT}.[/bold #00ff88]")
        alog.write(f"[#64748b]Node 1: {cards.get('forensics_card', {}).get('name', 'forensics')} | Node 2: {cards.get('finops_card', {}).get('name', 'finops')}[/#64748b]\n")
        self.voice.callout_startup()

    @work(exclusive=True)
    async def action_trigger_traffic(self):
        wlog = self.query_one("#wiretap-log", RichLog)
        wlog.write("\n[bold #ff0055]═══════════════════ [TRAFFIC INJECTED] ═══════════════════[/bold #ff0055]")
        wlog.write("[bold #ffb700]Simulating high-volume API request against target_app.buggy_repository...[/bold #ffb700]")

        incident = await self.orchestrator.trigger_unoptimized_traffic()
        self.current_incident = incident

        # Update HUD state to ALERT
        self.burn_amount = "$3,840.50/mo"
        self.burn_color = "#ff0055"
        self.burn_badge = "CRITICAL STORM"
        self._update_badges()

        # Update left column
        self._render_blast_box(is_storm=True, aurora_cost=3840.50, azure_cost=4800.77, query_count=incident.query_count)

        wlog.write(f"[bold #ff0055]🚨 TELEMETRY INCIDENT [{incident.incident_id}][/bold #ff0055]")
        wlog.write(f"  • Queries Intercepted: [bold #ff0055]{incident.query_count}[/bold #ff0055] (Threshold: 5)")
        wlog.write(f"  • Execution Latency:   [bold #ff0055]{incident.wall_clock_ms:.1f}ms[/bold #ff0055] (Threshold: 20ms)")
        wlog.write(f"  • Table Scan Detected: [bold #ff0055]{incident.scan_detected}[/bold #ff0055] on unindexed 'bids' table")
        wlog.write(f"  • Duplicate Patterns:  SELECT * FROM bids WHERE auction_id = ? ([bold #ff0055]40 repeats[/bold #ff0055])")
        wlog.write(f"[bold #ff0055]>>> {incident.alert_summary}[/bold #ff0055]\n")

        self.voice.callout_query_storm(queries=incident.query_count)

    @work(exclusive=True)
    async def action_engage_heal(self):
        if not self.current_incident:
            # Trigger first if not run yet
            self.current_incident = await self.orchestrator.trigger_unoptimized_traffic()

        alog = self.query_one("#a2a-log", RichLog)
        wlog = self.query_one("#wiretap-log", RichLog)
        rlog = self.query_one("#reforger-diff-log", RichLog)

        alog.write("\n[bold #00f0ff]══════════════ [A2A SWARM HEALING ENGAGED] ══════════════[/bold #00f0ff]")
        self.voice.callout_heal_engaged()

        result = await self.orchestrator.engage_autonomous_heal(self.current_incident)

        # Update burn counters to NORMALIZED
        self.burn_amount = "$24.50/mo"
        self.burn_color = "#00ff88"
        self.burn_badge = "NORMALIZED"
        self._update_badges()

        # Update left blast box
        self._render_blast_box(is_storm=False, aurora_cost=24.50, azure_cost=23.50, query_count=1)

        # Render Benchmark Box in Right Column
        summary_box = self.query_one("#benchmark-summary-box", Static)
        bench = result.get("patch", {})
        impact = result.get("finops", {}).get("impact", {})

        t = Table(title="[bold #00ff88]SANDBOX BENCHMARK VERIFICATION[/bold #00ff88]", box=None, expand=True)
        t.add_column("Metric", style="bold #cbd5e1")
        t.add_column("Before", style="bold #ff0055")
        t.add_column("After", style="bold #00ff88")
        t.add_column("Delta", style="bold #00f0ff")

        b_q = bench.get("before", {}).get("query_count", 41)
        a_q = bench.get("after", {}).get("query_count", 1)
        b_ms = bench.get("before", {}).get("wall_clock_ms", 210.0)
        a_ms = bench.get("after", {}).get("wall_clock_ms", 3.5)

        t.add_row("Queries / Request", f"{b_q}", f"{a_q}", "-97.6%")
        t.add_row("Execution Plan", "SCAN TABLE bids", "INDEX B-TREE SEARCH", "O(N)->O(log N)")
        t.add_row("Execution Latency", f"{b_ms:.1f}ms", f"{a_ms:.1f}ms", f"-{round(((b_ms-a_ms)/b_ms)*100, 1)}%")
        t.add_row("AWS Monthly Burn", "$3,840.50/mo", "$24.50/mo", f"-${impact.get('monthly_savings_aurora', 3816.0):,.2f}/mo")
        t.add_row("Annual Savings", "—", "—", f"+${impact.get('annual_cloud_savings', 45792.0):,.2f}/yr")

        p = Panel(t, border_style="#00ff88")
        summary_box.update(p)

        # Display syntax highlighted diff
        rlog.clear()
        rlog.write("[bold #00ff88]>>> THE REFORGER HOT-PATCH UNIFIED DIFF (buggy_repository.py):[/bold #00ff88]\n")
        diff_str = bench.get("unified_diff", "")
        for line in diff_str.splitlines():
            if line.startswith("+"):
                rlog.write(f"[bold #00ff88]{line}[/bold #00ff88]")
            elif line.startswith("-"):
                rlog.write(f"[bold #ff0055]{line}[/bold #ff0055]")
            elif line.startswith("@"):
                rlog.write(f"[bold #00f0ff]{line}[/bold #00f0ff]")
            else:
                rlog.write(f"[#94a3b8]{line}[/#94a3b8]")

        self.voice.callout_heal_completed()

    def action_reset_state(self):
        res = self.orchestrator.reset()
        self.current_incident = None

        self.burn_amount = "$24/mo"
        self.burn_color = "#00ff88"
        self.burn_badge = "RESET READY"
        self._update_badges()

        self._render_blast_box(is_storm=False, aurora_cost=24.50, azure_cost=23.50, query_count=1)

        wlog = self.query_one("#wiretap-log", RichLog)
        wlog.write("\n[bold #ffb700]═══════════════════ [DEMO STATE RESET] ═══════════════════[/bold #ffb700]")
        wlog.write("[bold #00ff88]✓ Dropped index idx_bids_auction_id from SQLite.[/bold #00ff88]")
        wlog.write("[bold #00ff88]✓ Restored unoptimized buggy_repository.py from backup.[/bold #00ff88]")
        wlog.write("[#64748b]System primed for repeat query storm stage demonstration.[/#64748b]\n")

        summary_box = self.query_one("#benchmark-summary-box", Static)
        summary_box.update("")

        rlog = self.query_one("#reforger-diff-log", RichLog)
        rlog.clear()
        rlog.write("[bold #ffb700]Demo state restored to unoptimized baseline. Press [T] to trigger traffic.[/bold #ffb700]")

        self.voice.callout_reset()

    def action_quit(self) -> None:
        """Exits the application immediately."""
        self.exit()

    def action_toggle_voice(self):
        new_state = self.voice.toggle()
        btn = self.query_one("#btn-voice", Button)
        if new_state:
            btn.label = "🎙️ Voice: ON (V)"
            self.voice.speak("Voice callouts enabled.")
        else:
            btn.label = "🔇 Voice: OFF (V)"

    # --- Button Event Handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-trigger":
            self.action_trigger_traffic()
        elif btn_id == "btn-heal":
            self.action_engage_heal()
        elif btn_id == "btn-reset":
            self.action_reset_state()
        elif btn_id == "btn-voice":
            self.action_toggle_voice()
        elif btn_id == "btn-quit":
            self.exit()

    # --- Orchestrator Event Hook ---

    def _handle_orchestrator_event(self, event: Dict[str, Any]):
        etype = event.get("event_type", "")
        data = event.get("data", {})
        ts = event.get("timestamp", "")
        
        alog = self.query_one("#a2a-log", RichLog)

        if etype == "A2A_RPC_SEND":
            target = data.get("to", "unknown")
            method = data.get("method", "")
            alog.write(f"[{ts}] [bold #00f0ff]➔ A2A JSON-RPC DISPATCH[/bold #00f0ff] to [bold #ffb700]{target}[/bold #ffb700]")
            alog.write(f"    Method: [bold]{method}[/bold] | Payload: {data.get('payload', {})}")

        elif etype == "A2A_RPC_RECV":
            source = data.get("from", "unknown")
            payload = data.get("data", {})
            alog.write(f"[{ts}] [bold #00ff88]⬅ A2A JSON-RPC RESPONSE[/bold #00ff88] from [bold #ffb700]{source}[/bold #ffb700]")
            if "verdict" in payload:
                v = payload.get("verdict", "")
                if "[GEMINI 3.8 FLASH]" in v:
                    alog.write(f"    [bold #b026ff]⚡ Forensics Profiler (Gemini 3.8 Flash):[/bold #b026ff]")
                    clean_v = v.replace("[GEMINI 3.8 FLASH]", "").strip()
                    alog.write(f"    [bold #f1f5f9]{clean_v}[/bold #f1f5f9]")
                else:
                    alog.write(f"    [bold #ff0055]Verdict:[/bold #ff0055] {v}")
                    
            if "ai_verdict" in payload:
                aiv = payload.get("ai_verdict", "")
                if "[GEMINI 3.8 FLASH]" in aiv:
                    alog.write(f"    [bold #b026ff]⚡ FinOps Actuary (Gemini 3.8 Flash):[/bold #b026ff]")
                    clean_aiv = aiv.replace("[GEMINI 3.8 FLASH]", "").strip()
                    alog.write(f"    [bold #f1f5f9]{clean_aiv}[/bold #f1f5f9]")

            if "unoptimized" in payload:
                unopt = payload.get("unoptimized", {})
                alog.write(f"    [bold #ff0055]Aurora Blast:[/bold #ff0055] ${unopt.get('aws_aurora_monthly', 0):,.2f}/mo | [bold #ff0055]Azure SQL:[/bold #ff0055] ${unopt.get('azure_sql_monthly', 0):,.2f}/mo ({unopt.get('azure_vcores')} vCores)")

        elif etype == "REFORGER_ACTION":
            step = data.get("step", "")
            msg = data.get("message", "")
            alog.write(f"[{ts}] [bold #b026ff]⚡ THE REFORGER [{step}][/bold #b026ff]: {msg}")

if __name__ == "__main__":
    app = VulcanHUDApp()
    app.run()
