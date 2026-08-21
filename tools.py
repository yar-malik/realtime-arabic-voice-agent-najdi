"""Tools the agent can call mid-sentence.

Retrieval answers "what is the policy". It cannot answer "how long do *I*
have left" — that needs the caller's actual invoice. So the model is given a
small set of functions, each one a lookup against a real system, and it calls
them while it is still speaking.

Keep the set small and the descriptions blunt. A tool the model half
understands is worse than one it does not have, because it will call it
confidently on the wrong turn.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable

# Stand-in for your order system. Replace `_PURCHASES` with a real query.
_PURCHASES = {
    "INV-77120": {"part": "EL-441027", "bought": "2026-08-02", "channel": "branch", "opened": True},
    "INV-77121": {"part": "ME-118304", "bought": "2026-07-11", "channel": "online", "opened": False},
}

_BRANCH_HOURS = {
    "riyadh": {"sat_thu": "09:00–21:00", "fri": "16:00–22:00"},
    "jeddah": {"sat_thu": "09:00–22:00", "fri": "16:00–22:00"},
    "dammam": {"sat_thu": "09:00–21:00", "fri": "16:00–22:00"},
}


def lookup_purchase(invoice: str) -> dict[str, Any]:
    """How long is left on a specific purchase's return window."""
    record = _PURCHASES.get(invoice.upper())
    if not record:
        return {"found": False, "invoice": invoice}

    bought = datetime.fromisoformat(record["bought"]).date()
    # Opened electrical parts get fourteen days, everything else thirty.
    window = 14 if record["opened"] and record["part"].startswith("EL") else 30
    ends = bought + timedelta(days=window)
    return {
        "found": True,
        "invoice": invoice.upper(),
        "part": record["part"],
        "bought": bought.isoformat(),
        "window_days": window,
        "window_ends": ends.isoformat(),
        "days_left": max(0, (ends - date.today()).days),
    }


def branch_hours(city: str) -> dict[str, Any]:
    """Opening hours for a branch."""
    hours = _BRANCH_HOURS.get(city.strip().lower())
    return {"found": bool(hours), "city": city, **(hours or {})}


REGISTRY: dict[str, Callable[..., dict]] = {
    "lookup_purchase": lookup_purchase,
    "branch_hours": branch_hours,
}

# The same set, in the shape a model expects to be handed.
SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "lookup_purchase",
            "description": (
                "Look up one purchase by its invoice number and return how many "
                "days are left to return it. Use when the caller asks about "
                "their own purchase rather than the policy in general."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice": {"type": "string", "description": "Invoice number, e.g. INV-77120"}
                },
                "required": ["invoice"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "branch_hours",
            "description": "Opening hours for one branch. Cities: riyadh, jeddah, dammam.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
]


def call(name: str, arguments: str | dict) -> dict:
    """Dispatch one tool call. Bad arguments come back as data, not exceptions.

    A tool that raises mid-call takes the whole conversation down. A tool that
    returns `{"error": ...}` lets the model say something sensible instead.
    """
    fn = REGISTRY.get(name)
    if fn is None:
        return {"error": f"no tool named {name}"}
    try:
        kwargs = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        return fn(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
