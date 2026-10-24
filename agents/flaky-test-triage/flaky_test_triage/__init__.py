try:
    from . import agent  # noqa: F401  (ADK discovers root_agent through this import)
except ImportError:  # lets the pure-Python tools be tested without google-adk
    pass
