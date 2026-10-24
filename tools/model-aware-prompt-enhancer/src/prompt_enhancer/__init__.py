"""Model-Aware Prompt Enhancer: diagnose prompts, propose minimal intent-preserving patches, and measure them.

Public API::

    from prompt_enhancer import analyze, enhance, enhance_messages, Options

    report = analyze("Summarize the report.", model="gemini-3-pro")
    result = enhance(prompt, model="claude-sonnet-5", accept=["PE301"], answers={"PE301": "5 bullet points"})
"""

from .analyzer import Options, analyze
from .engine import enhance, enhance_messages
from .schema import AnalysisReport, Diagnostic, EnhancementResult, Patch, Requirement

__version__ = "0.3.0"
__all__ = [
    "analyze", "enhance", "enhance_messages", "Options",
    "AnalysisReport", "Diagnostic", "EnhancementResult", "Patch", "Requirement", "__version__",
]
