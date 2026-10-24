"""Interactive Command-Line Interface (CLI) for GoalFlow."""

import os
import shutil
import sys
from datetime import date, datetime
from typing import Optional

from goalflow import db, progress
from goalflow.config import get_db_path, get_gemini_api_key, get_model_name
from goalflow.models import GoalLevel, GoalStatus


def print_banner():
    """Display GoalFlow welcome banner."""
    print("=" * 68)
    print("        GoalFlow - Personal Growth & Goal-Reflection AI Agent")
    print("=" * 68)
    print("Type 'help' to see available commands, or type any message to chat.")
    print("Type 'exit' to quit.\n")


def print_help():
    """Print available commands and usage guide."""
    print("\n--- Available Commands ---")
    print("  add-goal          : Create a new goal (yearly, monthly, weekly, daily)")
    print("  list-goals        : List goals in a structured view (optional: level)")
    print("  update-goal       : Update the status of an existing goal")
    print("  reflect           : Record and analyze today's reflection")
    print("  encourage         : Request evidence-based encouragement and perspective")
    print("  achievements      : View or manually record verified milestones/wins")
    print("  progress          : View progress overview and stalled goals")
    print("  check-in          : Perform your daily check-in")
    print("  backup            : Create a local backup copy of your database")
    print("  clear-data        : Delete all saved personal records (privacy reset)")
    print("  help              : Show this help message")
    print("  exit / quit       : Exit GoalFlow")
    print("\nTip: You can also type natural thoughts directly, e.g.:")
    print("     goalflow> I feel like I have not achieved anything this week.\n")


def format_goal_row(goal, sub_info=None) -> str:
    """Format a goal row cleanly for the CLI."""
    status_symbol = {
        GoalStatus.COMPLETED: "[x]",
        GoalStatus.IN_PROGRESS: "[>]",
        GoalStatus.PENDING: "[ ]",
        GoalStatus.ABANDONED: "[-]",
    }.get(goal.status, "[ ]")

    parent_str = f" (parent: #{goal.parent_id})" if goal.parent_id else ""
    date_str = f" [Due: {goal.target_date}]" if goal.target_date else ""
    progress_str = f" ({sub_info['progress_percentage']}% done)" if sub_info and sub_info.get("total_subgoals", 0) > 0 else ""

    return f"  #{goal.id:<3} {status_symbol} [{goal.level.value.upper():<7}] {goal.title}{parent_str}{date_str}{progress_str}"


def handle_add_goal():
    """Interactive flow to create a new goal."""
    print("\n--- Create a New Goal ---")
    title = input("Goal title: ").strip()
    if not title:
        print("Error: Goal title cannot be empty.\n")
        return

    print("Choose level: 1. yearly  2. monthly  3. weekly  4. daily")
    level_choice = input("Level [1-4, default: 4 (daily)]: ").strip()
    level_map = {"1": "yearly", "2": "monthly", "3": "weekly", "4": "daily"}
    level = level_map.get(level_choice, "daily")

    category = input("Category (e.g. learning, career, health) [default: general]: ").strip()
    if not category:
        category = "general"

    parent_id_str = input("Parent Goal ID (optional, press Enter to skip): ").strip()
    parent_id = None
    if parent_id_str:
        try:
            parent_id = int(parent_id_str)
        except ValueError:
            print("Warning: Invalid parent ID. Skipping parent linking.")

    target_date = input("Target Date (YYYY-MM-DD, optional): ").strip() or None

    try:
        new_goal = db.create_goal(
            title=title,
            level=level,
            category=category,
            parent_id=parent_id,
            target_date=target_date,
        )
        print(f"Goal created successfully: #{new_goal.id} [{new_goal.level.value}] '{new_goal.title}'\n")
    except Exception as e:
        print(f"Error creating goal: {e}\n")


def handle_list_goals(arg: str = ""):
    """List goals with filtering."""
    level = arg.strip().lower() if arg else None
    if level and level not in ["yearly", "monthly", "weekly", "daily"]:
        print(f"Unknown level '{level}'. Showing all goals.")
        level = None

    goals = db.list_goals(level=level)
    if not goals:
        print("\nNo goals found. Use 'add-goal' to create one!\n")
        return

    print(f"\n--- Stored Goals {f'({level.upper()})' if level else ''} ---")
    for g in goals:
        sub_info = progress.calculate_goal_progress(g.id)
        print(format_goal_row(g, sub_info))
    print()


def handle_update_goal():
    """Interactive flow to update goal status."""
    print("\n--- Update Goal Status ---")
    gid_str = input("Enter Goal ID to update: ").strip()
    try:
        gid = int(gid_str)
    except ValueError:
        print("Error: Invalid goal ID.\n")
        return

    goal = db.get_goal(gid)
    if not goal:
        print(f"Error: Goal #{gid} not found.\n")
        return

    print(f"Current Goal: #{goal.id} [{goal.status.value}] '{goal.title}'")
    print("Status options: 1. pending  2. in_progress  3. completed  4. abandoned")
    opt = input("Choose status [1-4]: ").strip()
    opt_map = {"1": "pending", "2": "in_progress", "3": "completed", "4": "abandoned"}
    new_status = opt_map.get(opt)
    if not new_status:
        print("Error: Invalid status selected.\n")
        return

    updated = db.update_goal_status(gid, new_status)
    print(f"Goal #{updated.id} status updated to: {updated.status.value}\n")

    # If completed, ask if user wants to log this as a persistent achievement!
    if updated.status == GoalStatus.COMPLETED:
        log_ach = input("Would you like to record this as a permanent achievement milestone? [y/N]: ").strip().lower()
        if log_ach in ("y", "yes"):
            db.create_achievement(
                title=f"Completed: {updated.title}",
                category=updated.category,
                goal_id=updated.id,
            )
            print("Milestone added to your achievement memory!\n")


def handle_reflect(agent_service=None):
    """Handle daily reflection input and processing."""
    print("\n--- Daily Reflection ---")
    print("Share how your day went (what you worked on, what was completed, blockers, how you feel):")
    text = input("Reflection> ").strip()
    if not text:
        print("Reflection cancelled (empty input).\n")
        return

    api_key = get_gemini_api_key()
    if api_key and agent_service:
        print("\nGoalFlow Agent is reflecting on your day...", flush=True)
        prompt = (
            f"Here is my daily reflection: \"{text}\"\n"
            "Please analyze this reflection: extract completed items and obstacles, "
            "save the reflection using record_daily_reflection, suggest one realistic priority "
            "for tomorrow, and if appropriate ask me to confirm any completed goals."
        )
        try:
            response = agent_service.stream_chat(prompt)
            # If agent executed the tool or returned a short tool note, show database details
            latest = db.list_reflections(limit=1)
            if latest and (not response or not response.strip() or len(response.strip().splitlines()) <= 2):
                print(f"\nReflection #{latest[0].id} recorded in your history:")
                print(f"  Summary    : {latest[0].summary}")
                if latest[0].completed_notes:
                    print(f"  Completed  : {latest[0].completed_notes}")
                if latest[0].blockers:
                    print(f"  Blockers   : {latest[0].blockers}")
                if latest[0].next_day_priority:
                    print(f"  Tomorrow   : {latest[0].next_day_priority}\n")
        except Exception as e:
            print(f"\nAgent error: {e}. Falling back to local reflection storage.\n")
            _save_local_reflection(text)
    else:
        _save_local_reflection(text)


def _save_local_reflection(text: str):
    """Fallback local reflection storage without LLM API call."""
    ref = db.create_reflection(
        raw_text=text,
        summary=text[:100] + ("..." if len(text) > 100 else ""),
        completed_notes="Recorded offline",
        blockers="",
        next_day_priority="",
    )
    print(f"Reflection #{ref.id} saved locally.\n")


def handle_encourage(agent_service=None):
    """Provide grounding encouragement based on saved achievements."""
    print("\nReviewing your journey and saved milestones...", flush=True)
    api_key = get_gemini_api_key()
    if api_key and agent_service:
        prompt = (
            "I am feeling a bit discouraged and doubt my progress. "
            "Please check my saved achievements using retrieve_relevant_achievements, "
            "give me grounded evidence of what I've actually done, and suggest one small next step."
        )
        try:
            response = agent_service.stream_chat(prompt)
            if response and response.strip() and len(response.strip().splitlines()) > 1:
                return
        except Exception as e:
            print(f"(Agent communication note: {e})")

    # Direct deterministic evidence presentation
    achievements = db.list_achievements(limit=5)
    if not achievements:
        print("\nYou have not recorded any milestones or achievements yet.")
        print("That doesn't mean you haven't grown—it just means your achievements aren't logged here yet.")
        print("Use 'achievements add' or complete a goal to log your first milestone!\n")
        return

    print(f"\nHere is verified evidence from your personal history ({len(achievements)} milestones):")
    for a in achievements:
        print(f"  * [{a.milestone_date}] {a.title} ({a.category})")
    print("\nRemember: meaningful growth happens through steady, small steps. What is one 10-minute action you can take today?\n")


def handle_achievements(arg: str = ""):
    """View or add achievements."""
    subcmd = arg.strip().lower()
    if subcmd == "add":
        print("\n--- Record an Achievement / Milestone ---")
        title = input("Achievement title: ").strip()
        if not title:
            print("Error: Title cannot be empty.\n")
            return
        category = input("Category [default: learning]: ").strip() or "learning"
        notes = input("Notes / key takeaways (optional): ").strip() or None
        ach = db.create_achievement(title=title, category=category, notes=notes)
        print(f"Milestone saved: #{ach.id} '{ach.title}'\n")
    else:
        achievements = db.list_achievements()
        if not achievements:
            print("\nNo achievements saved yet. Type 'achievements add' to record one!\n")
            return
        print(f"\n--- Saved Achievement Memory ({len(achievements)} total) ---")
        for a in achievements:
            notes_str = f" - {a.notes}" if a.notes else ""
            print(f"  #{a.id:<3} [{a.milestone_date}] {a.title} ({a.category}){notes_str}")
        print()


def handle_progress(arg: str = ""):
    """Display progress overview and stalled goals."""
    timeframe = arg.strip().lower() if arg in ["today", "weekly", "monthly", "yearly"] else "weekly"
    overview = progress.get_progress_overview(timeframe=timeframe)

    print(f"\n================ Progress Overview ({timeframe.upper()}) ================")
    print(f"Period: {overview['start_date']} to {overview['end_date']}")
    print(f"Achievements logged in period : {overview['achievements_count']}")
    print(f"Reflections logged in period  : {overview['reflections_count']}")
    print(f"Yearly Goal Completion Rate   : {overview['yearly_rate']}%")
    print(f"Monthly Goal Completion Rate  : {overview['monthly_rate']}%")
    print(f"Weekly Goal Completion Rate   : {overview['weekly_rate']}%")
    print(f"Daily Goal Completion Rate    : {overview['daily_rate']}%")

    stalled = overview.get("stalled_goals", [])
    if stalled:
        print(f"\nGoals needing attention ({len(stalled)}):")
        for s in stalled:
            reason = "OVERDUE" if s["is_overdue"] else f"inactive for {s['days_inactive']} days"
            print(f"  * #{s['id']} [{s['level'].upper()}] '{s['title']}' ({reason})")
    else:
        print("\nNo stalled goals found. Keep up the momentum!")
    print("=" * 60 + "\n")


def handle_check_in():
    """Perform a daily check-in."""
    today_str = date.today().isoformat()
    latest = db.get_latest_check_in()

    if latest and latest.check_in_date == today_str:
        print(f"\nYou have already checked in today ({today_str}). Great job maintaining consistency!\n")
        return

    db.record_check_in(check_in_date=today_str, status="completed")
    print(f"\nCheck-in recorded for today ({today_str})! You showed up. That is what counts.\n")


def handle_backup():
    """Create a backup of the database file."""
    src = get_db_path()
    if not os.path.exists(src):
        print(f"Database file '{src}' does not exist yet. No data to back up.\n")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = f"goalflow_backup_{timestamp}.db"
    shutil.copy2(src, dest)
    print(f"\nDatabase backed up successfully to: {dest}\n")


def handle_clear_data():
    """Safely wipe personal records after confirmation."""
    print("\nWARNING: This will permanently delete all goals, reflections, achievements, and check-ins.")
    confirm = input("Type 'DELETE' to confirm permanent wipe: ").strip()
    if confirm == "DELETE":
        src = get_db_path()
        if os.path.exists(src):
            os.remove(src)
        db.init_db(src)
        print("All personal records have been completely erased.\n")
    else:
        print("Clear data operation cancelled.\n")


def suggest_command(message: str) -> Optional[str]:
    """Provide rule-based command hints based on message keywords."""
    msg = message.lower()
    if any(k in msg for k in ["check in", "check-in", "checkin", "streak", "showed up"]):
        return "check-in"
    if any(k in msg for k in ["add", "new goal", "create goal", "yearly goal", "monthly goal", "weekly goal", "daily goal", "set a goal"]):
        return "add-goal"
    if any(k in msg for k in ["list", "show goals", "see goals", "view goals", "my goals"]):
        return "list-goals"
    if any(k in msg for k in ["update", "mark complete", "finish goal", "completed goal"]):
        return "update-goal"
    if any(k in msg for k in ["achievement", "milestone", "win", "learned"]):
        return "achievements"
    if any(k in msg for k in ["progress", "stalled", "percentage", "rate", "stats", "overview"]):
        return "progress"
    if any(k in msg for k in ["discourage", "behind", "fail", "not improving", "doubt", "give up", "nothing"]):
        return "encourage"
    if any(k in msg for k in ["reflect", "today", "yesterday", "blocked", "scrolling"]):
        return "reflect"
    return None


def handle_chat_message(message: str, agent_service):
    """Route natural language messages to the GoalFlow ADK agent."""
    suggested = suggest_command(message)
    api_key = get_gemini_api_key()

    if not api_key or not agent_service:
        print("\nNotice: Running in offline mode.")
        if suggested:
            print(f"💡 Recommended Command: Type '{suggested}' to proceed!")
        else:
            print("💡 Tip: Type 'help' to see all available commands.")
        print()
        return

    try:
        print("\nGoalFlow is thinking...", flush=True)
        response = agent_service.stream_chat(message)
        if not response or not response.strip():
            if suggested:
                print(f"\n💡 Recommended Command: Type '{suggested}' to view or configure this!\n")
            else:
                print("\n(Action completed. Type 'help' to see available commands.)\n")
    except Exception as e:
        print(f"\nError communicating with agent: {e}")
        if suggested:
            print(f"💡 Offline Recommendation: Run '{suggested}' directly!\n")


def main():
    """Main CLI execution loop."""
    db.init_db()
    print_banner()

    agent_service = None
    if get_gemini_api_key():
        try:
            from goalflow.agent import GoalFlowAgentService
            agent_service = GoalFlowAgentService()
        except Exception as e:
            print(f"(Note: Could not initialize AI Agent service: {e})")

    while True:
        try:
            raw_input_line = input("goalflow> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Keep making steady progress.")
            break

        if not raw_input_line:
            continue

        parts = raw_input_line.split(" ", 1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if command in ("exit", "quit", "q"):
            print("Goodbye! Keep making steady progress.")
            break
        elif command == "help":
            print_help()
        elif command == "add-goal":
            handle_add_goal()
        elif command == "list-goals":
            handle_list_goals(arg)
        elif command == "update-goal":
            handle_update_goal()
        elif command == "reflect":
            handle_reflect(agent_service)
        elif command == "encourage":
            handle_encourage(agent_service)
        elif command == "achievements":
            handle_achievements(arg)
        elif command == "progress":
            handle_progress(arg)
        elif command == "check-in":
            handle_check_in()
        elif command == "backup":
            handle_backup()
        elif command == "clear-data":
            handle_clear_data()
        else:
            # Treat unknown command as a natural conversational prompt to the agent!
            handle_chat_message(raw_input_line, agent_service)


if __name__ == "__main__":
    main()
