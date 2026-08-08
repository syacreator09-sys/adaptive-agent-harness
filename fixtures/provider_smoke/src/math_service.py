def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    # Intentionally wrong so AAH has a real bounded defect to repair.
    return a - b


def format_currency(value: float) -> str:
    """Return USD with exactly two decimal places."""
    # Intentionally incomplete for smoke testing.
    return f"${value}"
