"""Claude AI classification for raw insurance payor names.

Returns a standardized payor name, broad category, PHDSC category, and a
short rationale for each raw name. Modeled on diagnosis_inference.py.
"""

import json
import re

import anthropic

from config.settings import ANTHROPIC_API_KEY


_BROAD_CATEGORIES = [
    "Medicare", "Medicaid", "Private", "Military/VA",
    "Workers Comp", "Tribal/IHS", "Self Pay", "Other/Unknown",
]

_PHDSC_CATEGORIES = [
    "1 - Medicare", "2 - Medicaid/CHIP", "3 - Other Govt",
    "4 - Corrections", "5 - Private", "6 - BCBS",
    "8 - No Payment", "9 - Other",
]


def infer_payor_classifications(
    entries: list[dict],
    existing_standardized: list[str] | None = None,
) -> dict[str, dict]:
    """Classify raw insurance names using Claude.

    Args:
        entries: list of {"raw_name": str, "event_count": int,
                          "current_standardized": str,
                          "current_broad": str, "current_phdsc": str}
        existing_standardized: list of standardized payor names already in
            use (so Claude reuses them instead of inventing variants).

    Returns:
        {raw_name: {"standardized_payor": str, "broad_category": str,
                    "phdsc_category": str, "explanation": str}}
        for entries where a classification was determined.
    """
    if not ANTHROPIC_API_KEY or not entries:
        return {}

    results: dict[str, dict] = {}
    batch_size = 25
    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        batch_results = _call_claude(batch, existing_standardized or [])
        results.update(batch_results)
    return results


def _call_claude(
    entries: list[dict],
    existing_standardized: list[str],
) -> dict[str, dict]:
    """Single Claude call to classify a batch of raw payor names."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    existing_text = (
        "\n".join(f"- {n}" for n in sorted(existing_standardized) if n)
        if existing_standardized else "(none yet)"
    )

    entry_lines = []
    for e in entries:
        line = f"- raw_name: \"{e.get('raw_name', '')}\""
        if e.get("event_count"):
            line += f", events: {e['event_count']}"
        cur_std = e.get("current_standardized") or ""
        cur_broad = e.get("current_broad") or ""
        cur_phdsc = e.get("current_phdsc") or ""
        if cur_std or cur_broad or cur_phdsc:
            line += f", current: std=\"{cur_std}\", broad=\"{cur_broad}\", phdsc=\"{cur_phdsc}\""
        entry_lines.append(line)
    entry_text = "\n".join(entry_lines)

    broad_text = ", ".join(_BROAD_CATEGORIES)
    phdsc_text = "\n".join(f"  - {p}" for p in _PHDSC_CATEGORIES)

    system_prompt = f"""You are a healthcare revenue-cycle analyst classifying raw insurance payor names from a radiation oncology billing system in Washington State.

For each raw_name, return:
1. standardized_payor — a clean, canonical payor name (e.g. "Aetna", "Premera Blue Cross", "Molina Healthcare WA Medicaid"). REUSE names from the existing list below whenever they match; only invent a new name if no existing one fits.
2. broad_category — exactly one of: {broad_text}
3. phdsc_category — exactly one of (use the FULL string with the number prefix):
{phdsc_text}
4. explanation — ONE concise sentence (≤ 25 words) explaining the classification, citing what about the raw name signals the category. Mention plan type, government program, or BCBS affiliation if relevant.

Rules:
- Medicare Advantage plans (e.g. "Humana Medicare Advantage", "United Healthcare AARP", "Kaiser Senior Advantage") → broad=Medicare, phdsc=1 - Medicare.
- WA Medicaid managed-care plans (Apple Health via Molina, Coordinated Care, Amerigroup, CHPW, Wellpoint, United Healthcare Community Plan, etc.) → broad=Medicaid, phdsc=2 - Medicaid/CHIP.
- Blue Cross / Blue Shield / Premera / Regence / Anthem → broad=Private, phdsc=6 - BCBS.
- TRICARE, CHAMPVA, VA, US Family Health Plan → broad=Military/VA, phdsc=3 - Other Govt.
- Labor & Industries, workers comp carriers (Sedgwick, CorVel, Gallagher Bassett, etc.) → broad=Workers Comp, phdsc=3 - Other Govt.
- Tribal health (Indian Health Service, Quinault, Chehalis, Nisqually, Tongas, Squaxin) → broad=Tribal/IHS, phdsc=3 - Other Govt.
- Department of Corrections, county jails, prison medical → broad=Other/Unknown, phdsc=4 - Corrections.
- Self pay / patient pay / cash → broad=Self Pay, phdsc=8 - No Payment.
- Commercial/employer plans (Aetna, Cigna, United Healthcare commercial, Kaiser Permanente commercial) → broad=Private, phdsc=5 - Private.
- Unknown / illegible / blank → broad=Other/Unknown, phdsc=9 - Other.
- If a current classification looks correct, confirm it and explain briefly.

EXISTING STANDARDIZED PAYOR NAMES (reuse when applicable):
{existing_text}"""

    user_prompt = f"""Classify these raw insurance names. Return ONLY a JSON object mapping each raw_name (verbatim) to {{"standardized_payor": ..., "broad_category": ..., "phdsc_category": ..., "explanation": ...}}.

ENTRIES:
{entry_text}

Example shape:
{{"MOLINA HEALTHCARE OF WA INC": {{"standardized_payor": "Molina Healthcare WA Medicaid", "broad_category": "Medicaid", "phdsc_category": "2 - Medicaid/CHIP", "explanation": "Molina's Washington plan is Apple Health Medicaid managed care."}}}}

For entries you truly cannot classify, omit them from the response (do not return null)."""

    try:
        from utils.ai_config import build_message_kwargs
        response = client.messages.create(
            **build_message_kwargs(
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        )

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        full_text = "\n".join(text_parts)

        json_match = re.search(r"\{[\s\S]*\}", full_text)
        if not json_match:
            return {}

        parsed = json.loads(json_match.group())

        # Normalize both response shapes:
        # 1) flat dict-of-dicts: {"raw_name": {"standardized_payor": ...}}
        # 2) wrapped list: {"results": [{"raw_name": "X", "standardized_payor": ...}, ...]}
        # Sonnet 4.6+ tends to return shape (2); older models return (1).
        records: list[tuple[str, dict]] = []
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            for item in parsed["results"]:
                if isinstance(item, dict):
                    raw = (item.get("raw_name") or "").strip()
                    if raw:
                        records.append((raw, item))
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    raw = (item.get("raw_name") or "").strip()
                    if raw:
                        records.append((raw, item))
        else:
            for raw, val in parsed.items():
                if isinstance(val, dict):
                    records.append((raw, val))

        valid_broad = set(_BROAD_CATEGORIES)
        valid_phdsc = set(_PHDSC_CATEGORIES)

        results: dict[str, dict] = {}
        for raw, val in records:
            std = (val.get("standardized_payor") or "").strip()
            broad = (val.get("broad_category") or "").strip()
            phdsc = (val.get("phdsc_category") or "").strip()
            expl = (val.get("explanation") or "").strip()
            if broad not in valid_broad:
                broad = "Other/Unknown"
            if phdsc not in valid_phdsc:
                phdsc = "9 - Other"
            results[raw] = {
                "standardized_payor": std,
                "broad_category": broad,
                "phdsc_category": phdsc,
                "explanation": expl,
            }
        return results

    except (anthropic.APIError, json.JSONDecodeError) as e:
        print(f"[payor_inference] {type(e).__name__}: {e}", flush=True)
        return {}
    except Exception as e:
        # Unexpected — log + re-raise during dev-friendly debugging
        print(f"[payor_inference] unexpected {type(e).__name__}: {e}", flush=True)
        return {}
