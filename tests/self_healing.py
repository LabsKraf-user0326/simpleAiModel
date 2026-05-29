"""Self-healing field resolver.

When an API response changes its field names (e.g. `priority` → `level`),
tests usually break with a KeyError. This helper looks for the canonical
field first, then walks a list of known aliases. If it finds a match
under an alias it logs a warning and continues; if nothing matches it
raises a clear error so the test fails properly instead of silently.

Typical aliases for this project:
    priority   → level, urgency, rank, severity, importance
    confidence → score, probability, certainty, prob
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

log = logging.getLogger("self_healing")

# Common alias families. Edit here when the API gains a new synonym.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "priority":   ("level", "urgency", "rank", "severity", "importance"),
    "confidence": ("score", "probability", "certainty", "prob"),
}


class FieldNotFound(KeyError):
    """Raised when neither the canonical field nor any alias is present."""


def resolve_field(
    payload: Mapping[str, Any],
    canonical: str,
    aliases: Iterable[str] | None = None,
) -> tuple[str, Any]:
    """Return (key_used, value) for `canonical` in `payload`.

    Lookup order:
      1. The canonical name itself.
      2. Each alias in order. If `aliases` is None, falls back to
         `FIELD_ALIASES.get(canonical, ())`.

    On alias hit, logs a WARNING with both names so the drift is visible
    in test output. On total miss, raises FieldNotFound with the list of
    names that were tried and the keys that were actually present.
    """
    if canonical in payload:
        return canonical, payload[canonical]

    candidates = tuple(aliases) if aliases is not None else FIELD_ALIASES.get(canonical, ())
    for alt in candidates:
        if alt in payload:
            log.warning(
                "self-healing: field %r missing; using alias %r instead. "
                "Update the test (or the API) to make this explicit.",
                canonical, alt,
            )
            return alt, payload[alt]

    tried = (canonical, *candidates)
    raise FieldNotFound(
        f"None of the expected fields were present. Tried {list(tried)}; "
        f"response had keys {sorted(payload.keys())}."
    )


def resolve_value(payload: Mapping[str, Any], canonical: str, aliases: Iterable[str] | None = None) -> Any:
    """Convenience wrapper that returns just the value."""
    _, value = resolve_field(payload, canonical, aliases)
    return value
