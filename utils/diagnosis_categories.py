"""Map ICD-9/ICD-10 diagnosis codes to clinical treatment categories.

This module replaces the raw BodySystemDesc/SiteDesc values from the
Lookup - Diagnosis CSV with curated treatment-oriented categories aligned
to radiation oncology practice (NCCN-style grouping).

Resolution order
-----------------
1. Exact code match in ``_ICD_OVERRIDES`` (fixes known lookup bugs)
2. Exact code match in ``_ICD_CODE_CATEGORY``
3. Longest-prefix match in ``_ICD_PREFIX_CATEGORY``
4. ``SiteDesc`` lookup in ``_SITE_TO_CATEGORY``
5. ``BodySystemDesc`` fallback in ``_BODY_SYSTEM_FALLBACK``
6. ``"Uncategorized"``

Public API
----------
- ``CATEGORIES``              – sorted list of category display names
- ``build_code_to_category``  – build {DiagnosisCode: category} from lookup df
- ``get_categories_for_codes`` – return set of categories for comma-sep codes
- ``primary_category``        – return first matching category for comma-sep codes
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Seed taxonomy — used only to populate the DB on first run
# ---------------------------------------------------------------------------
_SEED_SUBCATEGORIES: dict[str, list[str]] = {
    "Benign Diseases": [
        "Dupuytren / Plantar", "Gynecomastia", "Hemangioma",
        "Heterotopic Ossification", "Keloid / Scar", "Neurofibromatosis",
        "Orbital Pseudotumor", "Osteoarthritis", "Rheumatoid Arthritis",
    ],
    "Breast": ["Left", "Male", "Right", "Unspecified Laterality"],
    "Central Nervous System": [
        "AVM", "Craniopharyngioma", "Glioma / Primary Brain",
        "Hemangioblastoma", "Meningioma", "Ocular / Orbit", "Paraganglioma",
        "Pituitary / Pineal", "Schwannoma", "Spinal Cord",
    ],
    "GU – Non-Prostate": [
        "Adrenal", "Bladder", "Kidney / RCC", "Penile", "Testicular", "Urethra",
    ],
    "GU – Prostate": ["Prostate Cancer"],
    "Gastrointestinal": [
        "Anal", "Biliary", "Colon", "Esophageal",
        "GIST", "Gastric", "Liver / HCC", "Neuroendocrine",
        "Other/Unspecified", "Pancreatic", "Rectal", "Small Intestine",
    ],
    "Gynecologic": [
        "Cervical", "Fallopian / Adnexal", "Other", "Ovarian",
        "Uterine / Endometrial", "Vaginal", "Vulvar",
    ],
    "Head and Neck": [
        "Hypopharynx", "Larynx", "Nasal Cavity / Sinus", "Nasopharynx",
        "Oral Cavity", "Oropharynx", "Salivary Gland", "Thyroid", "Trachea",
        "Unknown Primary/Other",
    ],
    "Hematologic": [
        "Hodgkin Lymphoma", "Kaposi Sarcoma", "Langerhans", "Leukemia", "MALT",
        "MDS/PMF/Splenomegaly", "Mantle Cell", "Mycosis Fungoides",
        "Myeloma / Plasmacytoma", "Non-Hodgkin Lymphoma (Diffuse)",
        "Non-Hodgkin Lymphoma (Follicular)", "Non-Hodgkin Lymphoma (Other)",
        "Other/Unspecified", "T-Cell Lymphoma",
    ],
    "Metastases & Palliative": [
        "Adrenal Metastases", "Bone Metastases", "Brain Metastases",
        "Liver Metastases", "Lung Metastases", "Lymph Node Metastases",
        "Neuroendocrine Metastases", "Other Metastases", "Skin Metastases",
    ],
    "Sarcomas": [
        "Bone Sarcoma", "Other/Unspecified", "Peripheral Nerve Sheath",
        "Retroperitoneal Sarcoma", "Soft Tissue Sarcoma",
    ],
    "Skin": [
        "Melanoma", "Merkel Cell", "Non-Melanoma Skin Cancer",
        "Other/Unspecified",
    ],
    "Thoracic": [
        "Lung Cancer", "Mediastinal", "Mesothelioma", "Neuroendocrine",
        "Other", "Thymic",
    ],
}


# ---------------------------------------------------------------------------
# Live taxonomy — reads from DB, auto-seeds on first use
# ---------------------------------------------------------------------------
def _load_taxonomy() -> dict[str, list[str]]:
    """Load taxonomy from DB. Seeds from _SEED_SUBCATEGORIES on first run."""
    try:
        from data.reviews_db import get_diagnosis_taxonomy, taxonomy_table_row_count, seed_taxonomy
        if taxonomy_table_row_count() == 0:
            seed_taxonomy(_SEED_SUBCATEGORIES)
        return get_diagnosis_taxonomy()
    except Exception:
        return dict(_SEED_SUBCATEGORIES)


def get_taxonomy() -> dict[str, list[str]]:
    """Return the current {category: [subcategories]} from the DB."""
    return _load_taxonomy()


# Module-level references — refreshed via get_taxonomy() for live reads,
# but these provide stable import-time values for page layouts.
SUBCATEGORIES: dict[str, list[str]] = _load_taxonomy()
CATEGORIES: list[str] = sorted(SUBCATEGORIES.keys())
ALL_SUBCATEGORIES: list[str] = sorted(
    {sc for subs in SUBCATEGORIES.values() for sc in subs}
)


# ---------------------------------------------------------------------------
# ICD code → subcategory mapping (loaded from CSV)
# ---------------------------------------------------------------------------
def _load_subcategory_csv() -> dict[str, tuple[str, str]]:
    """Load {icd_code: (category, subcategory)} from data/diagnosis_subcategories.csv."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "diagnosis_subcategories.csv"
    if not csv_path.exists():
        return {}
    result: dict[str, tuple[str, str]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["icd_code"].strip()
            cat = row["category"].strip()
            subcat = row.get("subcategory", "").strip()
            if code and cat:
                result[code] = (cat, subcat)
    return result


_SUBCATEGORY_MAP: dict[str, tuple[str, str]] = _load_subcategory_csv()

# Track codes already auto-seeded this session (avoid repeated DB writes)
_seen_new: set[str] = set()

# ---------------------------------------------------------------------------
# Step 1: Exact overrides – fix known lookup bugs or force routing
# ---------------------------------------------------------------------------
_ICD_OVERRIDES: dict[str, str] = {
    # Lookup bugs (SiteDesc is wrong in ARIA export)
    "C61":    "GU – Prostate",           # lookup says SiteDesc="Bone"
    "D32.0":  "Central Nervous System",  # lookup says SiteDesc="Larynx" (meningioma)
    "C06.0":  "Head and Neck",           # lookup says SiteDesc="Penis" (cheek mucosa)

    # NETs → Thoracic (small-cell / carcinoid family)
    "C7A.1":  "Thoracic",
    "C7A.8":  "Thoracic",

    # Sezary / Mycosis fungoides → Hematologic (T-cell lymphoma)
    "C84.00": "Hematologic",
    "C84.04": "Hematologic",
    "C84.08": "Hematologic",
    "C84.09": "Hematologic",

    # ARIA SiteDesc bugs (ICD code meaning overrides wrong SiteDesc)
    "C50.912": "Breast",                 # lookup says SiteDesc="Leukemia" — actually breast cancer
    "C71.8":   "Central Nervous System",  # lookup says SiteDesc="Bone" — actually brain tumor
    "162.0":   "Thoracic",               # lookup says SiteDesc="Head & Neck (Misc)" — actually trachea
    "195.0":   "Head and Neck",          # ICD-9 ill-defined head/face/neck; routed to Skin via H&N (Misc)
    "187.7":   "GU – Non-Prostate",      # lookup says SiteDesc="Skin" — actually scrotum
    "228.00":  "Benign Diseases",        # hemangioma unspecified; was routed to Mets via "Other Sites"

    # ICD-9 ill-defined sites misrouted via Endocrine → "Glands (Misc)" → CNS
    "195.4":   "Metastases & Palliative",  # ill-defined upper limb
    "195.5":   "Metastases & Palliative",  # ill-defined lower limb

    # Uterine leiomyoma → Gynecologic (benign but treated by gyn rad onc)
    "D25.9":   "Gynecologic",

    # --- Codes found unresolved in referral data ---
    "C62.90":  "GU – Non-Prostate",       # testicular, unspecified
    "C62.92":  "GU – Non-Prostate",       # testicular, left
    "C62.91":  "GU – Non-Prostate",       # testicular, right
    "C68.9":   "GU – Non-Prostate",       # urinary organ, unspecified
    "C17.9":   "Gastrointestinal",        # small intestine, unspecified
    "C18.5":   "Gastrointestinal",        # splenic flexure
    "C24.9":   "Gastrointestinal",        # biliary tract
    "C05.2":   "Head and Neck",           # uvula
    "C72.30":  "Central Nervous System",  # optic nerve
    "C69.90":  "Central Nervous System",  # eye, unspecified
    "C74.91":  "GU – Non-Prostate",       # adrenal gland, right
    "C74.92":  "GU – Non-Prostate",       # adrenal gland, left
    "C76.50":  "Metastases & Palliative", # lower limb, ill-defined
    "C44.221": "Skin",                    # SCC of ear
    "C44.92":  "Skin",                    # skin, unspecified
    "D49.89":  "Thoracic",               # neoplasm uncertain behaviour (thymoma in referral data)
    "D49.9":   "Metastases & Palliative", # neoplasm NOS
    "D3A.00":  "Thoracic",               # carcinoid tumour NOS
    "C7A.00":  "Thoracic",               # malignant carcinoid NOS
    "D09.9":   "Skin",                   # carcinoma in situ NOS (SCC in-situ in referral data)
    "D44.7":   "Central Nervous System",  # paraganglioma
    "D47.2":   "Hematologic",            # MGUS
    "D75.1":   "Hematologic",            # polycythemia
    "D36.10":  "Central Nervous System",  # schwannoma
    "G93.89":  "Central Nervous System",  # brain mass / lesion
    "G93.9":   "Central Nervous System",  # brain disorder NOS
    "E23.6":   "Central Nervous System",  # pituitary disorder
    "E23.7":   "Central Nervous System",  # pituitary lesion
    "G50.0":   "Benign Diseases",         # trigeminal neuralgia
    "J38.3":   "Head and Neck",           # vocal cord dysplasia
    "K13.70":  "Head and Neck",           # mouth lesion
    "J98.59":  "Thoracic",               # mediastinal mass
    "M81.0":   "Benign Diseases",         # osteoporosis
    "M84.550A": "Metastases & Palliative", # pathologic fracture pelvis
    "M84.551D": "Metastases & Palliative", # pathologic fracture hip
    "M84.48XA": "Metastases & Palliative", # pathologic rib fracture
    "M89.9":   "Metastases & Palliative", # bone lesion NOS
}

# ---------------------------------------------------------------------------
# Step 2: Exact code → category
# ---------------------------------------------------------------------------
_ICD_CODE_CATEGORY: dict[str, str] = {
    # ── Metastases & Palliative ──────────────────────────────────
    "C79.31": "Metastases & Palliative",   # secondary brain
    "C79.32": "Metastases & Palliative",   # secondary cerebral meninges
    "C79.40": "Metastases & Palliative",   # secondary nervous system NOS
    "C79.49": "Metastases & Palliative",   # secondary other nervous system
    "C79.51": "Metastases & Palliative",   # secondary bone
    "C79.52": "Metastases & Palliative",   # secondary bone marrow
    "C79.02": "Metastases & Palliative",   # secondary kidney
    "C79.10": "Metastases & Palliative",   # secondary urinary organs NOS
    "C79.11": "Metastases & Palliative",   # secondary bladder
    "C79.2":  "Metastases & Palliative",   # secondary skin
    "C79.71": "Metastases & Palliative",   # secondary right adrenal
    "C79.72": "Metastases & Palliative",   # secondary left adrenal
    "C79.81": "Metastases & Palliative",   # secondary breast
    "C79.82": "Metastases & Palliative",   # secondary genital organs
    "C79.89": "Metastases & Palliative",   # secondary other specified
    "C79.9":  "Metastases & Palliative",   # secondary NOS
    "C80.1":  "Metastases & Palliative",   # malignant neoplasm NOS
    "Z51.5":  "Metastases & Palliative",   # encounter for palliative care
    "Z51.0":  "Metastases & Palliative",   # encounter for antineoplastic RT
    "G95.20": "Metastases & Palliative",   # cord compression NOS
    "G95.29": "Metastases & Palliative",   # other cord compression
    "G89.3":  "Metastases & Palliative",   # neoplasm-related pain
    "336.9":  "Metastases & Palliative",   # ICD-9 spinal cord disease

    # ── Central Nervous System ───────────────────────────────────
    "Q28.2":  "Central Nervous System",    # cerebral AVM
    "747.81": "Central Nervous System",    # ICD-9 cerebrovascular AVM

    # ── Hematologic ──────────────────────────────────────────────
    "D75.81": "Hematologic",               # myelofibrosis
    "289.83": "Hematologic",               # ICD-9 myelofibrosis
    "R16.1":  "Hematologic",               # splenomegaly (low-dose RT)
    "789.2":  "Hematologic",               # ICD-9 splenomegaly

    # ── Benign Diseases ──────────────────────────────────────────
    # Hemangioma
    "D18.00": "Benign Diseases",
    "D18.02": "Benign Diseases",
    "D18.09": "Benign Diseases",
    # Keloid / hypertrophic scar
    "L91.0":  "Benign Diseases",
    # Dupuytren / plantar fibromatosis
    "M72.0":  "Benign Diseases",
    "M72.2":  "Benign Diseases",
    # Heterotopic ossification
    "M61.40": "Benign Diseases",
    "M61.451": "Benign Diseases",
    "M61.452": "Benign Diseases",
    "M61.49": "Benign Diseases",
    # Calcific tendinitis
    "M65.221": "Benign Diseases",
    # Gynecomastia
    "N62":    "Benign Diseases",
    # Neurofibromatosis
    "Q85.00": "Benign Diseases",
    # Benign mammary dysplasia
    "N60.92": "Benign Diseases",
    "N60.99": "Benign Diseases",
    # Benign breast neoplasm
    "D24.1":  "Benign Diseases",
    # Osteoarthritis (low-dose RT)
    "M16.10": "Benign Diseases",
    "M17.0":  "Benign Diseases",
    "M17.11": "Benign Diseases",
    "M18.0":  "Benign Diseases",
    "M19.011": "Benign Diseases",
    "M19.012": "Benign Diseases",
    "M19.031": "Benign Diseases",
    "M19.041": "Benign Diseases",
    "M19.042": "Benign Diseases",
    "M19.90": "Benign Diseases",
    # Rheumatoid arthritis (low-dose RT)
    "M06.9":  "Benign Diseases",
    # Orbital granuloma
    "376.11": "Benign Diseases",
    # ICD-9 benign equivalents
    "611.1":  "Benign Diseases",           # hypertrophy of breast (= N62)
    "728.6":  "Benign Diseases",           # contracture of palmar fascia (Dupuytren)
    "728.13": "Benign Diseases",           # postop heterotopic ossification
    "701.4":  "Benign Diseases",           # keloid scar
    "726.12": "Benign Diseases",           # calcific tendinitis bicipital
    "728.89": "Benign Diseases",           # other muscle/fascia disorders
}

# ---------------------------------------------------------------------------
# Step 3: Prefix rules (longest match wins)
# ---------------------------------------------------------------------------
_ICD_PREFIX_CATEGORY: dict[str, str] = {
    # ICD-10 secondary neoplasms
    "C77": "Metastases & Palliative",     # secondary lymph nodes
    "C78": "Metastases & Palliative",     # secondary respiratory/digestive
    "C7B": "Metastases & Palliative",     # secondary neuroendocrine

    # ICD-9 secondary neoplasms (196–199 are ALL metastatic/disseminated)
    "196": "Metastases & Palliative",     # secondary malignant neo of lymph nodes
    "197": "Metastases & Palliative",     # secondary malignant neo of respiratory/digestive
    "198": "Metastases & Palliative",     # secondary malignant neo of other specified sites
    "199": "Metastases & Palliative",     # disseminated/unspecified malignant neoplasm

    # ICD-9 nasal cavities/sinuses — ARIA SiteDesc="Head & Neck (Misc)" routes to Skin
    "160": "Head and Neck",
}

# ---------------------------------------------------------------------------
# Step 4: SiteDesc → category
# ---------------------------------------------------------------------------
_SITE_TO_CATEGORY: dict[str, str] = {
    # Central Nervous System
    "Brain":                  "Central Nervous System",
    "Nervous System (Misc)":  "Central Nervous System",
    "Orbit":                  "Central Nervous System",
    "Uvea":                   "Central Nervous System",
    "Glands (Misc)":          "Central Nervous System",

    # Head and Neck
    "Lip and Oral Cavity":                          "Head and Neck",
    "Oropharynx (p16-)":                            "Head and Neck",
    "Nasopharynx":                                  "Head and Neck",
    "Hypopharynx":                                  "Head and Neck",
    "Larynx":                                       "Head and Neck",
    "Larynx: Supraglottis":                         "Head and Neck",
    "Salivary Glands":                              "Head and Neck",
    "Thyroid Gland":                                "Head and Neck",
    "Nasal Cavity and Sinuses":                     "Head and Neck",
    "Pharynx":                                      "Head and Neck",
    "Cervical Lymph Nod&Unk Primary Tumor H&N":     "Head and Neck",

    # Skin (includes H&N skin codes via Head & Neck (Misc) SiteDesc)
    "Melanoma":               "Skin",
    "Merkel Cell":            "Skin",
    "Skin":                   "Skin",
    "Head & Neck (Misc)":     "Skin",
    "Eyelid":                 "Skin",
    "Conjunctiva":            "Skin",

    # Breast
    "Breast":                 "Breast",

    # Thoracic
    "Lung":                   "Thoracic",
    "Pleural Mesothelioma":   "Thoracic",
    "Thymus":                 "Thoracic",
    "Heart":                  "Thoracic",
    "Thoracic (Misc)":        "Thoracic",
    "Respiratory (Misc)":     "Thoracic",

    # Gastrointestinal
    "Esophagus":              "Gastrointestinal",
    "Stomach":                "Gastrointestinal",
    "Small Intestine":        "Gastrointestinal",
    "Colon":                  "Gastrointestinal",
    "Rectal":                 "Gastrointestinal",
    "Anal Canal":             "Gastrointestinal",
    "Pancreas":               "Gastrointestinal",
    "Gallbladder":            "Gastrointestinal",
    "Liver and Biliary Passages": "Gastrointestinal",
    "Intrahepatic Bile Ducts": "Gastrointestinal",
    "Extrahepatic Bile Ducts": "Gastrointestinal",
    "Perihilar Bile Ducts":   "Gastrointestinal",
    "Ampulla of Vater":       "Gastrointestinal",
    "Digestive (Misc)":       "Gastrointestinal",

    # GU – Prostate (C61 handled by override)
    "Prostate":               "GU – Prostate",

    # GU – Non-Prostate
    "Bladder":                "GU – Non-Prostate",
    "Kidney":                 "GU – Non-Prostate",
    "Renal Pelvis and Ureter": "GU – Non-Prostate",
    "Testicular":             "GU – Non-Prostate",
    "Penis":                  "GU – Non-Prostate",
    "Urethra":                "GU – Non-Prostate",
    "Adrenal Gland":          "GU – Non-Prostate",
    "Genitourinary (Misc)":   "GU – Non-Prostate",
    "Male Organs (Misc)":     "GU – Non-Prostate",

    # Gynecologic
    "Cervical":               "Gynecologic",
    "Corpus Uteri Carcinoma&Carcinosarcoma":     "Gynecologic",
    "Corpus Uteri Leiomyosarcoma&Endometrial":   "Gynecologic",
    "Ovarian":                "Gynecologic",
    "Vulva":                  "Gynecologic",
    "Vagina":                 "Gynecologic",
    "Fallopian Tubes":        "Gynecologic",
    "Uterine":                "Gynecologic",
    "Female Organs (Misc)":   "Gynecologic",

    # Hematologic
    "Hematology":             "Hematologic",
    "Leukemia":               "Hematologic",
    "Myelomas":               "Hematologic",
    "Hodgkin's Disease":      "Hematologic",
    "Non-Hodgkin's Lymphoma": "Hematologic",
    "Lymph Nodes":            "Hematologic",
    "Sezary Syndrome":        "Hematologic",
    "Kaposi's Sarcoma":       "Hematologic",

    # Sarcomas
    "Soft Tissue":                            "Sarcomas",
    "Soft Tissue Sarcoma of Trunk&Extremity": "Sarcomas",
    "Soft Tissue Sarcoma of Head&Neck":       "Sarcomas",
    "Soft Tissue Sarcoma of Abdomen&Thoracic": "Sarcomas",
    "Soft Tissue Sarcoma of Retroperitoneum": "Sarcomas",
    "Bone":                                   "Sarcomas",
    "Limbs":                                  "Sarcomas",

    # Catch-all (dominated by C79.51 bone mets)
    "Other Sites":            "Metastases & Palliative",
}

# ---------------------------------------------------------------------------
# Step 5: BodySystemDesc fallback
# ---------------------------------------------------------------------------
_BODY_SYSTEM_FALLBACK: dict[str, str] = {
    "Breast":                 "Breast",
    "Central Nervous System": "Central Nervous System",
    "Digestive System":       "Gastrointestinal",
    "Endocrine":              "Central Nervous System",
    "Genitourinary":          "GU – Non-Prostate",
    "Gynecological":          "Gynecologic",
    "Head & Neck":            "Head and Neck",
    "Hematology":             "Hematologic",
    "Lymphomas":              "Hematologic",
    "Musculoskeletal":        "Sarcomas",
    "Opthalmic":              "Central Nervous System",
    "Skin":                   "Skin",
    "Thoracic":               "Thoracic",
    "Misc.":                  "Metastases & Palliative",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _resolve_code(code: str, site: str, body: str) -> str:
    """Resolve a single diagnosis code to a category name."""
    if code in _ICD_OVERRIDES:
        return _ICD_OVERRIDES[code]
    if code in _ICD_CODE_CATEGORY:
        return _ICD_CODE_CATEGORY[code]
    for length in range(len(code), 0, -1):
        prefix = code[:length]
        if prefix in _ICD_PREFIX_CATEGORY:
            return _ICD_PREFIX_CATEGORY[prefix]
    if site and site in _SITE_TO_CATEGORY:
        return _SITE_TO_CATEGORY[site]
    if body and body in _BODY_SYSTEM_FALLBACK:
        return _BODY_SYSTEM_FALLBACK[body]
    return "Uncategorized"


def seed_diagnosis_db(diag_lookup: pd.DataFrame | None = None) -> int:
    """Populate the diagnosis_overrides DB table from all legacy sources.

    Merges (in order, each layer overriding the last):
    1. ARIA lookup table (SiteDesc / BodySystemDesc resolution)
    2. Hardcoded ``_ICD_CODE_CATEGORY`` / ``_ICD_OVERRIDES``
    3. Curated subcategory CSV (``diagnosis_subcategories.csv``)

    Only inserts codes that are NOT already in the DB (preserves user edits).
    Returns the number of new rows inserted.
    """
    from data.reviews_db import get_all_diagnosis_overrides, bulk_upsert_diagnosis_overrides

    existing = get_all_diagnosis_overrides()
    # Build the full legacy mapping
    legacy: dict[str, tuple[str, str]] = {}  # code → (category, subcategory)

    # Layer 1: ARIA lookup table
    if diag_lookup is not None and not diag_lookup.empty and "DiagnosisCode" in diag_lookup.columns:
        has_site = "SiteDesc" in diag_lookup.columns
        has_body = "BodySystemDesc" in diag_lookup.columns
        for _, row in diag_lookup.iterrows():
            code = str(row["DiagnosisCode"]).strip()
            site = str(row["SiteDesc"]).strip() if has_site else ""
            body = str(row["BodySystemDesc"]).strip() if has_body else ""
            if site == "nan":
                site = ""
            if body == "nan":
                body = ""
            cat = _resolve_code(code, site, body)
            if cat != "Uncategorized":
                legacy[code] = (cat, "")

    # Layer 2: hardcoded dicts
    for code, cat in _ICD_CODE_CATEGORY.items():
        legacy[code] = (cat, legacy.get(code, ("", ""))[1])
    for code, cat in _ICD_OVERRIDES.items():
        legacy[code] = (cat, legacy.get(code, ("", ""))[1])

    # Layer 3: curated CSV (has both category and subcategory)
    for code, (cat, sub) in _SUBCATEGORY_MAP.items():
        if cat:
            legacy[code] = (cat, sub)

    # Insert only codes not already in the DB
    new_records = []
    for code, (cat, sub) in legacy.items():
        if code not in existing:
            new_records.append({
                "icd_code": code,
                "category": cat,
                "subcategory": sub,
                "source": "seed",
            })

    if new_records:
        bulk_upsert_diagnosis_overrides(new_records)

    return len(new_records)


# Process-level caches for code→category / code→subcategory dicts.
# Populated lazily; invalidated via invalidate_code_map_cache() after
# Classification Manager edits (diagnosis_overrides table mutations).
_CODE_MAP_CACHE: dict[str, dict[str, str]] = {}


def invalidate_code_map_cache() -> None:
    """Clear cached code→category and code→subcategory dicts.

    Call after any write to the ``diagnosis_overrides`` table so the next
    ``build_code_to_category`` / ``build_code_to_subcategory`` call reflects
    the edit.
    """
    _CODE_MAP_CACHE.clear()


def build_code_to_category(diag_lookup: pd.DataFrame | None) -> dict[str, str]:
    """Build a ``{DiagnosisCode: category}`` dict.

    The ``diagnosis_overrides`` DB table is the single source of truth.
    On first run, ``seed_diagnosis_db()`` auto-populates it from legacy
    sources (ARIA lookup, hardcoded dicts, curated CSV).

    For codes not yet in the DB (e.g. newly appeared in data), falls back
    to the old resolution chain and seeds them into the DB for next time.

    Cached at module scope — callers hit the DB only on first use (or after
    ``invalidate_code_map_cache()``).
    """
    cached = _CODE_MAP_CACHE.get("c2c")
    if cached is not None:
        return cached

    from data.reviews_db import get_all_diagnosis_overrides, diagnosis_table_row_count

    # Auto-seed on first use
    if diagnosis_table_row_count() == 0:
        seed_diagnosis_db(diag_lookup)

    # DB is ground truth
    overrides = get_all_diagnosis_overrides()
    result: dict[str, str] = {
        code: ov["category"]
        for code, ov in overrides.items()
        if ov["category"]
    }

    # For any ARIA lookup codes not yet in the DB, resolve via legacy chain
    # and seed them so they appear in the manager for classification
    if diag_lookup is not None and not diag_lookup.empty and "DiagnosisCode" in diag_lookup.columns:
        has_site = "SiteDesc" in diag_lookup.columns
        has_body = "BodySystemDesc" in diag_lookup.columns
        new_records = []
        for _, row in diag_lookup.iterrows():
            code = str(row["DiagnosisCode"]).strip()
            if code in result or code in _seen_new:
                continue
            _seen_new.add(code)
            site = str(row["SiteDesc"]).strip() if has_site else ""
            body = str(row["BodySystemDesc"]).strip() if has_body else ""
            if site == "nan":
                site = ""
            if body == "nan":
                body = ""
            cat = _resolve_code(code, site, body)
            if cat != "Uncategorized":
                result[code] = cat
            new_records.append({
                "icd_code": code,
                "category": cat if cat != "Uncategorized" else "",
                "subcategory": "", "source": "auto",
            })
        if new_records:
            from data.reviews_db import bulk_upsert_diagnosis_overrides
            bulk_upsert_diagnosis_overrides(new_records)

    _CODE_MAP_CACHE["c2c"] = result
    return result


def get_categories_for_codes(codes_str: str, c2c: dict[str, str]) -> set[str]:
    """Return the set of categories for a comma-separated codes string."""
    if not codes_str or not c2c:
        return set()
    cats = set()
    for code in str(codes_str).split(","):
        cat = c2c.get(code.strip(), "")
        if cat:
            cats.add(cat)
    return cats


def build_code_to_subcategory(diag_lookup: pd.DataFrame | None = None) -> dict[str, str]:
    """Build a ``{DiagnosisCode: subcategory}`` dict from the DB.

    Cached at module scope — invalidate with ``invalidate_code_map_cache()``
    after writes to ``diagnosis_overrides``.
    """
    cached = _CODE_MAP_CACHE.get("c2s")
    if cached is not None:
        return cached
    from data.reviews_db import get_all_diagnosis_overrides
    overrides = get_all_diagnosis_overrides()
    result = {
        code: ov["subcategory"]
        for code, ov in overrides.items()
        if ov.get("subcategory")
    }
    _CODE_MAP_CACHE["c2s"] = result
    return result


def get_subcategories_for_codes(codes_str: str, c2s: dict[str, str]) -> set[str]:
    """Return the set of subcategories for a comma-separated codes string."""
    if not codes_str or not c2s:
        return set()
    subs = set()
    for code in str(codes_str).split(","):
        sub = c2s.get(code.strip(), "")
        if sub:
            subs.add(sub)
    return subs


def primary_category(codes_str: str, c2c: dict[str, str]) -> str:
    """Return the first matching category for a comma-separated codes string.

    Returns ``"Unknown"`` if no code matches.
    """
    if pd.isna(codes_str) or not c2c:
        return "Unknown"
    for code in str(codes_str).split(","):
        cat = c2c.get(code.strip(), "")
        if cat:
            return cat
    return "Unknown"


def assign_diagnosis_column(
    df: pd.DataFrame,
    c2c: dict[str, str],
    mode: str = "primary",
    codes_col: str = "DiagnosisCodes",
    target_col: str = "_bs",
) -> pd.DataFrame:
    """Add a diagnosis category column and optionally explode rows.

    Parameters
    ----------
    mode : ``"primary"`` — assign only the first code's category (one row per row).
           ``"all"`` — explode so each code's category gets its own row.

    Returns a **copy** with the new *target_col*.  Rows with ``"Unknown"``
    or empty categories are dropped.
    """
    if codes_col not in df.columns or not c2c:
        return df.copy().assign(**{target_col: "Unknown"})

    out = df.copy()
    if mode == "all":
        out["_diag_cats_list"] = out[codes_col].apply(
            lambda v: list(get_categories_for_codes(v, c2c)) if pd.notna(v) else []
        )
        out = out.explode("_diag_cats_list").rename(columns={"_diag_cats_list": target_col})
    else:
        out[target_col] = out[codes_col].apply(lambda v: primary_category(v, c2c))
    out = out[out[target_col].notna() & (out[target_col] != "") & (out[target_col] != "Unknown")]
    return out


def filter_by_diagnosis(
    df: pd.DataFrame,
    selected_cats: list[str],
    c2c: dict[str, str],
    mode: str = "primary",
    codes_col: str = "DiagnosisCodes",
) -> pd.DataFrame:
    """Filter *df* to rows matching *selected_cats* using the given mode.

    Parameters
    ----------
    mode : ``"primary"`` — match only the first code's category.
           ``"all"`` — match if any code's category is in *selected_cats*.
    """
    if not selected_cats or codes_col not in df.columns or not c2c:
        return df
    cat_set = set(selected_cats)
    if mode == "primary":
        mask = df[codes_col].apply(
            lambda v: primary_category(v, c2c) in cat_set
        )
    else:
        mask = df[codes_col].apply(
            lambda v: bool(get_categories_for_codes(v, c2c) & cat_set)
        )
    return df[mask]


def get_subcategory(code: str) -> str:
    """Return the subcategory for an ICD code, or '' if unknown."""
    try:
        from data.reviews_db import get_all_diagnosis_overrides
        ov = get_all_diagnosis_overrides().get(code)
        if ov and ov["subcategory"]:
            return ov["subcategory"]
    except Exception:
        pass
    entry = _SUBCATEGORY_MAP.get(code)
    return entry[1] if entry else ""


def get_category_and_subcategory(code: str) -> tuple[str, str]:
    """Return (category, subcategory) for an ICD code from the DB."""
    try:
        from data.reviews_db import get_all_diagnosis_overrides
        ov = get_all_diagnosis_overrides().get(code)
        if ov:
            return (ov["category"], ov["subcategory"])
    except Exception:
        pass
    entry = _SUBCATEGORY_MAP.get(code)
    return entry if entry else ("", "")


def get_all_subcategory_entries() -> dict[str, tuple[str, str]]:
    """Return the full {icd_code: (category, subcategory)} map from the DB."""
    try:
        from data.reviews_db import get_all_diagnosis_overrides
        overrides = get_all_diagnosis_overrides()
        if overrides:
            return {
                code: (ov["category"], ov["subcategory"])
                for code, ov in overrides.items()
            }
    except Exception:
        pass
    return dict(_SUBCATEGORY_MAP)


# ---------------------------------------------------------------------------
# Free-text → category regex patterns
# ---------------------------------------------------------------------------
# For datasets where structured ICD codes are partially or fully missing
# (med-onc referrals export, referring-provider diagnoses, etc.), map free-
# text diagnosis strings to the same category names used for ICD-derived
# diagnoses. Order matters — first match wins, so specific patterns precede
# broad ones. Sarcomas early so "osteoblastoma" doesn't fall through to Mets
# via "bone".
#
# Originally lived in pages/referrals.py; lifted here so medonc_referrals.py
# and any future pages can share it without duplicating the pattern library.

import re as _re

DIAG_TEXT_PATTERNS: list[tuple[str, "_re.Pattern"]] = [
    ("Sarcomas",               _re.compile(
        r"sarcoma|soft.?tissue|lipomatous.?tumor|spindle.?cell"
        r"|giant.?cell.?tumor|osteoblas|fibrous.?tumor|fibromatosis", _re.I)),
    ("Metastases & Palliative", _re.compile(
        r"bone\s*met|brain\s*met|secondary.*bone|secondary.*brain|C79\.[35]"
        r"|metasta|\bmet\b|\bmets\b|spine\s*met|cord.?compress|spinal.?cord"
        r"|sternal\s*met|rib\s*met|hip\s*met|sacr\w*\s*met|pelvic\s*met"
        r"|lytic.?lesion|lystic|bone.?lesion|pathologic\w*\s*fracture"
        r"|\bbone\b|\bspine\b|lspine|\bfemur\b|femurs|\bhumerus\b|\brib\b|\bpelvi"
        r"|pevic|skull.?lesion|sternum|SVC.?syndrom|\bPCI\b"
        r"|T\d+\b|L\s*\d+\b|C\d+\s*spin|sacrum|clavicle|lumbar"
        r"|\bhip\b|shoulder|scapula|chest.?wall|chest\b|axilla"
        r"|flank|leg.?mass|thigh.?mass|arm\b|elbow|forearm|T-\d+"
        r"|calf\b|knee\b|dorsal.?hand|finger|ankle|wrist"
        r"|face.?mass|back.?pain", _re.I)),
    ("GU – Prostate",          _re.compile(r"prostat", _re.I)),
    ("Breast",                 _re.compile(
        r"breast|breat|bresst|breaast|mammary|left brest|DCIS|LCIS", _re.I)),
    ("Thoracic",               _re.compile(
        r"\blung\b|pulmon|bronch|\bSCLC\b|\bNSCL\b|mesothelioma"
        r"|mediastin|thymom|thymus|thymic|paratracheal", _re.I)),
    ("Central Nervous System", _re.compile(
        r"\bbrain\b|\bGBM\b|gliob|glioma|oligodendro|astrocyt|mening"
        r"|ependymoma|pituitary|schwannoma|acoustic.?neuroma|cerebell"
        r"|cranial|\borbit\b|orbital|choroid|chorodial|vestibul\w+\s*schwann"
        r"|frontal.?lobe.?lesion|parietal.?lobe|\bcns\b|optic.?nerve"
        r"|cauda.?equina|brachial.?plex|neuropath", _re.I)),
    ("Head and Neck",          _re.compile(
        r"tongue|tounge|tonsil|tonge|laryn|pharyn|pharny|hypo.?pharyn|hypoharyn"
        r"|oral|oropharyn|orophayn|nasopharyn|salivary|thyroid|palat"
        r"|sinus|nasal|\bBOT\b|base of tongue|parotid|vocal.?cord"
        r"|epiglott|glotti|mandib|submandib|buccal|retromolar"
        r"|adenoid.?cystic|lingual|\bH&N\b|\bSCCA\b|mouth|throat"
        r"|arytenoid|supraclav|neck.?mass|head.?neck|\bneck\b"
        r"|midface|zygoma|auditory|adenoid\b|otalgia|perianal", _re.I)),
    ("Gastrointestinal",       _re.compile(
        r"pancrea|hepato|hepatocell|esophag|esphag|esopah|esopheal"
        r"|rectal|rectum|recral|retum|rectosigmoid|colon|colorect"
        r"|gastri|gastic|bile|biliary|cholang|\banal\b|\banus\b"
        r"|stomach|small.?bowel|pyloric|\bcec\w+|splenic.?flexure"
        r"|\bGI\b|\bliver\b|peritoneum|peritoneal|stomal.?tumor"
        r"|intestin|appendix|appendic|ampullar|GE.?junction"
        r"|gastroesophag|duoden", _re.I)),
    ("Gynecologic",            _re.compile(
        r"cervi|cerivx|uter|endomet|edometr|endrometr|ovar|vulv|vagin|vlava"
        r"|fallopian|adnex|\bCIN\s*(?:I{1,3}|\d)", _re.I)),
    ("Hematologic",            _re.compile(
        r"lymph|lymhoma|hodgkin|leukemi|\bAML\b|\bCML\b|\bCLL\b|\bALL\b"
        r"|myelom|meyloma|myelona|myelofibro|\bMDS\b|myelodys"
        r"|polycythem|thrombocyth|essential.?thromb|plasmacytom|plasma.?cyt|plasma.?cell"
        r"|waldenstrom|macroglob"
        r"|mycosis.?fungoid|mycosis.?fungod|spleen|spleno|\bSPLEN\b"
        r"|pancytopen|\bMGUS\b|amyloid", _re.I)),
    ("Skin",                   _re.compile(
        r"melan|squamous.{0,10}skin|basal.?cell|basil.?cell|\bBCC\b|\bSCC\b"
        r"|\bskin\b|cutane|merkel|\bMCC\b|keloid|scalp|ear\b|forehead"
        r"|cheek|temple|lip\b|nose\b|eyelid|sebaceous.?carcinom"
        r"|\bAFX\b|hidradenitis|squamous.?cell.?carcinom", _re.I)),
    ("GU – Non-Prostate",      _re.compile(
        r"bladder|bkadder|renal|kidney|ureter|ureth|urothel"
        r"|transitional.?cell|testic|testis|penile|penis|adrenocort|adrenal"
        r"|seminoma", _re.I)),
    ("Benign Diseases",        _re.compile(
        r"benign|keloid|dupuytren|\bAVM\b|arteriovenous|hemangioma"
        r"|heterotopic.?oss|het\s*erotrophic|hypertrophic.?scar"
        r"|osteopor|osteopeni|neurofibroma|Graves|psoriasis"
        r"|\bHHT\b|Osler.?Weber|trigeminal.?neuralgia|neuralgia"
        r"|arthritis|bursitis", _re.I)),
]


def categorise_free_text(text) -> str | None:
    """Map a free-text diagnosis string to one of CATEGORIES via regex.

    Returns None if no pattern matches. Use for fields like ``Onc Dx`` or
    ``Rfl Prim Dx`` when structured ICD codes are missing or unreliable.
    """
    if pd.isna(text) or not str(text).strip():
        return None
    s = str(text)
    for name, pat in DIAG_TEXT_PATTERNS:
        if pat.search(s):
            return name
    return None


# Free-text markers of malignancy. Deliberately conservative — matches the
# unambiguous cancer terms ("malignant ...", "carcinoma", "sarcoma", etc.) and
# not bare "neoplasm"/"tumor" (which may be benign). Used to flag referrals
# whose patient-level ``Onc Dx`` indicates cancer even though the referral's own
# diagnosis code resolved to a symptom or benign entry.
_MALIGNANT_RE = _re.compile(
    r"\b(cancer|carcinom\w*|malignan\w*|sarcoma|lymphoma|leukem\w*|melanoma"
    r"|myeloma|mesothelioma|glioblastoma|gliom\w*|blastoma|seminoma|astrocytoma"
    r"|adenocarcinoma|cholangiocarcinoma|metasta\w*)\b", _re.I)


def is_malignant_text(text) -> bool:
    """True when a free-text diagnosis clearly denotes a malignancy."""
    if pd.isna(text) or not str(text).strip():
        return False
    return bool(_MALIGNANT_RE.search(str(text)))


# ---------------------------------------------------------------------------
# Referral-specific cascade
# ---------------------------------------------------------------------------
# Applies to exports (rad-onc and med-onc referrals alike) that carry the
# same "Diagnoses" / "Rfl Prim Dx" / "Onc Dx" columns. The referral-intent
# priority order is:
#   1. ICD-10/ICD-9 code extracted from "Diagnoses"  → taxonomy lookup
#   2. Free-text regex on "Rfl Prim Dx"
#   3. Free-text regex on "Diagnoses"
#   4. Free-text regex on "Onc Dx"  (patient-level, last resort)
#   5. "Other"
#
# Rationale: Diagnoses / Rfl Prim Dx are referral-specific (what the referring
# provider entered for THIS referral). Onc Dx is patient-level — useful as a
# safety net for referrals missing the referral-specific fields, but should
# not preempt the referral-specific signal.

_ICD10_CODE_RE = _re.compile(r"([A-Z]\d[0-9A-Z](?:\.[0-9A-Z]+)?)\s*\(ICD-10")
_ICD9_CODE_RE = _re.compile(r"(\d{3}(?:\.\d+)?)\s*\(ICD-9")


def _extract_icd_code(text) -> str | None:
    """Return first ICD-10 (preferred) or ICD-9 code from a Diagnoses string."""
    if pd.isna(text):
        return None
    s = str(text)
    m = _ICD10_CODE_RE.search(s)
    if m:
        return m.group(1)
    m = _ICD9_CODE_RE.search(s)
    if m:
        return m.group(1)
    return None


def categorise_referral(diagnoses=None, rfl_prim_dx=None, onc_dx=None,
                        c2c: dict[str, str] | None = None) -> str:
    """Referral-intent category for a single referral row.

    Args mirror the common referral-export column names. Pass ``c2c`` (the
    {ICD_code: category} map from ``build_code_to_category(load_diagnosis())``)
    when available so tier 1 works; omit it and the function falls through
    to free-text tiers.

    Returns one of CATEGORIES or "Other". Never returns None/Unknown so
    callers can safely group without post-filtering.
    """
    if c2c:
        code = _extract_icd_code(diagnoses)
        if code:
            cat = c2c.get(code)
            # Treat "Unknown" (taxonomy sentinel for codes present-but-unmapped)
            # as a miss so the free-text tiers get a shot.
            if cat and cat != "Unknown":
                return cat
    for field in (rfl_prim_dx, diagnoses, onc_dx):
        cat = categorise_free_text(field)
        if cat:
            return cat
    return "Other"
