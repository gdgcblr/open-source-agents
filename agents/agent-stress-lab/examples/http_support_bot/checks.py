"""State check for the HTTP example: how many tickets did this run open for the persona's email?

The bot is a long-running service shared by all runs, so tickets are counted only inside this
run's time window (first to last trace event). Runs are sequential, so windows never overlap.
"""

import json
import os
import urllib.request

from murphy.checks import CheckResult


def single_ticket(ctx) -> CheckResult:
    base = os.environ.get("SUPPORT_BOT_URL", "http://127.0.0.1:8010")
    since = ctx.trace[0]["ts"] if ctx.trace else 0
    url = f"{base}/admin/tickets?email={ctx.vars['email']}&since={since}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        count = json.load(resp)["count"]
    expected = ctx.vars.get("tickets", 1)
    return CheckResult("one-ticket", count == expected, "dup" if count > expected else "wrong",
                       f"{count} ticket(s) opened for {ctx.vars['email']} (expected {expected})")
