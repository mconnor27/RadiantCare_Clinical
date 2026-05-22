"""NPPES NPI Registry API client for referring physician specialty lookup.

Taxonomy normalization is delegated to ``config.specialties.normalize_specialty``
so this module stays in lockstep with loader-side and RPM-side mapping.
"""

import time
import requests

from config.specialties import normalize_specialty

_NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"


def lookup_npi(npi: str) -> dict | None:
    """Look up a single NPI via the NPPES API.

    Returns {"specialty": str, "organization": str} or None if not found / error.
    """
    try:
        resp = requests.get(
            _NPPES_URL,
            params={"number": str(npi), "version": "2.1"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    if data.get("result_count", 0) == 0:
        return None

    result = data["results"][0]

    # --- Specialty from taxonomies ---
    specialty = None
    raw_taxonomy = ""
    taxonomies = result.get("taxonomies", [])
    # Prefer the primary taxonomy
    primary = next((t for t in taxonomies if t.get("primary")), None)
    tax = primary or (taxonomies[0] if taxonomies else None)
    if tax:
        desc = tax.get("desc", "")
        raw_taxonomy = desc
        # Normalize via shared specialty module; falls back to raw desc if unmapped.
        specialty = normalize_specialty(desc) or desc

    # --- Organization from basic info ---
    basic = result.get("basic", {})
    organization = basic.get("organization_name") or ""

    # --- Practice location address (prefer LOCATION over MAILING) ---
    addresses = result.get("addresses", [])
    practice = next(
        (a for a in addresses if (a.get("address_purpose") or "").upper() == "LOCATION"),
        None,
    )
    if practice is None and addresses:
        practice = addresses[0]

    address = city = state = zip_code = ""
    if practice:
        line1 = (practice.get("address_1") or "").strip()
        line2 = (practice.get("address_2") or "").strip()
        address = f"{line1} {line2}".strip() if line2 else line1
        city = (practice.get("city") or "").strip()
        state = (practice.get("state") or "").strip()
        postal = (practice.get("postal_code") or "").strip()
        # Normalize 9-digit ZIP+4 to 5-digit ("981010001" → "98101")
        zip_code = postal[:5] if postal else ""

    return {
        "specialty": specialty,
        "raw_taxonomy": raw_taxonomy,
        "organization": organization,
        "address": address,
        "city": city,
        "state": state,
        "zip_code": zip_code,
    }


def batch_lookup_npis(
    npis: list[str],
    on_progress=None,
    delay: float = 0.3,
) -> list[dict]:
    """Batch NPI lookups with rate limiting.

    Returns list of {"npi": str, "specialty": str|None, "organization": str|None}.
    Calls on_progress(done, total) after each lookup if provided.
    """
    results = []
    total = len(npis)
    for i, npi in enumerate(npis):
        info = lookup_npi(npi)
        results.append({
            "npi": str(npi),
            "specialty": info["specialty"] if info else None,
            "raw_taxonomy": info["raw_taxonomy"] if info else None,
            "organization": info["organization"] if info else None,
            "status": "found" if info else "not_found",
        })
        if on_progress:
            on_progress(i + 1, total)
        if i < total - 1:
            time.sleep(delay)
    return results
