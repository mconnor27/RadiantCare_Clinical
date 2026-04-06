"""Claude AI institution inference for referring physicians via web search."""

import json
import re
import os

import anthropic

from config.settings import ANTHROPIC_API_KEY

# Departments that clearly belong to Providence — skip web search
_PROVIDENCE_RE = re.compile(
    r"PMG|PRCS|PH&S|PROVIDENCE|PSJH|SW\s*WA|KADLEC|SWEDISH",
    re.IGNORECASE,
)


def _is_providence(department: str) -> bool:
    return bool(department and _PROVIDENCE_RE.search(department))


def infer_institutions(
    physicians: list[dict],
    existing_institutions: list[str],
) -> dict[str, str]:
    """Research institution names for referring physicians using Claude + web search.

    Args:
        physicians: list of {"npi": str, "name": str, "city_state": str, "department": str}
        existing_institutions: list of institution names already in the database
            (so Claude reuses existing names when possible)

    Returns:
        {npi: institution_name} for physicians where institution was determined.
    """
    if not ANTHROPIC_API_KEY:
        return {}

    # Fast-path: Providence departments don't need API calls
    results = {}
    need_lookup = []
    for phys in physicians:
        dept = phys.get("department", "") or ""
        if _is_providence(dept):
            # Use city for geographic distinction
            city = (phys.get("city_state", "") or "").split(",")[0].strip()
            results[phys["npi"]] = f"Providence {city}" if city else "Providence"
        else:
            need_lookup.append(phys)

    if not need_lookup:
        return results

    # Batch into groups of 15 for API calls
    batch_size = 15
    for i in range(0, len(need_lookup), batch_size):
        batch = need_lookup[i : i + batch_size]
        batch_results = _call_claude(batch, existing_institutions)
        results.update(batch_results)

    return results


def _call_claude(
    physicians: list[dict],
    existing_institutions: list[str],
) -> dict[str, str]:
    """Call Claude API with web search to research physician institutions."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    institution_list = "\n".join(f"- {inst}" for inst in existing_institutions) if existing_institutions else "(none yet)"

    physician_lines = []
    for p in physicians:
        physician_lines.append(
            f"- NPI: {p.get('npi', 'N/A')}, Name: {p.get('name', 'Unknown')}, "
            f"Location: {p.get('city_state', 'Unknown')}, Department: {p.get('department', 'Unknown')}"
        )
    physician_text = "\n".join(physician_lines)

    system_prompt = """You are a medical data analyst helping identify the institution/practice that referring physicians belong to.

For each physician, determine their institution using web search when needed. Guidelines:

1. Use BROAD institution names: "Providence", "Kaiser Permanente", "Virginia Mason", "Fred Hutch", "MultiCare", "UW Medicine", "Seattle Cancer Care Alliance", etc.
2. Different cities CAN be distinct entries (e.g., "Providence Olympia" vs "Providence Seattle") but minor office variations within a city should collapse to one name.
3. When possible, reuse institution names from the existing list below to maintain consistency.
4. If you cannot determine the institution with reasonable confidence, return null for that physician.
5. For Providence-affiliated departments (PMG, PRCS, etc.), just return "Providence" + city.

EXISTING INSTITUTIONS (reuse these names when they match):
""" + institution_list

    user_prompt = f"""Research the following physicians and determine their institution/practice name. Return a JSON object mapping NPI to institution name.

PHYSICIANS:
{physician_text}

Return ONLY a JSON object like: {{"1234567890": "Providence Olympia", "0987654321": "Kaiser Permanente Tacoma"}}
NPIs where you cannot determine the institution should map to null."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract the text response (may have tool_use blocks interspersed)
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        full_text = "\n".join(text_parts)

        # Extract JSON from the response
        json_match = re.search(r"\{[^{}]*\}", full_text, re.DOTALL)
        if not json_match:
            return {}

        parsed = json.loads(json_match.group())
        # Filter out null values
        return {npi: inst for npi, inst in parsed.items() if inst}

    except (anthropic.APIError, json.JSONDecodeError, Exception):
        return {}
