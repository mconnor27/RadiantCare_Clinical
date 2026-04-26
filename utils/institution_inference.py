"""Claude AI institution + address inference for referring physicians via web search."""

import json
import re

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
) -> dict[str, dict]:
    """Research institution + practice address for referring physicians via Claude + web search.

    Args:
        physicians: list of {"npi": str, "name": str, "city_state": str,
                             "department": str, "first_referral": str, "last_referral": str}
            ``first_referral`` / ``last_referral`` are MM/DD/YYYY date strings used to
            anchor the AI to the practice the physician held during that window
            (handles MDs who change offices over time).
        existing_institutions: list of institution names already in the DB
            (so Claude reuses existing names when possible).

    Returns:
        ``{npi: {"institution": str, "address": str, "city": str, "state": str,
                 "zip_code": str, "effective_date_range": str}}``
        for physicians where at least an institution was determined.
        Address fields are empty strings when the AI can't pin them down.

    Notes:
        - The return shape changed from ``{npi: str}`` (institution only) to
          ``{npi: dict}``. Callers must read ``result["institution"]`` and
          (optionally) the address fields.
    """
    if not ANTHROPIC_API_KEY:
        return {}

    # Fast-path: Providence departments don't need API calls. We still don't
    # know the address from the department alone, so address stays blank.
    results: dict[str, dict] = {}
    need_lookup = []
    for phys in physicians:
        dept = phys.get("department", "") or ""
        if _is_providence(dept):
            city = (phys.get("city_state", "") or "").split(",")[0].strip()
            results[phys["npi"]] = {
                "institution": f"Providence {city}" if city else "Providence",
                "address": "", "city": "", "state": "", "zip_code": "",
                "effective_date_range": "",
            }
        else:
            need_lookup.append(phys)

    if not need_lookup:
        return results

    batch_size = 15
    for i in range(0, len(need_lookup), batch_size):
        batch = need_lookup[i : i + batch_size]
        batch_results = _call_claude(batch, existing_institutions)
        results.update(batch_results)

    return results


def _call_claude(
    physicians: list[dict],
    existing_institutions: list[str],
) -> dict[str, dict]:
    """Call Claude API with web search to research physician institution + address."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    institution_list = (
        "\n".join(f"- {inst}" for inst in existing_institutions)
        if existing_institutions else "(none yet)"
    )

    physician_lines = []
    for p in physicians:
        first = (p.get("first_referral") or "").strip()
        last = (p.get("last_referral") or "").strip()
        if first and last and first != last:
            window = f"referred {first} to {last}"
        elif first or last:
            window = f"referred {first or last}"
        else:
            window = "referral dates unknown"
        physician_lines.append(
            f"- NPI: {p.get('npi', 'N/A')}, Name: {p.get('name', 'Unknown')}, "
            f"Location hint: {p.get('city_state', 'Unknown')}, "
            f"Department: {p.get('department', 'Unknown')}, "
            f"Window: {window}"
        )
    physician_text = "\n".join(physician_lines)

    system_prompt = """You are a medical data analyst identifying both the INSTITUTION and the PRACTICE ADDRESS of referring physicians.

For each physician, return:
1. institution — broad institution name (e.g. "Providence", "Kaiser Permanente", "Virginia Mason", "MultiCare", "UW Medicine"). Different cities CAN be distinct (e.g. "Providence Olympia" vs "Providence Seattle"). Reuse names from the existing list when they match.
2. address — physical street address of the practice the physician worked at during the referral window (street + suite if applicable). Use the WINDOW field as your time anchor — many physicians change offices over the years, and an out-of-date address is worse than no address.
3. city, state, zip_code — separate components for the same address.
4. effective_date_range — short string describing what time window the address is valid for (e.g. "2018-2024", "current", "as of 2022"). Empty if unknown.

Address rules:
- Only return an address if you have HIGH confidence it matches the physician+window. Wrong addresses corrupt downstream maps and reports — silence is better than a guess.
- Prefer the office that matches the city/state hint. If the physician has multiple offices, pick the one consistent with the referral window.
- For Providence-affiliated physicians, the address is typically the Providence clinic in the city listed.
- If you can find the institution but NOT the address, return institution + empty address fields. Do not invent.

If you cannot determine the institution with reasonable confidence, omit that NPI from the response (do not return null).

EXISTING INSTITUTIONS (reuse these names when they match):
""" + institution_list

    user_prompt = f"""Research these physicians via web search. Return ONLY a JSON object mapping NPI to a dict with keys: institution, address, city, state, zip_code, effective_date_range.

PHYSICIANS:
{physician_text}

Example response:
{{"1234567890": {{"institution": "Providence Olympia", "address": "413 Lilly Rd NE", "city": "Olympia", "state": "WA", "zip_code": "98506", "effective_date_range": "current"}}, "0987654321": {{"institution": "Kaiser Permanente Tacoma", "address": "", "city": "", "state": "", "zip_code": "", "effective_date_range": ""}}}}

Omit NPIs you cannot identify."""

    try:
        from utils.ai_config import build_message_kwargs
        response = client.messages.create(
            **build_message_kwargs(
                max_tokens=4096,
                system=system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
                messages=[{"role": "user", "content": user_prompt}],
            )
        )

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        full_text = "\n".join(text_parts)

        # JSON may be wrapped in code fences; grab the largest brace-balanced object.
        json_match = re.search(r"\{[\s\S]*\}", full_text)
        if not json_match:
            return {}

        parsed = json.loads(json_match.group())

        # Normalize both response shapes (see utils/payor_inference.py for context):
        # Sonnet/Opus 4.x often return {"results": [{"npi": "X", ...}, ...]}
        # instead of the requested flat {npi: {...}} dict.
        records: list[tuple[str, object]] = []
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            for item in parsed["results"]:
                if isinstance(item, dict):
                    npi = str(item.get("npi") or "").strip()
                    if npi:
                        records.append((npi, item))
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    npi = str(item.get("npi") or "").strip()
                    if npi:
                        records.append((npi, item))
        else:
            for npi, val in parsed.items():
                records.append((npi, val))

        results: dict[str, dict] = {}
        for npi, val in records:
            # Tolerate the older string-only response shape just in case.
            if isinstance(val, str):
                if val:
                    results[npi] = {
                        "institution": val, "address": "", "city": "",
                        "state": "", "zip_code": "", "effective_date_range": "",
                    }
                continue
            if not isinstance(val, dict):
                continue
            inst = (val.get("institution") or "").strip()
            if not inst:
                continue
            postal = (val.get("zip_code") or "").strip()
            zip_clean = postal[:5] if postal else ""
            results[npi] = {
                "institution": inst,
                "address": (val.get("address") or "").strip(),
                "city": (val.get("city") or "").strip(),
                "state": (val.get("state") or "").strip().upper()[:2],
                "zip_code": zip_clean,
                "effective_date_range": (val.get("effective_date_range") or "").strip(),
            }
        return results

    except (anthropic.APIError, json.JSONDecodeError) as e:
        print(f"[institution_inference] {type(e).__name__}: {e}", flush=True)
        return {}
    except Exception as e:
        print(f"[institution_inference] unexpected {type(e).__name__}: {e}", flush=True)
        return {}
