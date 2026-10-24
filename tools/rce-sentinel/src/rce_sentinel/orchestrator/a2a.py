"""Agent-to-agent messaging with integrity, role policy, and an audit trail.

Every message between agents (handoff, verify request/result, merge input, intel item) is an
envelope that is:
- signed (HMAC) over sender, recipient, kind, trust, run id, sequence, and payload hash,
  so a tampered or forged message is rejected;
- bound to one run, one sender, and one recipient, so it cannot be replayed or redirected;
- checked against a role policy (who may send which kind to whom);
- chained to the previous message by hash, so the transcript cannot be edited or reordered;
- trust-labelled, with a ceiling per sender role: collectors and models can never claim
  more than their ceiling, and unverified text stays data, never instructions;
- logged to SQLite (hashes only, never payloads) for audit.

Scope, honestly: this is integrity, policy, and audit for in-process agents. The key lives in
the same process, so it does not defend against a compromised process.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time

from pydantic import BaseModel, Field

from rce_sentinel.memory.store import Store
from rce_sentinel.memory.trust import SINGLE, UNVERIFIED, VERIFIED, Signer
from rce_sentinel.orchestrator.prompts import sanitize

MAX_PAYLOAD = 2000

# kind -> (allowed sender roles, allowed recipient roles)
POLICY: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "handoff": (frozenset({"judge"}), frozenset({"judge"})),
    "verify_request": (frozenset({"judge", "planner"}), frozenset({"verifier"})),
    "verify_result": (frozenset({"verifier"}), frozenset({"judge", "planner"})),
    "merge_input": (frozenset({"judge"}), frozenset({"merger"})),
    "intel_item": (frozenset({"collector"}), frozenset({"triage", "planner"})),
    "plan_input": (frozenset({"triage"}), frozenset({"planner"})),
}

# Highest trust each role may attach to what it sends.
CEILING = {"collector": UNVERIFIED, "triage": SINGLE, "judge": SINGLE, "planner": SINGLE,
           "merger": SINGLE, "verifier": VERIFIED}


class A2AError(Exception):
    """A message failed verification or policy."""


class Envelope(BaseModel):
    v: int = 1
    run_id: str
    seq: int
    ts: float
    sender: str
    recipient: str
    kind: str
    trust: int
    payload: str = Field(max_length=MAX_PAYLOAD)
    payload_hash: str
    prev: str
    sig: str


def role_of(agent: str) -> str:
    """'judge:tier2' -> 'judge'."""
    return agent.split(":", 1)[0]


def _fields(e: Envelope) -> tuple[object, ...]:
    return (e.v, e.run_id, e.seq, e.sender, e.recipient, e.kind, e.trust, e.payload_hash,
            e.prev)


class Bus:
    def __init__(self, run_id: str, store: Store | None = None):
        self.run_id = run_id
        self.store = store
        self._signer = Signer(secrets.token_bytes(32))  # per-run, in memory only
        self._lock = threading.Lock()
        self._seq = 0
        self._last = ""
        self._known: set[str] = set()
        self._consumed: set[str] = set()
        self.log: list[Envelope] = []

    def send(self, sender: str, recipient: str, kind: str, payload: str, trust: int) -> Envelope:
        if kind not in POLICY:
            raise A2AError(f"unknown message kind {kind!r}")
        senders, recipients = POLICY[kind]
        if role_of(sender) not in senders or role_of(recipient) not in recipients:
            raise A2AError(f"{sender} may not send {kind} to {recipient}")
        trust = min(trust, CEILING.get(role_of(sender), UNVERIFIED))
        text = sanitize(payload, MAX_PAYLOAD)
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self._lock:
            self._seq += 1
            env = Envelope(run_id=self.run_id, seq=self._seq, ts=time.time(), sender=sender,
                           recipient=recipient, kind=kind, trust=trust, payload=text,
                           payload_hash=digest, prev=self._last, sig="")
            env.sig = self._signer.sign(*_fields(env))
            self._last = env.sig
            self._known.add(env.sig)
            self.log.append(env)
        self._audit(env)
        return env

    def receive(self, env: Envelope, me: str) -> str:
        """Verify an envelope addressed to `me` and return its payload as data."""
        if env.run_id != self.run_id:
            raise A2AError("message belongs to a different run")
        if env.recipient != me:
            raise A2AError(f"message for {env.recipient} delivered to {me}")
        if env.kind not in POLICY:
            raise A2AError(f"unknown message kind {env.kind!r}")
        senders, recipients = POLICY[env.kind]
        if role_of(env.sender) not in senders or role_of(env.recipient) not in recipients:
            raise A2AError(f"policy forbids {env.sender} -> {env.recipient} for {env.kind}")
        if not self._signer.verify(env.sig, *_fields(env)):
            raise A2AError("bad signature: message was altered or forged")
        if hashlib.sha256(env.payload.encode()).hexdigest() != env.payload_hash:
            raise A2AError("payload does not match its signed hash")
        if env.trust > CEILING.get(role_of(env.sender), UNVERIFIED):
            raise A2AError("sender claimed more trust than its role allows")
        with self._lock:
            if env.prev and env.prev not in self._known:
                raise A2AError("broken chain: unknown predecessor")
            if env.sig in self._consumed:
                raise A2AError("replayed message")
            self._consumed.add(env.sig)
        return env.payload

    def relay(self, sender: str, recipient: str, kind: str, payload: str, trust: int) -> str:
        """Send and deliver in one step (agents here run in one process)."""
        return self.receive(self.send(sender, recipient, kind, payload, trust), recipient)

    def verify_chain(self) -> bool:
        """Re-check signatures and hash links over everything sent this run."""
        prev = ""
        for e in self.log:
            if e.prev != prev or not self._signer.verify(e.sig, *_fields(e)):
                return False
            prev = e.sig
        return True

    def _audit(self, e: Envelope) -> None:
        if self.store is None:
            return
        self.store.execute(
            "INSERT INTO a2a_log(run_id, seq, sender, recipient, kind, trust, payload_hash, "
            "prev, sig, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (e.run_id, e.seq, e.sender, e.recipient, e.kind, e.trust, e.payload_hash, e.prev,
             e.sig, e.ts))


def envelope_json(e: Envelope) -> str:
    return json.dumps(e.model_dump(), sort_keys=True)
