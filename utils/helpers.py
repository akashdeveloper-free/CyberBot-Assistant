"""Small helpers shared by handlers."""

from __future__ import annotations


def is_positive_integer(value: str) -> bool:
    """Return whether a string represents a positive whole number."""

    try:
        return int(value.strip()) >= 1
    except (TypeError, ValueError):
        return False