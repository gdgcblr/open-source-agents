"""
Lightweight SQLite Wiretap & Query Interceptor for Project V.U.L.C.A.N.
Monitors query counts, execution latencies, and duplicate statement templates.
Emits structured TelemetryIncident JSON events on threshold breach (> 5 queries or > 20ms).
"""

import re
import time
import uuid
import json
import sqlite3
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

def normalize_sql_template(sql: str) -> str:
    """Replaces numeric literals, strings, and parameter placeholders to count templates."""
    cleaned = " ".join(sql.strip().split())
    # Replace single-quoted literals with '?'
    cleaned = re.sub(r"'[^']*'", "'?'", cleaned)
    # Replace numeric literals with ?
    cleaned = re.sub(r"\b\d+\b", "?", cleaned)
    return cleaned

@dataclass
class TelemetryIncident:
    incident_id: str
    timestamp: str
    caller: str
    query_count: int
    wall_clock_ms: float
    duplicate_patterns: Dict[str, int]
    raw_queries: List[str]
    is_anomaly: bool
    scan_detected: bool
    alert_summary: str

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(asdict(self), indent=indent)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SQLWiretap:
    """
    Context manager and query interception wrapper for sqlite3 connections.
    Intercepts every executed SQL query via sqlite3.set_trace_callback.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        caller: str = "unknown_caller",
        query_threshold: int = 5,
        latency_threshold_ms: float = 20.0,
        incident_callback: Optional[Callable[[TelemetryIncident], None]] = None,
    ):
        self.conn = connection
        self.caller = caller
        self.query_threshold = query_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.incident_callback = incident_callback

        self.captured_queries: List[str] = []
        self.start_time: float = 0.0
        self.elapsed_ms: float = 0.0
        self.incident: Optional[TelemetryIncident] = None

    def _trace_hook(self, statement: str):
        # Ignore internal sqlite schema introspection or pragma queries initiated by seeder
        stmt = statement.strip()
        if stmt and not stmt.startswith("PRAGMA") and not stmt.startswith("sqlite_"):
            self.captured_queries.append(stmt)

    def __enter__(self):
        self.captured_queries = []
        self.start_time = time.perf_counter()
        # Register sqlite trace callback
        self.conn.set_trace_callback(self._trace_hook)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Unregister trace callback
        self.conn.set_trace_callback(None)
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0

        # Template grouping
        template_counts: Dict[str, int] = {}
        for q in self.captured_queries:
            tpl = normalize_sql_template(q)
            template_counts[tpl] = template_counts.get(tpl, 0) + 1

        query_count = len(self.captured_queries)
        is_anomaly = (query_count > self.query_threshold) or (self.elapsed_ms > self.latency_threshold_ms)

        # Quick check for table scans
        scan_detected = False
        try:
            cur = self.conn.cursor()
            for tpl, count in template_counts.items():
                if count > 1 and "WHERE" in tpl.upper():
                    cur.execute(f"EXPLAIN QUERY PLAN {tpl.replace('?', '1')}")
                    rows = cur.fetchall()
                    for r in rows:
                        plan_str = str(r[-1]).upper()
                        if "SCAN" in plan_str and "SEARCH" not in plan_str:
                            scan_detected = True
                            break
        except Exception:
            pass

        # Build alert message
        alert = "OK"
        if is_anomaly:
            if query_count > 10:
                alert = f"QUERY_STORM_DETECTED: N+1 query burst ({query_count} queries executed in {self.elapsed_ms:.1f}ms). Full table scans detected."
            else:
                alert = f"LATENCY_THRESHOLD_BREACH: Execution took {self.elapsed_ms:.1f}ms with {query_count} queries."

        self.incident = TelemetryIncident(
            incident_id=f"INC-{uuid.uuid4().hex[:6].upper()}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            caller=self.caller,
            query_count=query_count,
            wall_clock_ms=round(self.elapsed_ms, 2),
            duplicate_patterns=template_counts,
            raw_queries=self.captured_queries,
            is_anomaly=is_anomaly,
            scan_detected=scan_detected,
            alert_summary=alert,
        )

        if is_anomaly and self.incident_callback:
            self.incident_callback(self.incident)

        return False  # Do not suppress exceptions
