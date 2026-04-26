"""Claude AI diagnosis classification for referral free-text diagnoses."""

import json
import re
import os

import anthropic

from config.settings import ANTHROPIC_API_KEY
from utils.diagnosis_categories import CATEGORIES, SUBCATEGORIES


def infer_diagnosis_categories(
    entries: list[dict],
) -> dict[str, dict]:
    """Classify diagnosis entries using Claude AI.

    Args:
        entries: list of {"key": str, "icd_code": str, "description": str,
                          "current_category": str, "current_subcategory": str, "patients": int}

    Returns:
        {key: {"category": str, "subcategory": str}} for entries where a classification was determined.
    """
    if not ANTHROPIC_API_KEY or not entries:
        return {}

    # Process in batches of 30
    results = {}
    batch_size = 30
    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        batch_results = _call_claude(batch)
        results.update(batch_results)

    return results


def _call_claude(entries: list[dict]) -> dict[str, dict]:
    """Call Claude API to classify diagnosis entries."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build the taxonomy reference
    taxonomy_lines = []
    for cat in CATEGORIES:
        subs = SUBCATEGORIES.get(cat, [])
        if subs:
            taxonomy_lines.append(f"- {cat}: {', '.join(subs)}")
        else:
            taxonomy_lines.append(f"- {cat}")
    taxonomy_text = "\n".join(taxonomy_lines)

    # Build the entries to classify
    entry_lines = []
    for e in entries:
        key = e["key"]
        icd = e.get("icd_code", "")
        desc = e.get("description", "")
        pts = e.get("patients", 0)
        curr_cat = e.get("current_category", "")
        curr_sub = e.get("current_subcategory", "")

        line = f"- Key: {key}"
        if icd:
            line += f", ICD: {icd}"
        if desc:
            line += f", Description: \"{desc}\""
        line += f", Patients: {pts}"
        if curr_cat:
            line += f", Current: {curr_cat}"
            if curr_sub:
                line += f" / {curr_sub}"
        entry_lines.append(line)
    entry_text = "\n".join(entry_lines)

    system_prompt = f"""You are a radiation oncology data analyst classifying diagnoses into treatment categories.

DIAGNOSIS TAXONOMY (category: subcategories):
{taxonomy_text}

Rules:
1. Each entry gets exactly ONE category and ONE subcategory from the taxonomy above.
2. For ICD codes, use your medical knowledge to classify correctly.
3. For free-text like "prostate", "L Breast", "lung", classify based on the text meaning.
4. Common abbreviations: L/Lt = Left, R/Rt = Right, CA = Cancer, mets = metastases, BCC = basal cell carcinoma, SCC = squamous cell carcinoma, GBM = glioblastoma.
5. Vague/administrative entries like "EVAL AND TREAT", "consult at 11", "follow up", "re-eval", scheduling notes → classify as category "Unknown" with subcategory "".
6. If a current classification exists and looks correct, confirm it.
7. Body part mentions without "met/mets" usually indicate the PRIMARY site, not metastasis.
8. Spine, bone, femur, rib mentions usually indicate metastatic disease (Metastases & Palliative / Bone Metastases).
9. "Brain" alone is ambiguous — could be primary brain tumor or brain mets. Default to Central Nervous System / Primary Brain unless "met" is mentioned."""

    user_prompt = f"""Classify these radiation oncology referral diagnoses. Return a JSON object mapping each key to {{"category": "...", "subcategory": "..."}}.

ENTRIES TO CLASSIFY:
{entry_text}

Return ONLY a JSON object like:
{{"prostate": {{"category": "GU \\u2013 Prostate", "subcategory": "Prostate Cancer"}}, "l breast": {{"category": "Breast", "subcategory": "Left"}}, "consult at 11": {{"category": "Unknown", "subcategory": ""}}}}

For entries that are not a diagnosis (scheduling notes, vague admin text), use category "Unknown". Only map to null if you truly have zero information."""

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

        # Extract JSON — may be wrapped in markdown code block
        json_match = re.search(r"\{[\s\S]*\}", full_text)
        if not json_match:
            return {}

        parsed = json.loads(json_match.group())
        # Filter out null values and validate against taxonomy
        results = {}
        valid_cats = set(CATEGORIES) | {"Unknown"}
        for key, val in parsed.items():
            if val is None:
                continue
            cat = val.get("category", "")
            sub = val.get("subcategory", "")
            if cat in valid_cats:
                results[key] = {"category": cat, "subcategory": sub}

        return results

    except (anthropic.APIError, json.JSONDecodeError, Exception):
        return {}
