"""d3v-keyguard command line."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading

from .errors import KeyguardError, PromptCancelled, PromptUnavailable
from .policy import Policy
from .prompt import _tty, default_prompt, describe_argv, review_pending, sanitize
from .redact import HANDLE_RE, Redactor, handle
from .vault import PASSPHRASE_RULE, Vault, check_passphrase


def _prompt():
    """KEYGUARD_PROMPT decides, even in a terminal: auto = GUI dialog (terminal only if no GUI), gui, tty.

    Agent harnesses may run commands in a pseudo-terminal whose output the model reads, so
    having a TTY is not proof that a human is watching; the GUI dialog is out of band.
    """
    return default_prompt()


def _interactive() -> bool:
    """stdin, stdout and stderr are terminals (a pipe-based agent harness is refused)."""
    try:
        return _tty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _ask(title: str, message: str) -> str:
    return _prompt().ask_secret(title, message)


def _unlock(vault: Vault, purpose: str, *, human_reset: bool = False) -> None:
    """Ask for the passphrase, telling the user exactly what it will be used for, then review pending entries."""
    msg = f"{purpose}\n\nEnter your vault passphrase only if you started this:"
    vault.unlock(_ask("d3v-keyguard: unlock vault", msg), human_reset=human_reset)
    result = review_pending(vault, _prompt())
    if result["approved"] or result["rejected"]:
        print(f"approved {len(result['approved'])}, rejected {len(result['rejected'])}, "
              f"still pending {len(result['pending'])}", file=sys.stderr)


def cmd_init(vault: Vault, a) -> int:
    if vault.exists():
        print(f"error: vault already exists at {vault.path}", file=sys.stderr)
        return 1
    if "onedrive" in str(vault.path).lower():
        print("warning: the vault is inside a OneDrive folder; old synced copies stay decryptable with the "
              "passphrase they had. Consider KEYGUARD_VAULT_PATH outside synced folders.", file=sys.stderr)
    pin = _ask("d3v-keyguard init", f"Choose a vault passphrase ({PASSPHRASE_RULE}):")
    check_passphrase(pin)
    if pin != _ask("d3v-keyguard init", "Repeat the passphrase:"):
        print("passphrases do not match", file=sys.stderr)
        return 1
    vault.create(pin)
    print(f"vault created at {vault.path}")
    print("note: the vault needs its OS-keyring entry; losing the keyring entry means losing the vault.")
    return 0


def cmd_add(vault: Vault, a) -> int:
    existing = {i["name"]: i for i in vault.list()}
    if existing.get(a.name, {}).get("status", "pending") != "pending" and not a.force:
        print(f"error: {handle(a.name)} already exists; use --force to replace it", file=sys.stderr)
        return 1
    value = _ask("d3v-keyguard add", f"Value for '{a.name}' (input hidden):")
    if not a.no_unlock:
        _unlock(vault, f"Store secret '{a.name}'" + (" (REPLACES the existing value)" if a.name in existing else ""))
    meta = {"description": a.description} if a.description else None
    state = vault.put(a.name, value, meta, overwrite=a.force)
    print(f"stored {handle(a.name)} ({state})")
    return 0


def cmd_list(vault: Vault, a) -> int:
    for item in vault.list():
        desc = item["metadata"].get("description", "")
        extra = " (+pending update)" if item.get("pending_update") else ""
        print(f"{handle(item['name'])}\t{item['status']}{extra}\t{desc}")
    return 0


def cmd_rm(vault: Vault, a) -> int:
    status = {i["name"]: i["status"] for i in vault.list()}.get(a.name)
    if status is not None and status != "pending":  # pending-only entries can be dropped without it
        _unlock(vault, f"PERMANENTLY delete secret '{sanitize(a.name, 128)}' (this cannot be undone)")
    ok = vault.delete(a.name)
    print("deleted" if ok else "not found")
    return 0 if ok else 1


def cmd_status(vault: Vault, a) -> int:
    print(json.dumps(vault.status(), indent=2))
    return 0


def cmd_lock(vault: Vault, a) -> int:
    vault.lock()
    print("each CLI invocation is its own process; nothing stays unlocked after it exits")
    return 0


def cmd_approve(vault: Vault, a) -> int:
    if not vault.pending():
        print("no pending secrets")
        return 0
    _unlock(vault, "Review entries stored while the vault was locked")
    print(f"still pending: {len(vault.pending())}")
    return 0


def cmd_reject(vault: Vault, a) -> int:
    done = vault.reject(a.names)
    print(f"rejected {len(done)}: {', '.join(done) or '-'}")
    return 0 if done else 1


def cmd_change_pin(vault: Vault, a) -> int:
    old = _ask("d3v-keyguard", "Current passphrase:")
    new = _ask("d3v-keyguard", f"New passphrase ({PASSPHRASE_RULE}):")
    check_passphrase(new)
    if new != _ask("d3v-keyguard", "Repeat new passphrase:"):
        print("passphrases do not match", file=sys.stderr)
        return 1
    vault.change_pin(old, new)
    print("passphrase changed; vault keys and OS-keyring pepper rotated (old file copies no longer verify)")
    return 0


def cmd_reset_lockout(vault: Vault, a) -> int:
    if not _interactive():
        print("reset-lockout must be run by a human in an interactive terminal", file=sys.stderr)
        return 2
    vault.unlock(_ask("d3v-keyguard: reset lockout",
                      "Clear the wrong-passphrase lockout of the vault. Do this only if YOU typed "
                      "'d3v-keyguard reset-lockout' yourself.\n\nEnter vault passphrase:"), human_reset=True)
    print("lockout cleared")
    return 0


def cmd_reveal(vault: Vault, a) -> int:
    if not _interactive():
        print("reveal only works in an interactive terminal (refused for piped/agent use)", file=sys.stderr)
        return 2
    name = sanitize(a.name, 128)
    warning = (f"This will PRINT the plaintext of secret '{name}' to this terminal. Agents that run commands in "
               f"a terminal can read it. Continue only if YOU typed 'd3v-keyguard reveal {name}' yourself.")
    typed = _ask("d3v-keyguard: reveal a secret", f"{warning}\n\nType the secret name ({name}) to confirm:")
    if typed.strip() != a.name:
        print("cancelled: the secret name did not match", file=sys.stderr)
        return 130
    vault.unlock(_ask("d3v-keyguard: unlock vault", f"{warning}\n\nEnter vault passphrase:"))
    print(vault.get(a.name).reveal())
    return 0


def _pump(src, dst, redactor: Redactor) -> None:
    """Copy child output line by line (bytes), redacting known values. Never dies: keeps draining."""
    for line in iter(src.readline, b""):
        try:
            text = line.decode("utf-8", "replace")
            clean = redactor.scrub_text(text)
            data = line if clean == text else clean.encode("utf-8", "replace")
            buf = getattr(dst, "buffer", None)
            if buf is not None:
                dst.flush()
                buf.write(data)
                buf.flush()
            else:
                dst.write(data.decode("utf-8", "replace"))
                dst.flush()
        except Exception:
            pass  # e.g. closed/unencodable stdout: discard this line but keep the pipe drained
    src.close()


def resolve_program(name: str) -> str | None:
    """Find the program to run, never from the current directory unless the user gave a path.

    On Windows, shutil.which() (like cmd.exe and PowerShell) searches the current directory
    first, so a planted `gh.cmd` in a cloned repo would receive the secret. Bare names are
    therefore only looked up in absolute PATH entries other than the current directory.
    PATHEXT is honoured, so `.cmd`/`.bat` shims (npm, az, gcloud) still resolve.
    """
    seps = {os.sep, os.altsep or os.sep, "/"}
    if any(s in name for s in seps):  # explicit path, e.g. ./build.cmd or C:\tools\x.exe
        exe = shutil.which(name)
        return os.path.abspath(exe) if exe else None
    cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if not d or not os.path.isabs(d) or os.path.normcase(os.path.abspath(d)) == cwd:
            continue
        exe = shutil.which(os.path.join(d, name))  # a directory part: which() checks only there
        if exe:
            return os.path.abspath(exe)
    return None


def cmd_exec(vault: Vault, a) -> int:
    cmd = list(a.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("usage: d3v-keyguard exec --env VAR=keyguard://name -- command [args]", file=sys.stderr)
        return 2
    mapping = {}
    for spec in a.env or []:
        var, _, ref = spec.partition("=")
        m = HANDLE_RE.fullmatch(ref)
        if not var or not m:
            print(f"bad --env {var!r}: expected VAR=keyguard://name", file=sys.stderr)
            return 2
        mapping[var] = m.group(1)
    exe = resolve_program(cmd[0])
    if exe is None:
        print(f"error: command not found: {cmd[0]} (exec runs programs from PATH, never from the current "
              f"directory unless you give a path such as .{os.sep}{cmd[0]}; shell builtins need 'cmd /c' "
              f"or 'sh -c')", file=sys.stderr)
        return 127
    policy = Policy.from_env()
    via_path = not any(s in cmd[0] for s in {os.sep, os.altsep or os.sep, "/"})
    denied = sorted({n for n in mapping.values() if not policy.allows_exec(exe, n, from_path=via_path)})
    if denied:
        print(f"error: policy denies exec of '{os.path.basename(exe)}' access to: {', '.join(denied)}",
              file=sys.stderr)
        return 1
    env = dict(os.environ)
    redactor = Redactor()
    if mapping:
        _unlock(vault, "\n".join(["d3v-keyguard exec wants to run:", *describe_argv(exe, cmd[1:]),
                                  "with secrets:", *(f"  {sanitize(var, 80)} = {handle(name)}"
                                                     for var, name in mapping.items())]))
        for var, name in mapping.items():
            value = vault.get(name).reveal()
            env[var] = value
            redactor.add(name, value)
        vault.lock()
    try:
        proc = subprocess.Popen([exe, *cmd[1:]], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print(f"error: command not found: {cmd[0]}", file=sys.stderr)
        return 127
    except OSError as exc:
        print(f"error: cannot run {cmd[0]}: {exc.strerror or exc}", file=sys.stderr)
        return 126
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, sys.stdout, redactor), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, sys.stderr, redactor), daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        code = 130
    for t in threads:
        t.join(timeout=5)
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="d3v-keyguard", description="Passphrase-protected secret vault for LLM agents")
    p.add_argument("--vault", help="vault file path (default: KEYGUARD_VAULT_PATH or per-user data dir)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create a new vault").set_defaults(fn=cmd_init)
    s = sub.add_parser("add", help="store a secret (value read via hidden prompt, then unlock to store it active)")
    s.add_argument("name")
    s.add_argument("--description", default="")
    s.add_argument("--force", action="store_true", help="replace an existing secret")
    s.add_argument("--no-unlock", action="store_true", help="store without the passphrase (entry stays pending)")
    s.set_defaults(fn=cmd_add)
    sub.add_parser("list", help="list secret handles and status").set_defaults(fn=cmd_list)
    s = sub.add_parser("rm", help="delete a secret")
    s.add_argument("name")
    s.set_defaults(fn=cmd_rm)
    sub.add_parser("status", help="show vault status").set_defaults(fn=cmd_status)
    sub.add_parser("lock", help="lock (informational for CLI)").set_defaults(fn=cmd_lock)
    sub.add_parser("approve", help="review pending secrets one by one (approve/reject/later)").set_defaults(
        fn=cmd_approve)
    s = sub.add_parser("reject", help="discard pending secrets (active values with the same name are kept)")
    s.add_argument("names", nargs="+")
    s.set_defaults(fn=cmd_reject)
    sub.add_parser("change-pin", help="change the passphrase and rotate vault keys").set_defaults(fn=cmd_change_pin)
    sub.add_parser("reset-lockout", help="clear wrong-passphrase lockout (interactive terminal only)").set_defaults(
        fn=cmd_reset_lockout
    )
    s = sub.add_parser("reveal", help="print a secret (interactive terminal only)")
    s.add_argument("name")
    s.set_defaults(fn=cmd_reveal)
    s = sub.add_parser("exec", help="run a command with secrets injected as env vars; output is redacted")
    s.add_argument("--env", action="append", metavar="VAR=keyguard://name")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_exec)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    vault = Vault(a.vault) if a.vault else Vault()
    try:
        return a.fn(vault, a)
    except PromptUnavailable as exc:
        print(f"error: {exc} (run in an interactive terminal, or with a display for the GUI dialog; "
              f"see KEYGUARD_PROMPT)", file=sys.stderr)
        return 2
    except (PromptCancelled, KeyboardInterrupt) as exc:
        print(f"cancelled: {exc or 'interrupted'}", file=sys.stderr)
        return 130
    except (KeyguardError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        vault.lock()


if __name__ == "__main__":
    sys.exit(main())
