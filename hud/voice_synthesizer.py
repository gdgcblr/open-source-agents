"""
J.A.R.V.I.S.-style Offline Voice Callout Subsystem for Project V.U.L.C.A.N.
Powered by pyttsx3 with non-blocking threaded queue and graceful silent fallback.
"""

import threading
import queue
import time
from typing import Optional

class VoiceSynthesizer:
    """
    Non-blocking, thread-safe speech synthesis engine.
    Queues utterances to prevent UI stutter or blocking main event loop.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._engine_available = False

        if self.enabled:
            self._start_worker()

    def _start_worker(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="VulcanVoiceWorker")
        self._thread.start()

    def _worker_loop(self):
        engine = None
        try:
            import pyttsx3
            engine = pyttsx3.init()
            # Set speech rate and volume
            engine.setProperty("rate", 195)
            engine.setProperty("volume", 0.95)
            
            # Prefer a modern English voice if available
            voices = engine.getProperty("voices")
            if voices:
                for v in voices:
                    if "david" in v.name.lower() or "george" in v.name.lower() or "english" in v.name.lower():
                        engine.setProperty("voice", v.id)
                        break
            self._engine_available = True
        except Exception:
            self._engine_available = False

        while self._running:
            try:
                text = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if text and self.enabled and self._engine_available and engine:
                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception:
                    pass
            self._queue.task_done()

    def speak(self, text: str):
        """Enqueues an utterance to be spoken asynchronously."""
        if not self.enabled:
            return
        # Avoid queue pileup
        if self._queue.qsize() > 3:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
        self._queue.put(text)

    def toggle(self) -> bool:
        """Toggles voice synthesis on or off. Returns new state."""
        self.enabled = not self.enabled
        return self.enabled

    # Pre-defined Tony Stark / J.A.R.V.I.S. Audio Callouts
    def callout_startup(self):
        self.speak("Project Vulcan online. Agent swarm active. Wiretap monitoring pre-production telemetry.")

    def callout_query_storm(self, queries: int = 41):
        self.speak(
            f"Alert! Query storm detected. {queries} queries intercepted. "
            "Full table scans on bids. Projected cloud burn three thousand eight hundred dollars per month."
        )

    def callout_heal_engaged(self):
        self.speak(
            "Autonomous Agent to Agent protocol engaged. "
            "Forensics profiler analyzing execution plan. "
            "FinOps actuary calculating blast radius. Reforger applying covering index and query consolidation."
        )

    def callout_heal_completed(self):
        self.speak(
            "Remediation complete. Forty-one queries reduced to one. "
            "Execution plan upgraded to index search. "
            "Cloud burn normalized to twenty-four dollars per month."
        )

    def callout_reset(self):
        self.speak("State restored to baseline unoptimized repository. Demo ready.")

    def stop(self):
        self._running = False
