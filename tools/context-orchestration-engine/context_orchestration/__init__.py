"""Context Orchestration Engine.

Independent LLM workers finish one long task in sequence with no raw
conversation passed between them. Context is engine-owned execution state:
the reconciler is its only writer, the compiler turns it into a bounded
briefing for each worker, and SQLite keeps it across crashes.
"""

from context_orchestration.compiler import ContextCompiler, HeuristicTokenEstimator
from context_orchestration.contracts import ContextPackage, ExecutionState, WorkerClaims, WorkerConfig
from context_orchestration.gateway import HTTPGateway, LiteLLMGateway, MockGateway, build_gateway
from context_orchestration.orchestrator import Orchestrator, RunSummary, load_workers
from context_orchestration.reconciler import StateReconciler
from context_orchestration.store import SQLiteStore
from context_orchestration.worker import UniversalWorker

__all__ = [
    "ContextCompiler",
    "ContextPackage",
    "ExecutionState",
    "HTTPGateway",
    "HeuristicTokenEstimator",
    "LiteLLMGateway",
    "MockGateway",
    "Orchestrator",
    "RunSummary",
    "SQLiteStore",
    "StateReconciler",
    "UniversalWorker",
    "WorkerClaims",
    "WorkerConfig",
    "build_gateway",
    "load_workers",
]

__version__ = "0.1.0"
