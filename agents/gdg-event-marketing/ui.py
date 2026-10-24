import argparse
import os
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import List, Optional

import keyring
import requests

from dotenv import load_dotenv
from google import genai
from campaign import build_campaign_ics, build_event_campaign
from creative import render_carousel_html
from publishing import (
    authorize_linkedin,
    disconnect_linkedin,
    get_linkedin_connection,
    publish_linkedin_post,
)

from agent import (
    CHANNEL_PROMPTS,
    DEMO_CHAPTER_ID,
    DEFAULT_MODEL,
    GDGEventMarketingAgent,
    build_demo_content,
    build_demo_event,
    fetch_upcoming_events,
)

GOOGLE_COLORS = {
    "blue": "#4285F4",
    "red": "#EA4335",
    "yellow": "#FBBC04",
    "green": "#34A853",
    "background": "#F8FAFD",
    "surface": "#FFFFFF",
    "text": "#202124",
    "muted": "#5F6368",
    "border": "#DADCE0",
    "pale_blue": "#E8F0FE",
}

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


def run_demo_generation(
    event: Optional[dict] = None, channels: Optional[List[str]] = None
) -> tuple[dict, dict]:
    selected_event = event or build_demo_event()
    assets = build_demo_content(selected_event)
    if channels is not None:
        invalid_channels = set(channels) - set(assets)
        if invalid_channels:
            raise ValueError(f"Unsupported channels: {', '.join(sorted(invalid_channels))}")
        assets = {channel: assets[channel] for channel in channels}
    return selected_event, assets


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


def run_linkedin_connection(
    client_id: str, client_secret: str, redirect_uri: str
) -> str:
    connection = authorize_linkedin(client_id, client_secret, redirect_uri)
    return connection.name


def run_linkedin_publish(draft: str, api_version: str) -> str:
    return publish_linkedin_post(draft, api_version)


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
        self.campaign_plan: list[dict] = []
        self.campaign_event: Optional[dict] = None
        self.campaign_text: Optional[ScrolledText] = None
        self.linkedin_draft_event: Optional[dict] = None
        self.linkedin_account = tk.StringVar(value="LinkedIn not connected")
        self.busy = False
        self.closed = False
        self._load_configuration()
        self._configure_theme()
        self._build_layout()
        self._load_linkedin_connection()
        self._load_event(build_demo_event())
        self.root.after(100, self._process_results)

    def _load_configuration(self) -> None:
        load_dotenv(Path(__file__).with_name(".env"))
        self.chapter_id.set(os.getenv("GDG_CHAPTER_ID", ""))

    def _configure_theme(self) -> None:
        colors = GOOGLE_COLORS
        self.root.configure(background=colors["background"])
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", background=colors["background"], foreground=colors["text"])
        style.configure("TFrame", background=colors["background"])
        style.configure("Card.TFrame", background=colors["surface"])
        style.configure("Header.TFrame", background=colors["surface"])
        style.configure("TLabel", background=colors["background"], foreground=colors["text"])
        style.configure("Header.TLabel", background=colors["surface"], foreground=colors["text"])
        style.configure(
            "Muted.TLabel", background=colors["surface"], foreground=colors["muted"]
        )
        style.configure(
            "Title.TLabel",
            background=colors["surface"],
            foreground=colors["text"],
            font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "Section.TLabel",
            background=colors["background"],
            foreground=colors["text"],
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "TLabelframe",
            background=colors["background"],
            bordercolor=colors["border"],
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=colors["background"],
            foreground=colors["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "TEntry",
            fieldbackground=colors["surface"],
            foreground=colors["text"],
            insertcolor=colors["text"],
            bordercolor=colors["border"],
            padding=6,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", colors["blue"])],
            lightcolor=[("focus", colors["blue"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["surface"],
            background=colors["surface"],
            foreground=colors["text"],
            arrowcolor=colors["muted"],
            bordercolor=colors["border"],
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["surface"])],
            selectbackground=[("readonly", colors["pale_blue"])],
            selectforeground=[("readonly", colors["text"])],
        )
        style.configure(
            "TButton",
            background=colors["surface"],
            foreground=colors["text"],
            bordercolor=colors["border"],
            padding=(10, 6),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TButton",
            background=[("pressed", colors["pale_blue"]), ("active", colors["pale_blue"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure(
            "Primary.TButton",
            background=colors["blue"],
            foreground=colors["surface"],
            bordercolor=colors["blue"],
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", colors["border"]),
                ("pressed", "#3367D6"),
                ("active", "#3367D6"),
            ],
            foreground=[("disabled", colors["muted"]), ("!disabled", colors["surface"])],
        )
        style.configure(
            "TCheckbutton", background=colors["background"], foreground=colors["text"]
        )
        style.map("TCheckbutton", background=[("active", colors["background"])])
        style.configure(
            "TNotebook",
            background=colors["background"],
            bordercolor=colors["border"],
            tabmargins=(0, 2, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=colors["surface"],
            foreground=colors["muted"],
            padding=(14, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", colors["pale_blue"]), ("active", colors["surface"])],
            foreground=[("selected", colors["blue"]), ("active", colors["text"])],
        )
        style.configure("TPanedwindow", background=colors["background"])

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer, style="Header.TFrame", padding=(16, 12))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        accent = tk.Frame(header, height=4, background=GOOGLE_COLORS["surface"])
        accent.pack(fill=tk.X, pady=(0, 10))
        for color in ("blue", "red", "yellow", "green"):
            tk.Frame(accent, height=4, background=GOOGLE_COLORS[color]).pack(
                side=tk.LEFT, fill=tk.X, expand=True
            )
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(fill=tk.X)
        logo = tk.Canvas(
            brand,
            width=48,
            height=38,
            background=GOOGLE_COLORS["surface"],
            highlightthickness=0,
        )
        logo.pack(side=tk.LEFT, padx=(0, 10))
        logo_scale = 1.15
        logo_x, logo_y = 4, 9
        bracket_paths = (
            (
                GOOGLE_COLORS["red"],
                ((1.33, 5.94), (8.84, 0.60), (13.30, 1.32), (12.57, 5.74), (5.06, 11.09), (0.60, 10.36)),
            ),
            (
                GOOGLE_COLORS["blue"],
                ((0.60, 6.64), (5.06, 5.91), (12.57, 11.26), (13.30, 15.68), (8.84, 16.40), (1.33, 11.05)),
            ),
            (
                GOOGLE_COLORS["yellow"],
                ((18.70, 1.33), (23.16, 0.60), (30.67, 5.95), (31.40, 10.37), (26.94, 11.10), (19.43, 5.75)),
            ),
            (
                GOOGLE_COLORS["green"],
                ((19.43, 11.25), (26.94, 5.90), (31.40, 6.63), (30.67, 11.05), (23.16, 16.40), (18.70, 15.67)),
            ),
        )
        for color, points in bracket_paths:
            coordinates = [
                coordinate * logo_scale + (logo_x if index % 2 == 0 else logo_y)
                for point in points
                for index, coordinate in enumerate(point)
            ]
            logo.create_polygon(
                coordinates,
                fill=color,
                outline=color,
                smooth=True,
                splinesteps=12,
            )
        title_block = ttk.Frame(brand, style="Header.TFrame")
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            title_block, text="Google Developer Groups", style="Title.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            title_block,
            text="EVENT MARKETING STUDIO · INDEPENDENT COMMUNITY PROJECT",
            wraplength=1000,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Label(
            title_block,
            text="One event in. Platform-ready drafts out. You stay in control of what gets published.",
            wraplength=1000,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

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
        self.description_text = ScrolledText(
            settings,
            height=3,
            wrap=tk.WORD,
            background=GOOGLE_COLORS["surface"],
            foreground=GOOGLE_COLORS["text"],
            insertbackground=GOOGLE_COLORS["text"],
            selectbackground=GOOGLE_COLORS["pale_blue"],
            selectforeground=GOOGLE_COLORS["text"],
            relief=tk.FLAT,
            padx=8,
            pady=6,
            highlightthickness=1,
            highlightbackground=GOOGLE_COLORS["border"],
            highlightcolor=GOOGLE_COLORS["blue"],
        )
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
        ttk.Label(toolbar, text="2. Drafts", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Create visual carousel",
            command=self._create_visual_carousel,
        ).pack(side=tk.LEFT, padx=(12, 0))
        self.generate_button = ttk.Button(
            toolbar,
            text="Generate drafts",
            command=self._start_generation,
            style="Primary.TButton",
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
            output = ScrolledText(
                panel,
                wrap=tk.WORD,
                font=("Segoe UI", 10),
                undo=True,
                background=GOOGLE_COLORS["surface"],
                foreground=GOOGLE_COLORS["text"],
                insertbackground=GOOGLE_COLORS["text"],
                selectbackground=GOOGLE_COLORS["pale_blue"],
                selectforeground=GOOGLE_COLORS["text"],
                relief=tk.FLAT,
                padx=12,
                pady=10,
                highlightthickness=1,
                highlightbackground=GOOGLE_COLORS["border"],
                highlightcolor=GOOGLE_COLORS["blue"],
            )
            output.grid(row=0, column=0, sticky="nsew")
            output.bind("<KeyRelease>", lambda _event, key=channel: self._update_count(key))
            footer = ttk.Frame(panel)
            footer.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            count = tk.StringVar(value="0 words")
            self.char_counts[channel] = count
            ttk.Label(footer, textvariable=count).pack(side=tk.LEFT)
            if channel == "linkedin":
                ttk.Label(footer, textvariable=self.linkedin_account).pack(
                    side=tk.LEFT, padx=(12, 4)
                )
                linkedin_controls = ttk.Frame(panel)
                linkedin_controls.grid(
                    row=2, column=0, sticky="ew", pady=(4, 0)
                )
                self.linkedin_connect_button = ttk.Button(
                    linkedin_controls,
                    text="Connect LinkedIn",
                    command=self._connect_linkedin,
                )
                self.linkedin_connect_button.pack(side=tk.RIGHT, padx=(6, 0))
                self.publish_linkedin_button = ttk.Button(
                    linkedin_controls,
                    text="Publish to LinkedIn",
                    command=self._publish_linkedin,
                    state=tk.DISABLED,
                )
                self.publish_linkedin_button.pack(side=tk.RIGHT, padx=(6, 0))
                self.linkedin_disconnect_button = ttk.Button(
                    linkedin_controls,
                    text="Disconnect",
                    command=self._disconnect_linkedin,
                )
                self.linkedin_disconnect_button.pack(side=tk.RIGHT, padx=(6, 0))
            selected = ttk.Checkbutton(
                footer,
                text="Include in generation",
                variable=self.channel_vars[channel],
            )
            selected.pack(side=tk.RIGHT)
            self.output_widgets[channel] = output
            self.tabs.add(panel, text=title)
        self._build_campaign_tab()
        self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._set_draft_actions(False)

    def _build_campaign_tab(self) -> None:
        panel = ttk.Frame(self.tabs, padding=8)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        controls = ttk.Frame(panel)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            controls,
            text="Build event timeline",
            command=self._create_campaign_plan,
            style="Primary.TButton",
        ).pack(side=tk.LEFT)
        ttk.Button(
            controls,
            text="Export calendar reminders…",
            command=self._export_campaign_calendar,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.campaign_text = ScrolledText(
            panel,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
            undo=True,
            background=GOOGLE_COLORS["surface"],
            foreground=GOOGLE_COLORS["text"],
            insertbackground=GOOGLE_COLORS["text"],
            selectbackground=GOOGLE_COLORS["pale_blue"],
            selectforeground=GOOGLE_COLORS["text"],
            relief=tk.FLAT,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=GOOGLE_COLORS["border"],
            highlightcolor=GOOGLE_COLORS["blue"],
        )
        self.campaign_text.grid(row=1, column=0, sticky="nsew")
        self.campaign_text.insert(
            "1.0",
            "Create a locally planned event campaign with an announcement, "
            "topic spotlight, one-day reminder, and post-event follow-up.\n\n"
            "The planner does not publish posts. You can edit the copy here and "
            "export calendar reminders for manual review.",
        )
        self.tabs.add(panel, text="Campaign timeline")

    def _mode_changed(self, _event=None) -> None:
        self._update_mode_controls()
        if self.mode.get() == "Offline demo":
            self._load_event(build_demo_event())
            self.status.set("Offline demo selected. No API calls will be made.")
        elif self.mode.get() == "Live: custom event":
            if self.current_event.get("chapter_id") == DEMO_CHAPTER_ID:
                self._load_event({})
            self.status.set("Enter your own event details, then generate drafts.")
        else:
            if self.current_event.get("chapter_id") == DEMO_CHAPTER_ID:
                self._load_event({})
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
        self.campaign_plan = []
        self.campaign_event = None
        if self.campaign_text is not None:
            self.campaign_text.delete("1.0", tk.END)
            self.campaign_text.insert(
                "1.0", "Event changed. Build a new timeline to refresh the plan."
            )
        for field, _label in EVENT_FIELDS:
            self.event_vars[field].set(str(event.get(field, "")))
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert("1.0", event.get("description", ""))
        marker = "Fictional demo - " if event.get("chapter_id") == DEMO_CHAPTER_ID else ""
        self.event_summary.set(
            f"{marker}{event.get('title', 'Event details')} | "
            f"{event.get('date_time', '')} | {event.get('location', '')}"
        )

    def _read_event(self) -> dict:
        event = {field: variable.get().strip() for field, variable in self.event_vars.items()}
        event["description"] = self.description_text.get("1.0", "end-1c").strip()
        event["chapter_id"] = (
            DEMO_CHAPTER_ID
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
        sensitive_values = []
        if function is run_live_generation and len(args) > 1 and args[1]:
            sensitive_values.append((args[1], "[redacted API key]"))
        if function is run_linkedin_connection and len(args) > 1 and args[1]:
            sensitive_values.append((args[1], "[redacted LinkedIn client secret]"))

        def redact(message: str) -> str:
            for value, replacement in sensitive_values:
                message = message.replace(value, replacement)
            return message

        try:
            result = function(*args)
            self.results.put((action, "success", result))
        except (requests.RequestException, genai.errors.APIError, ValueError, RuntimeError) as exc:
            self.results.put((action, "error", redact(str(exc))))
        except Exception as exc:
            error = redact(str(exc))
            self.results.put((action, "error", f"Unexpected {type(exc).__name__}: {error}"))

    def _load_linkedin_connection(self) -> None:
        try:
            connection = get_linkedin_connection()
        except (ValueError, keyring.errors.KeyringError) as exc:
            self.linkedin_account.set("LinkedIn connection unavailable")
            self.status.set(f"Could not read the local credential store: {exc}")
            return
        if connection:
            self.linkedin_account.set(f"Connected as {connection.name}")

    def _connect_linkedin(self) -> None:
        if self.busy:
            return
        client_id = os.getenv("LINKEDIN_CLIENT_ID", "").strip()
        client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("LINKEDIN_REDIRECT_URI", "").strip()
        if not client_id or not client_secret or not redirect_uri:
            messagebox.showerror(
                "LinkedIn setup required",
                "Set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, and "
                "LINKEDIN_REDIRECT_URI in your local .env file. See the README "
                "for the one-time LinkedIn app and Render callback setup.",
            )
            return
        self._set_busy(True, "Opening LinkedIn authorization in your browser…")
        try:
            self._start_worker(
                "linkedin_connect",
                run_linkedin_connection,
                client_id,
                client_secret,
                redirect_uri,
            )
        except OSError as exc:
            self._set_busy(False)
            messagebox.showerror("Could not start LinkedIn authorization", str(exc))

    def _disconnect_linkedin(self) -> None:
        if self.busy:
            return
        try:
            removed = disconnect_linkedin()
        except keyring.errors.KeyringError as exc:
            messagebox.showerror("Could not disconnect LinkedIn", str(exc))
            return
        self.linkedin_account.set("LinkedIn not connected")
        self.status.set(
            "Saved LinkedIn authorization removed from this device."
            if removed
            else "No saved LinkedIn authorization was found."
        )

    def _publish_linkedin(self) -> None:
        if self.busy:
            return
        draft = self.output_widgets["linkedin"].get("1.0", "end-1c").strip()
        event = self._read_event()
        if not draft:
            messagebox.showinfo(
                "LinkedIn draft required", "Generate a LinkedIn draft first."
            )
            return
        if self.linkedin_draft_event != event:
            messagebox.showerror(
                "Regenerate the draft",
                "Event details changed after this draft was generated. Generate a fresh draft before publishing.",
            )
            return
        if event.get("chapter_id") == DEMO_CHAPTER_ID:
            messagebox.showerror(
                "Demo content cannot be published",
                "Switch to a live custom event or a real GDG event before publishing.",
            )
            return
        try:
            connection = get_linkedin_connection()
        except (ValueError, keyring.errors.KeyringError) as exc:
            messagebox.showerror("Could not read LinkedIn connection", str(exc))
            return
        if connection is None:
            self.linkedin_account.set("LinkedIn not connected")
            self._connect_linkedin()
            return
        api_version = os.getenv("LINKEDIN_API_VERSION", "202610").strip()
        self._set_busy(True, "Publishing the visible LinkedIn draft…")
        self._start_worker("linkedin_publish", run_linkedin_publish, draft, api_version)

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
        elif action == "linkedin_connect":
            self.linkedin_account.set(f"Connected as {result}")
            self.status.set(
                "LinkedIn connected. Review the draft, then click Publish to LinkedIn."
            )
        elif action == "linkedin_publish":
            self.status.set(f"LinkedIn post published. Post ID: {result}")
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
        if "linkedin" in assets:
            self.linkedin_draft_event = dict(event)
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
        channels = tuple(CHANNEL_LABELS)
        return channels[index] if index < len(channels) else None

    def _tab_changed(self, _event=None) -> None:
        self.regenerate_button.configure(
            state=tk.NORMAL if self._selected_channel() else tk.DISABLED
        )

    def _update_count(self, channel: str) -> None:
        text = self.output_widgets[channel].get("1.0", "end-1c")
        words = len(text.split())
        self.char_counts[channel].set(f"{len(text)} characters · {words} words")
        if channel == "linkedin" and hasattr(self, "publish_linkedin_button"):
            self.publish_linkedin_button.configure(
                state=tk.NORMAL if text.strip() else tk.DISABLED
            )

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

    def _create_campaign_plan(self) -> None:
        try:
            event = self._read_event()
            self.campaign_plan = build_event_campaign(event)
        except ValueError as exc:
            messagebox.showerror("Cannot build campaign timeline", str(exc))
            return

        self.campaign_event = dict(event)
        sections = []
        for item in self.campaign_plan:
            scheduled_at = item["scheduled_at"]
            sections.append(
                "{} · {} · {}\n{}\n".format(
                    item["stage"],
                    scheduled_at.strftime("%a, %b %d, %Y · %I:%M %p %Z"),
                    "event day {:+d}".format(item["offset_days"]),
                    item["copy"],
                )
            )
        self.campaign_text.delete("1.0", tk.END)
        self.campaign_text.insert("1.0", "\n---\n\n".join(sections))
        self.status.set(
            "Event campaign planned locally. Review and edit each post; nothing was published."
        )

    def _export_campaign_calendar(self) -> None:
        if not self.campaign_plan:
            messagebox.showinfo(
                "Campaign timeline required",
                "Build an event timeline before exporting calendar reminders.",
            )
            return
        if self.campaign_event != self._read_event():
            messagebox.showinfo(
                "Campaign plan is out of date",
                "Event details changed. Build a new timeline before exporting reminders.",
            )
            return
        path = filedialog.asksaveasfilename(
            title="Export manual campaign review reminders",
            defaultextension=".ics",
            filetypes=(("Calendar file", "*.ics"),),
            initialfile="gdg-event-campaign-reminders.ics",
        )
        if not path:
            return
        try:
            calendar = build_campaign_ics(self._read_event(), self.campaign_plan)
            with open(path, "w", encoding="utf-8", newline="") as output:
                output.write(calendar)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not export reminders", str(exc))
            return
        self.status.set(
            "Calendar reminders exported. They are reminders only; posts are never auto-published."
        )

    def _create_visual_carousel(self) -> None:
        draft = self.output_widgets["linkedin"].get("1.0", "end-1c").strip()
        if not draft:
            messagebox.showinfo(
                "LinkedIn draft required",
                "Generate a LinkedIn draft first, then turn it into a visual carousel.",
            )
            return
        path = filedialog.asksaveasfilename(
            title="Save event visual carousel",
            defaultextension=".html",
            filetypes=(("HTML visual carousel", "*.html"),),
            initialfile="gdg-event-visual-carousel.html",
        )
        if not path:
            return
        try:
            page = render_carousel_html(self._read_event(), draft)
            output_path = Path(path)
            output_path.write_text(page, encoding="utf-8")
            webbrowser.open(output_path.resolve().as_uri())
        except OSError as exc:
            messagebox.showerror("Could not create visual carousel", str(exc))
            return
        self.status.set(
            "Visual carousel saved and opened locally. Review each card before sharing."
        )

    def _set_busy(self, busy: bool, message: Optional[str] = None) -> None:
        self.busy = busy
        self.generate_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        if hasattr(self, "publish_linkedin_button"):
            draft = self.output_widgets["linkedin"].get("1.0", "end-1c").strip()
            self.publish_linkedin_button.configure(
                state=tk.DISABLED if busy or not draft else tk.NORMAL
            )
        for button_name in ("linkedin_connect_button", "linkedin_disconnect_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.configure(state=tk.DISABLED if busy else tk.NORMAL)
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
            "to a Markdown file. LinkedIn publishing is optional: connect your "
            "account, review the visible draft, then click Publish to LinkedIn. "
            "Demo content cannot be published.",
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
