"""NPPES NPI Registry API client for referring physician specialty lookup."""

import time
import requests

# NPPES taxonomy description → normalized ABMS-aligned specialty name
# Covers the most common taxonomies returned by the NPI Registry.
_TAXONOMY_MAP = {
    # Primary Care
    "Family Medicine": "Primary Care",
    "Family Practice": "Primary Care",
    "General Practice": "Primary Care",
    "Adolescent Medicine (Family Medicine)": "Primary Care",
    # Internal Medicine
    "Internal Medicine": "Internal Medicine",
    "Geriatric Medicine (Internal Medicine)": "Internal Medicine",
    "Hospitalist": "Hospital Medicine",
    "Hospital Medicine": "Hospital Medicine",
    # Medical Oncology / Hematology
    "Medical Oncology": "Medical Oncology",
    "Hematology & Oncology": "Medical Oncology",
    "Hematology (Internal Medicine)": "Medical Oncology",
    "Hematology/Oncology": "Medical Oncology",
    # Radiation Oncology
    "Radiation Oncology": "Radiation Oncology",
    # Surgical Oncology
    "Surgical Oncology": "Surgical Oncology",
    # Gynecologic Oncology
    "Gynecologic Oncology": "Gynecologic Oncology",
    "Gynecological Oncology": "Gynecologic Oncology",
    # Urology
    "Urology": "Urology",
    "Urologist": "Urology",
    # Pulmonary
    "Pulmonary Disease": "Pulmonary Medicine",
    "Pulmonary Disease (Internal Medicine)": "Pulmonary Medicine",
    "Interventional Pulmonology": "Pulmonary Medicine",
    "Pulmonary Critical Care Medicine": "Pulmonary Medicine",
    # Neurology
    "Neurology": "Neurology",
    "Neurology with Special Qualifications in Child Neurology": "Neurology",
    "Neuromuscular Medicine": "Neurology",
    # Neurosurgery
    "Neurological Surgery": "Neurosurgery",
    "Neurosurgery": "Neurosurgery",
    # Cardiology
    "Cardiovascular Disease": "Cardiology",
    "Cardiovascular Disease (Internal Medicine)": "Cardiology",
    "Interventional Cardiology": "Cardiology",
    "Clinical Cardiac Electrophysiology": "Cardiology",
    "Cardiology": "Cardiology",
    # Gastroenterology
    "Gastroenterology": "Gastroenterology",
    "Gastroenterology (Internal Medicine)": "Gastroenterology",
    # Surgery
    "General Surgery": "General Surgery",
    "Surgery": "General Surgery",
    "Surgical Critical Care": "General Surgery",
    "Vascular Surgery": "Vascular Surgery",
    "Thoracic Surgery (Cardiothoracic Vascular Surgery)": "Thoracic Surgery",
    "Thoracic Surgery": "Thoracic Surgery",
    # Colorectal
    "Colon & Rectal Surgery": "Colorectal Surgery",
    "Colorectal Surgery": "Colorectal Surgery",
    # Orthopedics
    "Orthopaedic Surgery": "Orthopedics",
    "Orthopedic Surgery": "Orthopedics",
    "Sports Medicine (Orthopedic Surgery)": "Orthopedics",
    # ENT
    "Otolaryngology": "Otolaryngology",
    "Otolaryngology/Facial Plastic Surgery": "Otolaryngology",
    "Otolaryngic Allergy": "Otolaryngology",
    # OB/GYN
    "Obstetrics & Gynecology": "OB/GYN",
    "Obstetrics": "OB/GYN",
    "Gynecology": "OB/GYN",
    # Ophthalmology
    "Ophthalmology": "Ophthalmology",
    # Dermatology
    "Dermatology": "Dermatology",
    "Dermatopathology": "Dermatology",
    # Radiology
    "Diagnostic Radiology": "Radiology",
    "Interventional Radiology": "Radiology",
    "Neuroradiology": "Radiology",
    "Radiation Oncology": "Radiation Oncology",
    # Pathology
    "Pathology": "Pathology",
    "Anatomic Pathology": "Pathology",
    "Clinical Pathology": "Pathology",
    "Anatomic Pathology & Clinical Pathology": "Pathology",
    # Emergency
    "Emergency Medicine": "Emergency Medicine",
    # Nephrology
    "Nephrology": "Nephrology",
    "Nephrology (Internal Medicine)": "Nephrology",
    # Endocrinology
    "Endocrinology, Diabetes & Metabolism": "Endocrinology",
    "Endocrinology": "Endocrinology",
    # Rheumatology
    "Rheumatology": "Rheumatology",
    # Infectious Disease
    "Infectious Disease": "Infectious Disease",
    "Infectious Disease (Internal Medicine)": "Infectious Disease",
    # PM&R
    "Physical Medicine & Rehabilitation": "PM&R",
    "Physical Medicine and Rehabilitation": "PM&R",
    # Psychiatry
    "Psychiatry": "Psychiatry",
    "Psychiatry & Neurology": "Psychiatry",
    # Palliative
    "Hospice and Palliative Medicine": "Palliative Care",
    "Hospice and Palliative Medicine (Internal Medicine)": "Palliative Care",
    # Pediatrics
    "Pediatrics": "Pediatrics",
    "Pediatric Hematology-Oncology": "Pediatric Oncology",
    "Pediatric Medicine": "Pediatrics",
    # PA / NP
    "Physician Assistant": "PA/NP",
    "Nurse Practitioner": "PA/NP",
    "Family Nurse Practitioner": "PA/NP",
    "Adult Health": "PA/NP",
    # Plastic Surgery
    "Plastic Surgery": "Plastic Surgery",
    "Plastic and Reconstructive Surgery": "Plastic Surgery",
    "Plastic Surgery Within the Head and Neck": "Plastic Surgery",
    # Oral Surgery
    "Oral and Maxillofacial Surgery": "Oral Surgery",
    "Dentist": "Oral Surgery",
    # Breast Surgery
    "Breast Surgery": "Breast Surgery",
    # Hepatology
    "Transplant Hepatology": "Hepatology",
    "Hepatology": "Hepatology",
    # Neuro-Oncology
    "Neuro-Oncology": "Neuro-Oncology",
    # Allergy / Immunology
    "Allergy & Immunology": "Allergy & Immunology",
}

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
        specialty = _TAXONOMY_MAP.get(desc, desc)  # Fall back to raw description

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
