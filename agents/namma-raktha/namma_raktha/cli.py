"""
Interactive Rich Terminal Interface for NammaRaktha.
Run directly via: python run.py --cli
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.markdown import Markdown

from .agent import agent
from .models import AgentTriageResult
from .blood_banks import BENGALURU_BLOOD_BANKS

console = Console()

PRESET_SCENARIOS = {
    "1": (
        "Manipal Hospital Dengue Emergency (Platelets SDP)",
        "Urgent: Need 2 units of A+ platelets (SDP) for a critical dengue patient with dropping count at Manipal Hospital, HAL Old Airport Road. Attendant Suresh: 9886012345. IP: 5542."
    ),
    "2": (
        "Victoria Hospital Emergency (O-Negative Rare Blood)",
        "Emergency: Need 3 units of O-negative whole blood immediately for road accident trauma at Victoria Hospital, KR Market. Contact Dr. Ramesh: 9845011223."
    ),
    "3": (
        "Kidwai Oncology Plateletpheresis",
        "Required 1 unit Single Donor Platelet B+ for leukemia patient at Kidwai Memorial Institute of Oncology, Hosur Road. Attendant Anitha: 9900112233."
    ),
    "4": (
        "Rare Bombay Blood Group Alert",
        "CRITICAL: Bombay blood group patient in ICU at Jayadeva Institute of Cardiovascular Sciences, Bannerghatta Road. Needs 2 units packed red cells immediately. Contact: 9741098765."
    )
}


def display_triage_result(result: AgentTriageResult):
    req = result.requirement
    comp = result.compatibility
    sos = result.sos

    # 1. Header Banner
    console.print("\n")
    console.rule("[bold red]🚨 NAMMARAKTHA EMERGENCY TRIAGE REPORT 🚨[/bold red]")
    
    # 2. Patient & Request Details Table
    req_table = Table(title="📋 Verified Transfusion Requirement", show_header=True, header_style="bold magenta")
    req_table.add_column("Field", style="cyan", width=22)
    req_table.add_column("Details", style="white")

    req_table.add_row("Patient Name", req.patient_name or "Emergency Patient")
    req_table.add_row("Blood Group Needed", f"[bold red]{req.blood_group.value}[/bold red]")
    req_table.add_row("Component", f"[bold yellow]{req.component.value}[/bold yellow]")
    req_table.add_row("Units Required", f"[bold green]{req.units} unit(s)[/bold green]")
    req_table.add_row("Hospital", f"{req.hospital_name}")
    req_table.add_row("Location / Zone", f"{req.hospital_address} ({req.zone.value})")
    req_table.add_row("Emergency Urgency", f"[bold red]{req.urgency.value}[/bold red]")
    req_table.add_row("Attendant Contact", f"[bold green]{req.contact_name} - {req.contact_phone}[/bold green]")
    if req.case_or_ip_number:
        req_table.add_row("Case / IP Number", req.case_or_ip_number)
    console.print(req_table)

    # 3. Compatibility & Clinical Criteria
    comp_table = Table(title="🩸 Donor Compatibility & Eligibility", show_header=True, header_style="bold green")
    comp_table.add_column("Attribute", style="cyan", width=22)
    comp_table.add_column("Clinical Directive", style="white")

    compatible_str = ", ".join(f"[bold yellow]{g.value}[/bold yellow]" for g in comp.compatible_donor_groups)
    comp_table.add_row("Compatible Donor Groups", compatible_str)
    comp_table.add_row("Ideal Match", comp.ideal_donor_group.value)
    comp_table.add_row("Universal Donor Rule", comp.universal_donor_for_type)
    comp_table.add_row("Clinical Notes", "\n".join(f"• {note}" for note in comp.clinical_notes))
    comp_table.add_row("Eligibility Checklist", "\n".join(f"• {crit}" for crit in comp.donor_eligibility_criteria[:4]))
    console.print(comp_table)

    # 4. Matched Bangalore Blood Banks Table
    bb_table = Table(title="🏥 Prioritized 24/7 Bengaluru Blood Banks", show_header=True, header_style="bold blue")
    bb_table.add_column("Blood Centre", style="bold white", width=28)
    bb_table.add_column("Area & Metro Link", style="cyan", width=26)
    bb_table.add_column("Phone Helpline", style="green", width=22)
    bb_table.add_column("Bengaluru Transit / Traffic Advisory", style="yellow")

    for bb in result.matched_blood_banks:
        apheresis_badge = " [Apheresis/SDP]" if bb.has_apheresis else ""
        bb_table.add_row(
            f"{bb.name}{apheresis_badge}",
            f"{bb.area}\n{bb.metro_proximity}",
            bb.phone,
            bb.peak_traffic_advisory
        )
    console.print(bb_table)

    # 5. WhatsApp & Kannada Broadcast Panels
    console.print(Panel(
        f"[bold green]English WhatsApp Broadcast:[/bold green]\n\n{sos.english_text}\n\n"
        f"[bold cyan]Direct 1-Click WhatsApp Link:[/bold cyan]\n[underline blue]{sos.whatsapp_share_url}[/underline blue]",
        title="📱 WhatsApp SOS Broadcast",
        border_style="green"
    ))

    console.print(Panel(
        f"[bold yellow]Kannada Broadcast (ತುರ್ತು ಸಂದೇಶ):[/bold yellow]\n\n{sos.kannada_text}\n\n"
        f"[bold white]Phonetic Kannada:[/bold white]\n{sos.kannada_phonetic}",
        title="🟡 Kannada Broadcast (ಸ್ಥಳೀಯ ಭಾಷಾ ಸಂದೇಶ)",
        border_style="yellow"
    ))

    # 6. Actionable Advice
    console.print(Panel(
        result.actionable_advice,
        title="⚡ Actionable Protocol for Attendants",
        border_style="red"
    ))


def run_cli():
    console.print("""
[bold red]
 _   _                                ____       _     _   _           
| \ | | __ _ _ __ ___  _ __ ___   __ |  _ \ __ _| | __| |_| |__   __ _ 
|  \| |/ _` | '_ ` _ \| '_ ` _ \ / _`| |_) / _` | |/ /| __| '_ \ / _` |
| |\  | (_| | | | | | | | | | | | (_||  _ < (_| |   < | |_| | | | (_| |
|_| \_|\__,_|_| |_| |_|_| |_| |_|\__,_|_| \_\__,_|_|\_\ \__|_| |_|\__,_|
[/bold red]
[bold white]Bengaluru Emergency Blood & Platelet Donor Agent[/bold white]
[cyan]Bengaluru 24/7 Clinical Emergency Coordinator[/cyan]
-----------------------------------------------------------------------
    """)

    console.print("[bold yellow]Select a Scenario or Enter Custom Request:[/bold yellow]")
    for key, (title, _) in PRESET_SCENARIOS.items():
        console.print(f"  [bold cyan]{key}[/bold cyan]: {title}")
    console.print("  [bold cyan]5[/bold cyan]: Custom Emergency Request (Type your own prompt)")
    console.print("  [bold cyan]6[/bold cyan]: View All 24/7 Bengaluru Blood Banks Directory")
    console.print("  [bold cyan]q[/bold cyan]: Quit\n")

    choice = Prompt.ask("Enter option", default="1")

    if choice == "q":
        console.print("[yellow]Exiting NammaRaktha. Stay safe![/yellow]")
        sys.exit(0)
    elif choice in PRESET_SCENARIOS:
        title, text = PRESET_SCENARIOS[choice]
        console.print(f"\n[bold green]Running Scenario:[/bold green] {title}")
        console.print(f"[italic]{text}[/italic]\n")
        with console.status("[bold cyan]Triaging emergency with NammaRaktha Agent...[/bold cyan]", spinner="dots"):
            res = agent.triage(text)
        display_triage_result(res)
    elif choice == "5":
        user_input = Prompt.ask("\nEnter emergency details (e.g. blood group, hospital name, contact)")
        if user_input.strip():
            with console.status("[bold cyan]Triaging custom emergency...[/bold cyan]", spinner="dots"):
                res = agent.triage(user_input)
            display_triage_result(res)
    elif choice == "6":
        table = Table(title="🏥 All 24/7 Bengaluru Blood Banks Directory", show_header=True)
        table.add_column("Name", style="bold white")
        table.add_column("Zone", style="cyan")
        table.add_column("Area", style="green")
        table.add_column("Phone", style="yellow")
        table.add_column("Apheresis / SDP", style="magenta")
        for bb in BENGALURU_BLOOD_BANKS:
            table.add_row(
                bb.name,
                bb.zone.value.split("(")[0].strip(),
                bb.area,
                bb.phone,
                "✅ Yes" if bb.has_apheresis else "❌ Whole Blood only"
            )
        console.print(table)
    else:
        console.print("[red]Invalid selection.[/red]")


if __name__ == "__main__":
    run_cli()
