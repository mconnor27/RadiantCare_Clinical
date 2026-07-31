"""Centralized config for Claude model + extended-thinking selection.

All AI inference modules (diagnosis, institution, payor) read their model
and thinking budget from here so the user can pick once and have every
AI feature use the same setting. Persisted via ``data.reviews_db.app_settings``.

The model list is **discovered live** from Anthropic's Models API
(``client.models.list()``) and cached, so new releases (e.g. a future Opus 4.9)
appear in the picker automatically with no code change. If the API is
unreachable — no key, offline, cloud host without egress — we fall back to the
hardcoded ``_FALLBACK_MODELS`` list below.
"""

from __future__ import annotations

import threading
import time

# ---------------------------------------------------------------------------
# Fallback model list — used only when the Models API can't be reached.
# Keep sorted smartest → fastest. Each record carries its own reasoning
# capabilities so thinking still works offline.
# ---------------------------------------------------------------------------

_FALLBACK_MODELS = [
    {"id": "claude-opus-4-8",   "label": "Opus 4.8",   "tier": "smartest",
     "adaptive": True,  "effort": True,  "enabled": False},
    {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6", "tier": "balanced",
     "adaptive": True,  "effort": True,  "enabled": False},
    {"id": "claude-haiku-4-5",  "label": "Haiku 4.5",  "tier": "fastest",
     "adaptive": False, "effort": False, "enabled": True},
]

DEFAULT_MODEL = "claude-sonnet-4-6"

# How long a successful Models API result is trusted before re-fetching.
_CACHE_TTL_SECONDS = 12 * 60 * 60

# Which families we surface, and how they map to a user-facing "tier".
_FAMILY_TIER = {"opus": "smartest", "fable": "smartest", "mythos": "smartest",
                "sonnet": "balanced", "haiku": "fastest"}
_TIER_ORDER = {"smartest": 0, "balanced": 1, "fastest": 2}

# Extended-thinking levels. "off" sends no thinking parameter at all; the
# rest map to an ``effort`` level for adaptive-thinking models, or to a token
# budget for older models that still take ``budget_tokens``.
THINKING_LEVELS = [
    {"value": "off",    "label": "Off",    "effort": None,     "budget": 0},
    {"value": "low",    "label": "Low",    "effort": "low",    "budget": 1024},
    {"value": "medium", "label": "Medium", "effort": "medium", "budget": 4096},
    {"value": "high",   "label": "High",   "effort": "high",   "budget": 16384},
]

DEFAULT_THINKING = "off"

_KEY_MODEL = "ai_model"
_KEY_THINKING = "ai_thinking_level"


# ---------------------------------------------------------------------------
# Live model discovery (cached)
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict = {"models": None, "ts": 0.0}


def _cap_get(node, key):
    """Read ``key`` from a capabilities node that may be a Pydantic model
    (``ModelCapabilities``/``CapabilitySupport``) or a plain dict."""
    if node is None:
        return None
    if isinstance(node, dict):
        return node.get(key)
    return getattr(node, key, None)


def _caps_supported(caps, *path) -> bool:
    """Safely walk the nested capabilities tree (Pydantic model or dict),
    returning the ``supported`` leaf as a bool. Missing keys → False."""
    node = caps
    for key in path:
        node = _cap_get(node, key)
        if node is None:
            return False
    sup = _cap_get(node, "supported")
    return bool(node if sup is None else sup)


def _family(model_id: str) -> str | None:
    for fam in _FAMILY_TIER:
        if fam in model_id:
            return fam
    return None


def _label_from(model_id: str, display_name: str | None) -> str:
    if display_name:
        # "Claude Opus 4.8" → "Opus 4.8"
        return display_name.replace("Claude", "").strip()
    return model_id


def _fetch_models() -> list[dict] | None:
    """Query the Models API and shape the result into our model records.
    Returns None on any failure so the caller can fall back."""
    from config.settings import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        records: list[dict] = []
        for m in client.models.list():
            model_id = getattr(m, "id", "")
            fam = _family(model_id)
            if fam is None:
                continue  # skip anything that isn't a chat model family
            caps = getattr(m, "capabilities", None) or {}
            adaptive = _caps_supported(caps, "thinking", "types", "adaptive")
            enabled = _caps_supported(caps, "thinking", "types", "enabled")
            effort = _caps_supported(caps, "effort", "high")
            # If capabilities are absent (older SDK / model), fall back to a
            # conservative default: assume adaptive for opus/sonnet/fable,
            # budget-token thinking for haiku. Never assume effort.
            if not caps:
                adaptive = fam != "haiku"
                enabled = not adaptive
                effort = False
            created = getattr(m, "created_at", None)
            created = (created.isoformat() if hasattr(created, "isoformat")
                       else (str(created) if created else ""))
            records.append({
                "id": model_id,
                "label": _label_from(model_id, getattr(m, "display_name", None)),
                "tier": _FAMILY_TIER[fam],
                "created": created,
                "adaptive": adaptive,
                "effort": effort,
                "enabled": enabled,
            })
        if not records:
            return None
        # newest first, then a stable sort into smartest → balanced → fastest
        # tiers (so within each tier the newest model leads).
        records.sort(key=lambda r: r["created"], reverse=True)
        records.sort(key=lambda r: _TIER_ORDER.get(r["tier"], 9))
        return records
    except Exception:
        return None


def get_available_models(force: bool = False) -> list[dict]:
    """Return the list of model records to offer in the picker.

    Cached for ``_CACHE_TTL_SECONDS``; refreshes from the Models API in the
    background of a normal request. Falls back to ``_FALLBACK_MODELS`` when the
    API is unreachable so the app always has a usable list.
    """
    now = time.time()
    with _cache_lock:
        fresh = (
            _cache["models"] is not None
            and (now - _cache["ts"]) < _CACHE_TTL_SECONDS
        )
        if fresh and not force:
            return _cache["models"]

    fetched = _fetch_models()
    with _cache_lock:
        if fetched:
            _cache["models"] = fetched
            _cache["ts"] = now
            return fetched
        # keep a stale-but-usable cache if we have one, else the fallback
        if _cache["models"] is not None:
            return _cache["models"]
        return _FALLBACK_MODELS


def _model_record(model_id: str) -> dict:
    for rec in get_available_models():
        if rec["id"] == model_id:
            return rec
    for rec in _FALLBACK_MODELS:
        if rec["id"] == model_id:
            return rec
    # Unknown model: safest reasoning defaults (adaptive on, no effort).
    return {"id": model_id, "adaptive": True, "effort": False, "enabled": False}


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _valid_model(name: str) -> str:
    ids = {m["id"] for m in get_available_models()} | {m["id"] for m in _FALLBACK_MODELS}
    return name if name in ids else DEFAULT_MODEL


def _valid_thinking(level: str) -> str:
    levels = {t["value"] for t in THINKING_LEVELS}
    return level if level in levels else DEFAULT_THINKING


def get_model() -> str:
    """Return the currently selected model ID, validated against the live list."""
    from data.reviews_db import get_app_setting
    return _valid_model(get_app_setting(_KEY_MODEL, DEFAULT_MODEL))


def get_thinking_level() -> str:
    """Return the currently selected thinking level (off/low/medium/high)."""
    from data.reviews_db import get_app_setting
    return _valid_thinking(get_app_setting(_KEY_THINKING, DEFAULT_THINKING))


def get_reasoning_kwargs() -> dict:
    """Return the reasoning kwargs (``thinking`` and optional ``output_config``)
    for the current model + thinking level, using the model's live capabilities.

    Current models (Opus 4.6+, Sonnet 4.6, Fable 5) use **adaptive thinking**
    plus an ``effort`` level — ``budget_tokens`` is rejected with a 400 on
    Opus 4.7/4.8. Older models that still accept ``budget_tokens`` fall back to
    the enabled-thinking path. ``{}`` when thinking is off or unsupported.
    """
    level = get_thinking_level()
    if level == "off":
        return {}
    lvl = next((t for t in THINKING_LEVELS if t["value"] == level), None)
    if lvl is None:
        return {}

    rec = _model_record(get_model())

    if rec.get("adaptive"):
        kwargs: dict = {"thinking": {"type": "adaptive"}}
        if rec.get("effort") and lvl["effort"]:
            kwargs["output_config"] = {"effort": lvl["effort"]}
        return kwargs

    if rec.get("enabled") and lvl["budget"] > 0:
        return {"thinking": {"type": "enabled", "budget_tokens": lvl["budget"]}}

    return {}


def set_model(model_id: str) -> None:
    from data.reviews_db import set_app_setting
    set_app_setting(_KEY_MODEL, _valid_model(model_id))


def set_thinking_level(level: str) -> None:
    from data.reviews_db import set_app_setting
    set_app_setting(_KEY_THINKING, _valid_thinking(level))


def model_options() -> list[dict]:
    """Return [{value, label}] suitable for a Mantine Select."""
    return [
        {"value": m["id"], "label": f"{m['label']}  ({m['tier']})"}
        for m in get_available_models()
    ]


def thinking_options() -> list[dict]:
    return [{"value": t["value"], "label": t["label"]} for t in THINKING_LEVELS]


def build_message_kwargs(max_tokens: int, **extra) -> dict:
    """Convenience: returns a kwargs dict ready to splat into
    ``client.messages.create(...)`` — model, max_tokens, and reasoning
    (thinking / effort) pre-populated from the current settings. Caller adds
    system, messages, tools, etc.
    """
    kwargs = {"model": get_model(), "max_tokens": max_tokens, **extra}
    kwargs.update(get_reasoning_kwargs())
    return kwargs
