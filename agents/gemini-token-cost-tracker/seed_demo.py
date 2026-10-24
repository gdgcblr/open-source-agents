"""Fill usage.db with realistic fake history so you can demo without spending quota.
    python seed_demo.py
"""
import hashlib
import random
import time

from cost_tracker import store
from cost_tracker.pricing import calculate_cost

random.seed(7)
now = time.time()
big_prompt = hashlib.sha256(b"support-bot-system-prompt").hexdigest()[:16]

for i in range(40):
    day_offset = random.uniform(0, 6) * 86400
    model = random.choice(["gemini-3.1-pro", "gemini-2.5-pro", "gemini-2.5-flash"])
    p, o = random.randint(300, 4000), random.randint(100, 1800)
    t = random.randint(0, 3000) if "pro" in model else 0
    c = calculate_cost(model, p, o, t)
    store.record("demo", c["model"], p, o, t, 0, c["cost_usd"], ts=now - day_offset)

for i in range(8):  # same big prompt again and again
    c = calculate_cost("gemini-2.5-pro", 12000, 400)
    store.record("demo", c["model"], 12000, 400, 0, 0, c["cost_usd"],
                 prompt_hash=big_prompt, ts=now - i * 3600)
print("Seeded demo data into", store._path(None))
