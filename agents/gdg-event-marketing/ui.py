import os
import queue
import argparse
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from dotenv import load_dotenv
from google import genai

from agent import (
    DEFAULT_MODEL,
    GDGEventMarketingAgent,
    build_demo_content,
    build_demo_event,
)


def run_demo_generation() -> tuple[dict, dict]:
    event = build_demo_event()
    return event, build_demo_content(event)


def run_live_generation(chapter_id: str, api_key: str, model_name: str) -> tuple[dict, dict]:
    client = genai.Client(api_key=api_key)
    agent = GDGEventMarketingAgent(chapter_id, client, model_name)
    event = agent.fetch_latest_event()
    if not event:
        return {}, {}
    return event, agent.generate_content(event)


class EventMarketingApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GDG Event Marketing Agent")
        self.root.geometry("900x700")
        self.root.minsize(700, 560)
        self.results: queue.Queue = queue.Queue()
        self.output_widgets: dict[str, ScrolledText] = {}

        load_dotenv(Path(__file__).with_name(".env"))
        self.mode = tk.StringVar(value="demo")
        self.chapter_id = tk.StringVar(value=os.getenv("GDG_CHAPTER_ID", ""))
        self.api_key = tk.StringVar()
        self.status = tk.StringVar(value="Ready - choose a mode and generate drafts.")
        self.event_summary = tk.StringVar(value="No event loaded yet.")

        self._build_layout()
        self.root.after(100, self._process_results)

    def show_demo(self) -> None:
        self.mode.set("demo")
        self._update_mode()
        self._start_generation()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)

        ttk.Label(
            container,
            text="GDG Event Marketing Agent",
            font=("Segoe UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text="Create review-ready LinkedIn, X, and newsletter drafts from an event.",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(2, 14))

        settings = ttk.LabelFrame(container, text="Settings", padding=12)
        settings.grid(row=2, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 12))
        mode_frame = ttk.Frame(settings)
        mode_frame.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Offline demo (no key or network)",
            variable=self.mode,
            value="demo",
            command=self._update_mode,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(
            mode_frame,
            text="Live (Bevy + Gemini)",
            variable=self.mode,
            value="live",
            command=self._update_mode,
        ).pack(side=tk.LEFT)

        ttk.Label(settings, text="GDG chapter ID").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0)
        )
        self.chapter_entry = ttk.Entry(settings, textvariable=self.chapter_id)
        self.chapter_entry.grid(row=1, column=1, sticky="ew", pady=(10, 0))

        ttk.Label(settings, text="Gemini API key").grid(
            row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0)
        )
        self.key_entry = ttk.Entry(settings, textvariable=self.api_key, show="*")
        self.key_entry.grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Label(
            settings,
            text="Optional here if GEMINI_API_KEY is already set in your local .env.",
            foreground="#555555",
        ).grid(row=3, column=1, sticky="w", pady=(3, 0))

        actions = ttk.Frame(container)
        actions.grid(row=3, column=0, sticky="ew", pady=12)
        self.generate_button = ttk.Button(
            actions,
            text="Generate drafts",
            command=self._start_generation,
        )
        self.generate_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="Copy selected draft", command=self._copy_selected).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        result_frame = ttk.LabelFrame(container, text="Generated drafts", padding=10)
        result_frame.grid(row=4, column=0, sticky="nsew")
        result_frame.rowconfigure(1, weight=1)
        result_frame.columnconfigure(0, weight=1)
        ttk.Label(
            result_frame,
            textvariable=self.event_summary,
            wraplength=800,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.tabs = ttk.Notebook(result_frame)
        self.tabs.grid(row=1, column=0, sticky="nsew")
        for key, title in (
            ("linkedin", "LinkedIn"),
            ("twitter", "X"),
            ("email_newsletter", "Newsletter"),
        ):
            panel = ttk.Frame(self.tabs, padding=6)
            panel.rowconfigure(0, weight=1)
            panel.columnconfigure(0, weight=1)
            output = ScrolledText(panel, wrap=tk.WORD, font=("Segoe UI", 10), height=12)
            output.grid(row=0, column=0, sticky="nsew")
            output.configure(state=tk.DISABLED)
            self.output_widgets[key] = output
            self.tabs.add(panel, text=title)

        ttk.Label(
            container,
            textvariable=self.status,
            anchor="w",
            padding=(0, 8, 0, 0),
        ).grid(row=5, column=0, sticky="ew")
        self._update_mode()

    def _update_mode(self) -> None:
        live = self.mode.get() == "live"
        chapter_state = tk.NORMAL if live else tk.DISABLED
        key_state = tk.NORMAL if live else tk.DISABLED
        self.chapter_entry.configure(state=chapter_state)
        self.key_entry.configure(state=key_state)

    def _start_generation(self) -> None:
        if self.mode.get() == "live":
            chapter_id = self.chapter_id.get().strip()
            api_key = self.api_key.get().strip() or os.getenv("GEMINI_API_KEY", "").strip()
            if not chapter_id:
                messagebox.showerror("Chapter ID required", "Enter a GDG Community chapter ID.")
                return
            if not api_key or api_key == "your_gemini_api_key_here":
                messagebox.showerror(
                    "Gemini API key required",
                    "Enter your key above or set GEMINI_API_KEY in your local .env file.",
                )
                return
            model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
            target = run_live_generation
            args = (chapter_id, api_key, model_name)
        else:
            target = run_demo_generation
            args = ()

        self.generate_button.configure(state=tk.DISABLED)
        self.status.set("Working... Live requests can take a little while.")
        threading.Thread(
            target=self._worker,
            args=(target, args),
            daemon=True,
        ).start()

    def _worker(self, target, args: tuple) -> None:
        try:
            self.results.put(("success", target(*args)))
        except Exception as exc:
            self.results.put(("error", str(exc)))

    def _process_results(self) -> None:
        try:
            result_type, result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._process_results)
            return

        self.generate_button.configure(state=tk.NORMAL)
        if result_type == "error":
            self.status.set("The request failed.")
            messagebox.showerror("Could not generate drafts", result)
        else:
            event, assets = result
            if not event:
                self.event_summary.set("No upcoming published event was found for this chapter.")
                self.status.set("Try a chapter with an upcoming published event.")
            else:
                prefix = "Fictional demo event - " if self.mode.get() == "demo" else ""
                self.event_summary.set(
                    f"{prefix}{event.get('title', 'Event')} | "
                    f"{event.get('date_time', '')} | {event.get('location', '')}"
                )
                for key, widget in self.output_widgets.items():
                    widget.configure(state=tk.NORMAL)
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", assets[key])
                    widget.configure(state=tk.DISABLED)
                self.status.set(
                    "Offline sample drafts ready - no API calls made."
                    if self.mode.get() == "demo"
                    else "Drafts ready. Review them before posting; nothing was published."
                )

        self.root.after(100, self._process_results)

    def _copy_selected(self) -> None:
        selected = self.tabs.index(self.tabs.select())
        key = ("linkedin", "twitter", "email_newsletter")[selected]
        text = self.output_widgets[key].get("1.0", "end-1c")
        if not text.strip():
            self.status.set("There is no draft to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Selected draft copied to clipboard.")


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
        root.after(100, app.show_demo)
    root.mainloop()


if __name__ == "__main__":
    main()
