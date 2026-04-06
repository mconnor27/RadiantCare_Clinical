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

import pandas as pd

# ---------------------------------------------------------------------------
# Category display names (no roman-numeral prefixes)
# ---------------------------------------------------------------------------
CATEGORIES: list[str] = [
    "Benign Diseases",
    "Breast",
    "Central Nervous System",
    "Gastrointestinal",
    "GU – Non-Prostate",
    "GU – Prostate",
    "Gynecologic",
    "Head and Neck",
    "Hematologic",
    "Metastases & Palliative",
    "Sarcomas",
    "Skin",
    "Thoracic",
]

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


def build_code_to_category(diag_lookup: pd.DataFrame | None) -> dict[str, str]:
    """Build a ``{DiagnosisCode: category}`` dict from the diagnosis lookup table.

    This replaces the old ``{DiagnosisCode: BodySystemDesc}`` mapping.
    """
    if diag_lookup is None or diag_lookup.empty:
        return {}
    required = {"DiagnosisCode"}
    if not required.issubset(diag_lookup.columns):
        return {}

    has_site = "SiteDesc" in diag_lookup.columns
    has_body = "BodySystemDesc" in diag_lookup.columns

    # Seed with overrides and exact code mappings so codes not in the CSV
    # still resolve (e.g. referral-only ICD codes absent from Lookup table).
    result: dict[str, str] = {}
    result.update(_ICD_CODE_CATEGORY)
    result.update(_ICD_OVERRIDES)

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
            result[code] = cat
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
