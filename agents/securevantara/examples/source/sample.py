"""Synthetic review fixture. Never run this function with untrusted input."""


def calculate(expression):
    # Deliberate finding for the local smoke test; not production application code.
    return eval(expression)
