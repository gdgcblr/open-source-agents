"""Sample arithmetic library containing deliberate bugs for demonstration."""


def add(a, b):
    """Adds two numbers (currently has an off-by-one bug)."""
    return a + b + 1


def divide(a, b):
    """Divides a by b (currently crashes on 0 instead of raising ValueError)."""
    return a / b
