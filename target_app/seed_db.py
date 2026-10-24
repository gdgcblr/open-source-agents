"""
High-Speed Database Seeder for Project V.U.L.C.A.N.
Seeds 2,000 Auctions and 50,000 Bids in SQLite (< 0.5s)
Intentionally leaves bids(auction_id) unindexed for pre-prod query storm detection.
"""

import os
import sys
import time
import random
import sqlite3
from pathlib import Path

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH

def seed_database(db_path: Path = DB_PATH, force: bool = False) -> float:
    """
    Seeds the SQLite database with 2,000 auctions and 50,000 bids.
    Returns the elapsed execution time in seconds.
    """
    db_file = Path(db_path)
    if db_file.exists() and not force:
        # Check if already seeded
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM auctions")
            auc_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM bids")
            bid_count = cursor.fetchone()[0]
            conn.close()
            if auc_count >= 2000 and bid_count >= 50000:
                print(f"[VULCAN SEEDER] Database already populated ({auc_count} auctions, {bid_count} bids).")
                return 0.0
        except Exception:
            pass

    start_time = time.perf_counter()

    # If force or corrupted, delete existing
    if db_file.exists():
        try:
            db_file.unlink()
        except Exception:
            pass

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    # Turbo-charge SQLite for ultra-fast bulk seeding under 1s
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")
    cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache

    # Schema definition
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auctions (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        reserve_price REAL NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bids (
        id INTEGER PRIMARY KEY,
        auction_id INTEGER NOT NULL,
        bidder_name TEXT NOT NULL,
        amount REAL NOT NULL,
        bid_time TEXT NOT NULL
    )
    """)

    # Note: We INTENTIONALLY do NOT create an index on bids(auction_id)!
    # This allows EXPLAIN QUERY PLAN to genuinely demonstrate SCAN TABLE bids.

    # 1. Generate 2,000 Auctions (First 40 are ACTIVE, rest are CLOSED)
    auction_rows = []
    item_categories = [
        "Vintage Stark Industries Arc Reactor Replica",
        "Mark XLII Titanium Plating Fragment",
        "Vibranium-Alloy Vibrational Sensor",
        "Autonomous FinOps Optimization Core",
        "Sub-orbital Telemetry Transceiver",
        "Quantum Relational Cache Module",
        "DeepMind Tensor Co-processor",
        "J.A.R.V.I.S. Audio Waveform Filter"
    ]

    for i in range(1, 2001):
        status = "ACTIVE" if i <= 40 else "CLOSED"
        title = f"{random.choice(item_categories)} #{i}"
        reserve_price = round(random.uniform(150.0, 15000.0), 2)
        created_at = "2026-10-24 08:00:00"
        auction_rows.append((i, title, status, reserve_price, created_at))

    cursor.executemany(
        "INSERT INTO auctions (id, title, status, reserve_price, created_at) VALUES (?, ?, ?, ?, ?)",
        auction_rows
    )

    # 2. Generate 50,000 Bids distributed across all auctions
    bid_rows = []
    bidder_handles = [f"pilot_{n}" for n in range(1, 301)] + [f"stark_sec_{n}" for n in range(1, 101)]

    for bid_id in range(1, 50001):
        # Heavy clustering on active auctions 1..40 to make the scan realistic
        if random.random() < 0.25:
            auction_id = random.randint(1, 40)
        else:
            auction_id = random.randint(1, 2000)

        bidder = random.choice(bidder_handles)
        amount = round(random.uniform(50.0, 25000.0), 2)
        bid_time = "2026-10-24 09:30:00"
        bid_rows.append((bid_id, auction_id, bidder, amount, bid_time))

    cursor.executemany(
        "INSERT INTO bids (id, auction_id, bidder_name, amount, bid_time) VALUES (?, ?, ?, ?, ?)",
        bid_rows
    )

    conn.commit()
    conn.close()

    elapsed = time.perf_counter() - start_time
    print(f"[VULCAN SEEDER] Database successfully seeded in {elapsed:.3f}s: 2,000 auctions, 50,000 bids.")
    return elapsed

if __name__ == "__main__":
    seed_database(force=True)
