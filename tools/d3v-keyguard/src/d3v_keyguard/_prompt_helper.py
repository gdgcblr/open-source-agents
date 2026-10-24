"""Isolated tkinter dialog. Reads a JSON request on stdin, writes a JSON reply on stdout.

Run by file path with `python -I`, so it imports nothing from the caller's environment.
Exit 0 with a JSON reply (a user cancel is {"cancelled": true}); exit 3 if no GUI is available.
The request text is shown in a scrollable, read-only box and is never cut silently.
"""

import json
import sys

MAX_MESSAGE = 20000


def _cap(text, limit):
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... {len(text) - limit} chars hidden - do not approve unless you expected this ...]"


def _message_box(tk, parent, message, width=90):
    """Read-only, scrollable text: long requests stay fully visible."""
    lines = message.count("\n") + 1 + len(message) // width
    frame = tk.Frame(parent)
    frame.pack(fill="both", expand=True, padx=12, pady=8)
    text = tk.Text(frame, wrap="word", width=width, height=max(3, min(lines, 18)), relief="flat")
    bar = tk.Scrollbar(frame, command=text.yview)
    text.configure(yscrollcommand=bar.set)
    text.insert("1.0", message)
    text.configure(state="disabled")
    bar.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)


def _dialog(tk, root, title, message, kind):
    root.deiconify()
    root.title(title)
    _message_box(tk, root, message)
    result = {"cancelled": True}
    entry = None
    if kind == "secret":
        entry = tk.Entry(root, show="*", width=60)
        entry.pack(padx=12, pady=4)
        entry.focus_set()

    def ok(_event=None):
        result.clear()
        if entry is not None:
            value = entry.get()
            result.update({"value": value} if value else {"cancelled": True})
        else:
            result["ok"] = True
        root.destroy()

    def cancel(_event=None):
        result.clear()
        result.update({"cancelled": True} if kind == "secret" else {"ok": False})
        root.destroy()

    buttons = tk.Frame(root)
    buttons.pack(pady=8)
    tk.Button(buttons, text="OK" if kind == "secret" else "Yes", width=10, command=ok).pack(side="left", padx=6)
    tk.Button(buttons, text="Cancel" if kind == "secret" else "No", width=10, command=cancel).pack(side="left", padx=6)
    if entry is not None:
        entry.bind("<Return>", ok)
    root.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()
    return result


def _review(tk, root, title, message, items):
    root.deiconify()
    root.title(title)
    tk.Label(root, text=message, justify="left", wraplength=640).pack(padx=12, pady=8, anchor="w")
    # Buttons are packed first (bottom) so they stay visible; the item rows scroll.
    buttons = tk.Frame(root)
    buttons.pack(side="bottom", pady=8)
    if len(items) > 50:
        tk.Label(root, text=f"{len(items) - 50} more entries stay pending (review them next time).").pack(
            side="bottom")
    area = tk.Frame(root)
    area.pack(fill="both", expand=True, padx=12)
    canvas = tk.Canvas(area, width=660, height=min(420, 90 * max(1, len(items[:50]))), highlightthickness=0)
    bar = tk.Scrollbar(area, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    rows = tk.Frame(canvas)
    canvas.create_window((0, 0), window=rows, anchor="nw")
    rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
    choices = {}
    for item in items[:50]:
        frame = tk.Frame(rows, relief="groove", borderwidth=1)
        frame.pack(fill="x", pady=3)
        tk.Label(frame, text=_cap(item.get("label", ""), 1000), justify="left", wraplength=620).pack(anchor="w")
        var = tk.StringVar(value="later")
        for value, text in (("approve", "Approve"), ("reject", "Reject"), ("later", "Decide later")):
            tk.Radiobutton(frame, text=text, variable=var, value=value).pack(side="left")
        choices[str(item.get("name", ""))] = var
    result = {"cancelled": True}

    def apply():
        result.clear()
        result["decisions"] = {name: var.get() for name, var in choices.items()}
        root.destroy()

    tk.Button(buttons, text="Apply", command=apply).pack(side="left", padx=6)
    tk.Button(buttons, text="Cancel", command=root.destroy).pack(side="left", padx=6)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result


def main() -> int:
    request = json.loads(sys.stdin.read())
    try:
        import tkinter as tk

        root = tk.Tk()
    except Exception:
        return 3
    root.withdraw()
    root.attributes("-topmost", True)
    title = str(request.get("title", "d3v-keyguard"))[:80]
    message = _cap(request.get("message", ""), MAX_MESSAGE)
    kind = request.get("kind")
    if kind == "review":
        reply = _review(tk, root, title, message, list(request.get("items") or []))
    else:
        reply = _dialog(tk, root, title, message, "confirm" if kind == "confirm" else "secret")
    sys.stdout.write(json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
