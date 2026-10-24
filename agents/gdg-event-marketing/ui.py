import argparse
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import List, Optional

import requests

from dotenv import load_dotenv
from google import genai

from agent import (
    CHANNEL_PROMPTS,
    DEFAULT_MODEL,
    GDGEventMarketingAgent,
    build_demo_content,
    build_demo_event,
    fetch_upcoming_events,
)

CHANNEL_LABELS = {
    "linkedin": "LinkedIn",
    "twitter": "X",
    "email_newsletter": "Newsletter",
}
TONE_OPTIONS = (
    "Friendly and welcoming",
    "Professional",
    "Energetic",
    "Educational",
    "Casual and conversational",
)
EVENT_FIELDS = (
    ("title", "Event title"),
    ("date_time", "Date and time"),
    ("location", "Location"),
    ("speakers", "Speaker(s)"),
    ("url", "Event link"),
    ("description", "Description"),
)


def run_demo_generation(event: Optional[dict] = None) -> tuple[dict, dict]:
    selected_event = event or build_demo_event()
    return selected_event, build_demo_content(selected_event)


def run_live_generation(
    chapter_id: str,
    api_key: str,
    model_name: str,
    event: dict,
    options: dict,
) -> tuple[dict, dict]:
    client = genai.Client(api_key=api_key)
    agent = GDGEventMarketingAgent(chapter_id, client, model_name)
    return event, agent.generate_content(event, **options)


class EventMarketingApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GDG Event Marketing Studio")
        self.root.geometry("1080x860")
        self.root.minsize(780, 650)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.results: queue.Queue = queue.Queue()
        self.output_widgets: dict[str, ScrolledText] = {}
        self.channel_vars = {
            channel: tk.BooleanVar(value=True) for channel in CHANNEL_PROMPTS
        }
        self.event_vars = {
            field: tk.StringVar() for field, _label in EVENT_FIELDS
        }
        self.mode = tk.StringVar(value="demo")
        self.chapter_id = tk.StringVar(value="")
        self.api_key = tk.StringVar()
        self.tone = tk.StringVar(value=TONE_OPTIONS[0])
        self.audience = tk.StringVar(
            value="GDG community members and people curious about the topic"
        )
        self.call_to_action = tk.StringVar(value="Learn more using the event link")
        self.custom_instructions = tk.StringVar()
        self.event_choice = tk.StringVar(value="")
        self.status = tk.StringVar(value="Demo mode is ready. Review or edit event details, then generate.")
        self.event_summary = tk.StringVar(value="Demo event loaded.")
        self.char_counts: dict[str, tk.StringVar] = {}
        self.events: list[dict] = []
        self.current_event: dict = {}
        self.busy = False
        self.closed = False
        self._load_configuration()
        self._build_layout()
        self._load_event(build_demo_event())
        self.root.after(100, self._process_results)

    def _load_configuration(self) -> None:
        load_dotenv(Path(__file__).with_name(".env"))
        self.chapter_id.set(os.getenv("GDG_CHAPTER_ID", ""))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            header, text="GDG Event Marketing Studio", font=("Segoe UI", 21, "bold")
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="One event in. Platform-ready drafts out. You stay in control of what gets published.",
            wraplength=1000,
        ).pack(anchor="w", pady=(3, 0))

        content = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        content.grid(row=1, column=0, sticky="nsew")
        setup = ttk.Frame(content, padding=(0, 0, 0, 8))
        drafts = ttk.Frame(content)
        content.add(setup, weight=3)
        content.add(drafts, weight=2)
        self._build_setup(setup)
        self._build_drafts(drafts)

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, textvariable=self.status, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(footer, text="Help", command=self._show_help).pack(side=tk.RIGHT)

    def _build_setup(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        controls = ttk.Frame(parent)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="Workflow").grid(row=0, column=0, sticky="w")
        self.mode_box = ttk.Combobox(
            controls,
            textvariable=self.mode,
            values=("Offline demo", "Live: GDG event", "Live: custom event"),
            state="readonly",
            width=22,
        )
        self.mode_box.grid(row=0, column=1, sticky="w", padx=(6, 14))
        self.mode_box.current(0)
        self.mode_box.bind("<<ComboboxSelected>>", self._mode_changed)

        ttk.Label(controls, text="Chapter ID").grid(row=0, column=2, sticky="w")
        self.chapter_entry = ttk.Entry(controls, textvariable=self.chapter_id, width=16)
        self.chapter_entry.grid(row=0, column=3, sticky="ew", padx=(6, 6))
        self.find_events_button = ttk.Button(
            controls, text="Find events", command=self._fetch_events
        )
        self.find_events_button.grid(row=0, column=4, sticky="w")

        self.events_box = ttk.Combobox(
            controls, textvariable=self.event_choice, state="readonly", width=38
        )
        self.events_box.grid(row=0, column=5, sticky="ew", padx=(10, 0))
        self.events_box.bind("<<ComboboxSelected>>", self._select_event)

        settings = ttk.LabelFrame(parent, text="1. Event details and writing preferences", padding=10)
        settings.grid(row=1, column=0, sticky="nsew")
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)
        settings.rowconfigure(4, weight=1)

        for index, (field, label) in enumerate(EVENT_FIELDS[:4]):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(settings, text=label).grid(
                row=row, column=col, sticky="w", padx=(0, 6), pady=3
            )
            ttk.Entry(settings, textvariable=self.event_vars[field]).grid(
                row=row, column=col + 1, sticky="ew", padx=(0, 12), pady=3
            )

        ttk.Label(settings, text="Event link").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.event_vars["url"]).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=3
        )
        ttk.Label(settings, text="Description").grid(
            row=3, column=0, sticky="nw", pady=3
        )
        self.description_text = ScrolledText(settings, height=3, wrap=tk.WORD)
        self.description_text.grid(
            row=3, column=1, columnspan=3, sticky="ew", pady=3
        )
        self.description_text.bind("<KeyRelease>", self._event_edited)

        preferences = ttk.Frame(settings)
        preferences.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        preferences.columnconfigure(1, weight=1)
        preferences.columnconfigure(3, weight=1)
        ttk.Label(preferences, text="Tone").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            preferences,
            textvariable=self.tone,
            values=TONE_OPTIONS,
            state="readonly",
            width=27,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 14))
        ttk.Label(preferences, text="Audience").grid(row=0, column=2, sticky="w")
        ttk.Entry(preferences, textvariable=self.audience).grid(
            row=0, column=3, sticky="ew", padx=(6, 0)
        )
        ttk.Label(preferences, text="Call to action").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(preferences, textvariable=self.call_to_action).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(6, 0)
        )
        ttk.Label(preferences, text="Extra guidance").grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(preferences, textvariable=self.custom_instructions).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=(6, 0)
        )

        live_settings = ttk.Frame(settings)
        live_settings.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(live_settings, text="Gemini API key").pack(side=tk.LEFT)
        self.key_entry = ttk.Entry(live_settings, textvariable=self.api_key, show="*", width=38)
        self.key_entry.pack(side=tk.LEFT, padx=6)
        ttk.Label(
            live_settings,
            text="Only used for this session; local .env also works.",
            foreground="#555555",
        ).pack(side=tk.LEFT)

        self._update_mode_controls()

    def _build_drafts(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(toolbar, text="2. Drafts", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        self.generate_button = ttk.Button(
            toolbar, text="Generate drafts", command=self._start_generation
        )
        self.generate_button.pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Save all…", command=self._save_all).pack(
            side=tk.RIGHT, padx=(0, 6)
        )
        ttk.Button(toolbar, text="Copy draft", command=self._copy_selected).pack(
            side=tk.RIGHT, padx=(0, 6)
        )
        self.regenerate_button = ttk.Button(
            toolbar, text="Regenerate this tab", command=self._regenerate_selected
        )
        self.regenerate_button.pack(side=tk.RIGHT, padx=(0, 6))

        self.event_summary_label = ttk.Label(
            parent, textvariable=self.event_summary, wraplength=1000
        )
        self.event_summary_label.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.tabs = ttk.Notebook(parent)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        parent.rowconfigure(2, weight=1)

        for channel, title in CHANNEL_LABELS.items():
            panel = ttk.Frame(self.tabs, padding=5)
            panel.rowconfigure(0, weight=1)
            panel.columnconfigure(0, weight=1)
            output = ScrolledText(panel, wrap=tk.WORD, font=("Segoe UI", 10), undo=True)
            output.grid(row=0, column=0, sticky="nsew")
            output.bind("<KeyRelease>", lambda _event, key=channel: self._update_count(key))
            footer = ttk.Frame(panel)
            footer.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            count = tk.StringVar(value="0 words")
            self.char_counts[channel] = count
            ttk.Label(footer, textvariable=count).pack(side=tk.LEFT)
            selected = ttk.Checkbutton(
                footer,
                text="Include in generation",
                variable=self.channel_vars[channel],
            )
            selected.pack(side=tk.RIGHT)
            self.output_widgets[channel] = output
            self.tabs.add(panel, text=title)
        self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._set_draft_actions(False)

    def _mode_changed(self, _event=None) -> None:
        self._update_mode_controls()
        if self.mode.get() == "Offline demo":
            self._load_event(build_demo_event())
            self.status.set("Offline demo selected. No API calls will be made.")
        elif self.mode.get() == "Live: custom event":
            self.status.set("Enter your own event details, then generate drafts.")
        else:
            self.status.set("Enter a chapter ID and use Find events to load upcoming events.")

    def _update_mode_controls(self) -> None:
        live = self.mode.get() != "Offline demo"
        event_search = self.mode.get() == "Live: GDG event"
        self.chapter_entry.configure(state=tk.NORMAL if event_search else tk.DISABLED)
        self.find_events_button.configure(state=tk.NORMAL if event_search else tk.DISABLED)
        self.events_box.configure(state="readonly" if event_search else tk.DISABLED)
        self.key_entry.configure(state=tk.NORMAL if live else tk.DISABLED)

    def _load_event(self, event: dict) -> None:
        self.current_event = dict(event)
        for field, _label in EVENT_FIELDS:
            self.event_vars[field].set(str(event.get(field, "")))
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", event.get("description", ""))
        marker = "Fictional demo - " if event.get("chapter_id") == "DEMO-CHAPTER-001 (fictional)" else ""
        self.event_summary.set(
            f"{marker}{event.get('title', 'Event details')} | "
            f"{event.get('date_time', '')} | {event.get('location', '')}"
        )

    def _read_event(self) -> dict:
        event = {field: variable.get().strip() for field, variable in self.event_vars.items()}
        event["description"] = self.description_text.get("1.0", "end-1c").strip()
        event["chapter_id"] = (
            "DEMO-CHAPTER-001 (fictional)"
            if self.mode.get() == "Offline demo"
            else self.chapter_id.get().strip()
        )
        return event

    def _fetch_events(self) -> None:
        chapter_id = self.chapter_id.get().strip()
        if not chapter_id:
            messagebox.showerror("Chapter ID required", "Enter a GDG Community chapter ID.")
            self.chapter_entry.focus_set()
            return
        self._set_busy(True, "Finding upcoming published events…")
        self._start_worker("events", fetch_upcoming_events, chapter_id)

    def _select_event(self, _event=None) -> None:
        index = self.events_box.current()
        if 0 <= index < len(self.events):
            self._load_event(self.events[index])
            self.status.set("Event details loaded. You can edit them before generating.")

    def _validate(self, channels: List[str]) -> tuple[dict, Optional[dict]]:
        event = self._read_event()
        if not event["title"]:
            return event, {"title": "Event title required", "message": "Add an event title."}
        if not event["description"]:
            return event, {"title": "Description required", "message": "Add a short event description."}
        if not channels:
            return event, {"title": "Choose a channel", "message": "Select at least one output channel."}
        if self.mode.get() != "Offline demo":
            if not event["date_time"]:
                return event, {"title": "Date and time required", "message": "Add the event date and time."}
            if not self.chapter_id.get().strip() and self.mode.get() == "Live: GDG event":
                return event, {"title": "Chapter ID required", "message": "Enter a GDG Community chapter ID."}
            api_key = self.api_key.get().strip() or os.getenv("GEMINI_API_KEY", "").strip()
            if not api_key or api_key == "your_gemini_api_key_here":
                return event, {"title": "Gemini API key required", "message": "Enter your key or set GEMINI_API_KEY in your local .env."}
        return event, None

    def _start_generation(self, channels: Optional[List[str]] = None) -> None:
        if self.busy:
            return
        selected = channels or [
            channel for channel, variable in self.channel_vars.items() if variable.get()
        ]
        event, error = self._validate(selected)
        if error:
            messagebox.showerror(error["title"], error["message"])
            return
        if self.mode.get() == "Offline demo":
            self._set_busy(True, "Building fictional sample drafts…")
            self._start_worker("generate", run_demo_generation, event, selected)
            return

        chapter_id = self.chapter_id.get().strip() or event.get("chapter_id", "")
        api_key = self.api_key.get().strip() or os.getenv("GEMINI_API_KEY", "").strip()
        model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        options = {
            "tone": self.tone.get(),
            "audience": self.audience.get().strip(),
            "call_to_action": self.call_to_action.get().strip(),
            "custom_instructions": self.custom_instructions.get().strip(),
            "channels": selected,
        }
        self._set_busy(True, "Generating drafts with Gemini…")
        self._start_worker(
            "generate",
            run_live_generation,
            chapter_id,
            api_key,
            model,
            event,
            options,
        )

    def _regenerate_selected(self) -> None:
        channel = self._selected_channel()
        if channel:
            self._start_generation([channel])

    def _start_worker(self, action: str, function, *args) -> None:
        threading.Thread(
            target=self._worker,
            args=(action, function, args),
            daemon=True,
        ).start()

    def _worker(self, action: str, function, args: tuple) -> None:
        try:
            result = function(*args)
            self.results.put((action, "success", result))
        except (requests.RequestException, genai.errors.APIError, ValueError, RuntimeError) as exc:
            self.results.put((action, "error", str(exc)))

    def _process_results(self) -> None:
        if self.closed:
            return
        try:
            action, result_type, result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._process_results)
            return

        self._set_busy(False)
        if result_type == "error":
            self.status.set("The request failed. Check the details and try again.")
            messagebox.showerror("Could not complete request", result)
        elif action == "events":
            self.events = result
            if not self.events:
                self.event_choice.set("")
                self.events_box.configure(values=())
                self.status.set("No upcoming published events found for this chapter.")
            else:
                values = [
                    f"{event['date_time']} — {event['title']}"
                    for event in self.events
                ]
                self.events_box.configure(values=values)
                self.events_box.current(0)
                self._load_event(self.events[0])
                self.status.set(f"Found {len(self.events)} upcoming event(s). Select one or edit the details.")
        else:
            event, assets = result
            self._merge_drafts(event, assets)
            is_demo = self.mode.get() == "Offline demo"
            self.status.set(
                "Fictional sample drafts ready. No API calls were made."
                if is_demo
                else "Drafts ready. Review and edit them; nothing was published."
            )
        self.root.after(100, self._process_results)

    def _merge_drafts(self, event: dict, assets: dict) -> None:
        self.current_event = dict(event)
        self.event_summary.set(
            f"{'Fictional demo - ' if self.mode.get() == 'Offline demo' else ''}"
            f"{event.get('title', 'Event')} | {event.get('date_time', '')} | "
            f"{event.get('location', '')}"
        )
        for channel, text in assets.items():
            widget = self.output_widgets[channel]
            widget.delete("1.0", tk.END)
            widget.insert("1.0", text)
            self._update_count(channel)
        self._set_draft_actions(any(
            widget.get("1.0", "end-1c").strip()
            for widget in self.output_widgets.values()
        ))

    def _selected_channel(self) -> Optional[str]:
        if not self.tabs.select():
            return None
        index = self.tabs.index(self.tabs.select())
        return tuple(CHANNEL_LABELS)[index]

    def _tab_changed(self, _event=None) -> None:
        self.regenerate_button.configure(
            state=tk.NORMAL if self._selected_channel() else tk.DISABLED
        )

    def _update_count(self, channel: str) -> None:
        text = self.output_widgets[channel].get("1.0", "end-1c")
        words = len(text.split())
        self.char_counts[channel].set(f"{len(text)} characters · {words} words")

    def _event_edited(self, _event=None) -> None:
        self.current_event = self._read_event()

    def _copy_selected(self) -> None:
        channel = self._selected_channel()
        if not channel:
            return
        text = self.output_widgets[channel].get("1.0", "end-1c")
        if not text.strip():
            self.status.set("Generate a draft before copying.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except tk.TclError as exc:
            messagebox.showerror("Clipboard unavailable", str(exc))
            return
        self.status.set(f"{CHANNEL_LABELS[channel]} draft copied to clipboard.")

    def _save_all(self) -> None:
        drafts = {
            channel: widget.get("1.0", "end-1c").strip()
            for channel, widget in self.output_widgets.items()
        }
        drafts = {channel: text for channel, text in drafts.items() if text}
        if not drafts:
            self.status.set("Generate drafts before exporting.")
            return
        path = filedialog.asksaveasfilename(
            title="Save reviewed marketing drafts",
            defaultextension=".md",
            filetypes=(("Markdown", "*.md"), ("Text file", "*.txt"), ("All files", "*.*")),
            initialfile="gdg-event-marketing-drafts.md",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as output:
                output.write(f"# {self.current_event.get('title', 'GDG event drafts')}\n\n")
                output.write("> Review/export generated drafts. Nothing was published.\n\n")
                for channel, text in drafts.items():
                    output.write(f"## {CHANNEL_LABELS[channel]}\n\n{text}\n\n")
        except OSError as exc:
            messagebox.showerror("Could not save drafts", str(exc))
            return
        self.status.set(f"Saved {len(drafts)} draft(s) to the selected file.")

    def _set_busy(self, busy: bool, message: Optional[str] = None) -> None:
        self.busy = busy
        self.generate_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.find_events_button.configure(
            state=tk.DISABLED
            if busy or self.mode.get() != "Live: GDG event"
            else tk.NORMAL
        )
        if message:
            self.status.set(message)

    def _set_draft_actions(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.regenerate_button.configure(state=state)

    def _show_help(self) -> None:
        messagebox.showinfo(
            "Quick help",
            "OFFLINE DEMO: Generates fictional examples without internet or a key.\n\n"
            "LIVE GDG EVENT: Enter a chapter ID, find an upcoming event, review/edit "
            "its details, choose channels and writing preferences, then generate.\n\n"
            "LIVE CUSTOM EVENT: Enter your own event details and generate drafts.\n\n"
            "Edit drafts directly in their tabs. Copy one draft or save all drafts "
            "to a Markdown file. The agent never publishes content.",
        )

    def _close(self) -> None:
        self.closed = True
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="GDG Event Marketing desktop interface.")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Open the interface with fictional sample drafts loaded",
    )
    args = parser.parse_args()
    root = tk.Tk()
    app = EventMarketingApp(root)
    if args.demo:
        root.after(100, app._start_generation)
    root.mainloop()


if __name__ == "__main__":
    main()
