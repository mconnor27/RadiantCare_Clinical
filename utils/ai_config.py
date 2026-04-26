"""Centralized config for Claude model + extended-thinking selection.

All AI inference modules (diagnosis, institution, payor) read their model
and thinking budget from here so the user can pick once and have every
AI feature use the same setting. Persisted via ``data.reviews_db.app_settings``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Available models — keep this list sorted from smartest → fastest.
# Update model IDs here when Anthropic ships new versions.
# ---------------------------------------------------------------------------

MODELS = [
    {"id": "claude-opus-4-7",            "label": "Opus 4.7",   "tier": "smartest"},
    {"id": "claude-sonnet-4-6",          "label": "Sonnet 4.6", "tier": "balanced"},
    {"id": "claude-haiku-4-5-20251001",  "label": "Haiku 4.5",  "tier": "fastest"},
]

DEFAULT_MODEL = "claude-sonnet-4-6"

# Extended-thinking budgets. Off uses no thinking parameter at all.
THINKING_LEVELS = [
    {"value": "off",    "label": "Off",     "budget": 0},
    {"value": "low",    "label": "Low",     "budget": 1024},
    {"value": "medium", "label": "Medium",  "budget": 4096},
    {"value": "high",   "label": "High",    "budget": 16384},
]

DEFAULT_THINKING = "off"

_KEY_MODEL = "ai_model"
_KEY_THINKING = "ai_thinking_level"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _valid_model(name: str) -> str:
    ids = {m["id"] for m in MODELS}
    return name if name in ids else DEFAULT_MODEL


def _valid_thinking(level: str) -> str:
    levels = {t["value"] for t in THINKING_LEVELS}
    return level if level in levels else DEFAULT_THINKING


def get_model() -> str:
    """Return the currently selected model ID, validated against MODELS."""
    from data.reviews_db import get_app_setting
    return _valid_model(get_app_setting(_KEY_MODEL, DEFAULT_MODEL))


def get_thinking_level() -> str:
    """Return the currently selected thinking level (off/low/medium/high)."""
    from data.reviews_db import get_app_setting
    return _valid_thinking(get_app_setting(_KEY_THINKING, DEFAULT_THINKING))


def get_thinking_param() -> dict | None:
    """Return the kwarg dict to pass as ``thinking=`` to Anthropic SDK,
    or None when extended thinking is disabled.
    """
    level = get_thinking_level()
    budget = next((t["budget"] for t in THINKING_LEVELS if t["value"] == level), 0)
    if budget <= 0:
        return None
    return {"type": "enabled", "budget_tokens": budget}


def set_model(model_id: str) -> None:
    from data.reviews_db import set_app_setting
    set_app_setting(_KEY_MODEL, _valid_model(model_id))


def set_thinking_level(level: str) -> None:
    from data.reviews_db import set_app_setting
    set_app_setting(_KEY_THINKING, _valid_thinking(level))


def model_options() -> list[dict]:
    """Return [{value, label}] suitable for a Mantine Select."""
    return [{"value": m["id"], "label": f"{m['label']}  ({m['tier']})"} for m in MODELS]


def thinking_options() -> list[dict]:
    return [{"value": t["value"], "label": t["label"]} for t in THINKING_LEVELS]


def build_message_kwargs(max_tokens: int, **extra) -> dict:
    """Convenience: returns a kwargs dict ready to splat into
    ``client.messages.create(...)`` — model, max_tokens, and thinking
    pre-populated from the current settings. Caller adds system, messages,
    tools, etc.
    """
    kwargs = {"model": get_model(), "max_tokens": max_tokens, **extra}
    thinking = get_thinking_param()
    if thinking is not None:
        kwargs["thinking"] = thinking
    return kwargs
