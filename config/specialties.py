"""Single source of truth for referring-physician specialty normalization.

All raw specialty strings (NPI Registry taxonomies, ARIA free-text, etc.)
collapse here into the canonical names listed in ``ABMS_SPECIALTIES``.

Pipeline (applied in this order in data/loader.py):
  1. ``SPECIALTY_VARIANTS`` — exact-match table of known raw → canonical pairs.
  2. ``SPECIALTY_VARIANT_REGEX`` — case-insensitive regex fallback for variants
     not in the exact table (catches future "Resident with X", new Mohs subtaxa,
     etc. without code changes).
  3. ``DEPARTMENT_NAME_PATTERNS`` — infer specialty from the "Referred by
     Department" string when ``DoctorSpecialty`` is empty.
  4. ``DEPT_BUCKETS`` — coarse roll-ups for slicing (e.g. Vascular Surgery →
     General Surgery, Resident → Unknown). Applied to both ``DoctorSpecialty``
     and ``DeptSpecialty`` to match historical behavior.

Used by:
  - data/loader.py — Referrals load (DoctorSpecialty + DeptSpecialty)
  - utils/npi_lookup.py — NPI Registry taxonomy translation
  - pages/referrals.py — RPM grid display (via normalize_specialty)
  - utils/institution_inference.py — institution rule learning
"""

import re

# ---------------------------------------------------------------------------
# Canonical list (ABMS-aligned, plus a few oncology-relevant subspecialties
# and a handful of operational buckets the dashboard needs).
# ---------------------------------------------------------------------------
ABMS_SPECIALTIES: list[str] = [
    "Allergy & Immunology",
    "Alternative Medicine",
    "Breast Surgery",
    "Cardiology",
    "Colorectal Surgery",
    "Dermatology",
    "Emergency Medicine",
    "Endocrinology",
    "Gastroenterology",
    "General Surgery",
    "Gynecologic Oncology",
    "Hepatology",
    "Hospital Medicine",
    "Infectious Disease",
    "Infusion Services",
    "Internal Medicine",
    "Medical Oncology",
    "Nephrology",
    "Neuro-Oncology",
    "Neurology",
    "Neurosurgery",
    "OB/GYN",
    "Ophthalmology",
    "Oral Surgery",
    "Orthopedic Oncology",
    "Orthopedics",
    "Otolaryngology",
    "PA/NP",
    "Palliative Care",
    "Pathology",
    "Pediatric Oncology",
    "Pediatrics",
    "Plastic Surgery",
    "PM&R",
    "Primary Care",
    "Psychiatry",
    "Pulmonary Medicine",
    "Radiation Oncology",
    "Radiology",
    "Resident",
    "Rheumatology",
    "Surgical Oncology",
    "Thoracic Surgery",
    "Unknown",
    "Urology",
    "Vascular Surgery",
]

_ABMS_SET = set(ABMS_SPECIALTIES)

# ---------------------------------------------------------------------------
# Exact-match variants (NPI taxonomies + ARIA free-text typos/variants).
# Every value here MUST be in ABMS_SPECIALTIES.
# ---------------------------------------------------------------------------
SPECIALTY_VARIANTS: dict[str, str] = {
    # --- NPI Registry taxonomies ---
    "Cardiovascular Disease":                "Cardiology",
    "Cardiovascular Disease (Internal Medicine)": "Cardiology",
    "Interventional Cardiology":             "Cardiology",
    "Clinical Cardiac Electrophysiology":    "Cardiology",
    "Colon & Rectal Surgery":                "Colorectal Surgery",
    "Family Medicine":                       "Primary Care",
    "Family Practice":                       "Primary Care",
    "General Practice":                      "Primary Care",
    "Adolescent Medicine (Family Medicine)": "Primary Care",
    "General Surgeon":                       "General Surgery",
    "Surgical Critical Care":                "General Surgery",
    "Hematology & Medical Oncology":         "Medical Oncology",
    "Hematology & Oncology":                 "Medical Oncology",
    "Hematology/Oncology":                   "Medical Oncology",
    "Hematology (Internal Medicine)":        "Medical Oncology",
    "Internal Medicine, Hematology & Oncology": "Medical Oncology",
    "Oncology/Hematology":                   "Medical Oncology",
    "Hospice & Palliative Medicine":         "Palliative Care",
    "Hospice and Palliative Medicine":       "Palliative Care",
    "Hospice and Palliative Medicine (Internal Medicine)": "Palliative Care",
    "Internal Medicine, Pulmonary Disease":  "Pulmonary Medicine",
    "Pulmonary Disease":                     "Pulmonary Medicine",
    "Pulmonary Disease (Internal Medicine)": "Pulmonary Medicine",
    "Interventional Pulmonology":            "Pulmonary Medicine",
    "Pulmonary Critical Care Medicine":      "Pulmonary Medicine",
    "Neurological Surgery":                  "Neurosurgery",
    "Obstetrics & Gynecology":               "OB/GYN",
    "Obstetrics and Gynecology":             "OB/GYN",
    "Obstetrics":                            "OB/GYN",
    "Gynecology":                            "OB/GYN",
    "Gynecological Oncology":                "Gynecologic Oncology",
    "Opthamology":                           "Ophthalmology",
    "Optometry":                             "Ophthalmology",
    "Orthopaedic Surgery":                   "Orthopedics",
    "Orthopedic Surgery":                    "Orthopedics",
    "Sports Medicine (Orthopedic Surgery)":  "Orthopedics",
    "Physical Medicine & Rehabilitation":    "PM&R",
    "Physical Medicine and Rehabilitation":  "PM&R",
    "Physiatry":                             "PM&R",
    "Thoracic & Cardiac Surgery":            "Thoracic Surgery",
    "Thoracic Surgery (Cardiothoracic Vascular Surgery)": "Thoracic Surgery",
    "Nurse Practitioner":                    "PA/NP",
    "Physician Assistant":                   "PA/NP",
    "Family Nurse Practitioner":             "PA/NP",
    "Adult Health":                          "PA/NP",
    "Geriatric Medicine (Internal Medicine)": "Internal Medicine",
    "Hospitalist":                           "Hospital Medicine",
    "Hospital Medicine":                     "Hospital Medicine",
    "Neurology with Special Qualifications in Child Neurology": "Neurology",
    "Neuromuscular Medicine":                "Neurology",
    "Gastroenterology (Internal Medicine)":  "Gastroenterology",
    "Nephrology (Internal Medicine)":        "Nephrology",
    "Endocrinology, Diabetes & Metabolism":  "Endocrinology",
    "Infectious Disease (Internal Medicine)": "Infectious Disease",
    "Psychiatry & Neurology":                "Psychiatry",
    "Pediatric Hematology-Oncology":         "Pediatric Oncology",
    "Pediatric Medicine":                    "Pediatrics",
    "Plastic and Reconstructive Surgery":    "Plastic Surgery",
    "Plastic Surgery Within the Head and Neck": "Plastic Surgery",
    "Oral and Maxillofacial Surgery":        "Oral Surgery",
    "Dentist":                               "Oral Surgery",
    "Transplant Hepatology":                 "Hepatology",
    "Diagnostic Radiology":                  "Radiology",
    "Interventional Radiology":              "Radiology",
    "Neuroradiology":                        "Radiology",
    "Anatomic Pathology":                    "Pathology",
    "Clinical Pathology":                    "Pathology",
    "Anatomic Pathology & Clinical Pathology": "Pathology",
    "Dermatopathology":                      "Dermatology",
    "Other":                                 "Unknown",

    # --- ARIA free-text typos and variants ---
    # Medical Oncology
    "Medical Onoclogy":                      "Medical Oncology",
    "Medical Oncologist":                    "Medical Oncology",
    "Hematology-Oncogology":                 "Medical Oncology",
    "Hematology/ Medical Oncology":          "Medical Oncology",
    "Hematology/Medical Oncology":           "Medical Oncology",
    "Hematology and Oncology":               "Medical Oncology",
    "Internal Medicine Hematology & Oncology": "Medical Oncology",
    "Oncology and Hematology":               "Medical Oncology",
    "Hematology":                            "Medical Oncology",
    "Oncologist":                            "Medical Oncology",
    "Medical oncology":                      "Medical Oncology",
    "Medical  Oncology":                     "Medical Oncology",
    "Med Onc":                               "Medical Oncology",
    "Medical Oncology/Hemotology":           "Medical Oncology",
    "Medical Oncology & Hematology":         "Medical Oncology",
    "Oncology Hematology":                   "Medical Oncology",
    "Hematology oncology":                   "Medical Oncology",
    "Oncology":                              "Medical Oncology",
    "Med Onc/Hematology":                    "Medical Oncology",
    "Hematalogy & Oncology":                 "Medical Oncology",
    "Ophthalomology Oncology":               "Medical Oncology",
    # Neuro-Oncology (subspecialty kept distinct from Neurology)
    "Neuro Oncology":                        "Neuro-Oncology",
    "Neuro-oncology":                        "Neuro-Oncology",
    # Urology
    "Prostate Oncology":                     "Urology",
    "Urologic Oncology":                     "Urology",
    "Urologist":                             "Urology",
    # Orthopedic Oncology (subspecialty kept distinct from Orthopedics)
    "Orthopaedic Oncology":                  "Orthopedic Oncology",
    "Orthopeadic Oncology":                  "Orthopedic Oncology",
    # Radiation Oncology
    "Radiation Onocology":                   "Radiation Oncology",
    "Resident-Radiation Onc":                "Radiation Oncology",
    "Rad Oncology":                          "Radiation Oncology",
    # Pulmonary
    "Pulmonary":                             "Pulmonary Medicine",
    "Infectious Disease & Pulmonary Disease": "Pulmonary Medicine",
    "Pulmonary Disease and Critical Care Medicine": "Pulmonary Medicine",
    "Pulmonology":                           "Pulmonary Medicine",
    "Internal Medicine/Pulmonology":         "Pulmonary Medicine",
    # Primary Care
    "family Medicine":                       "Primary Care",
    "Family medicine":                       "Primary Care",
    "Family Practie":                        "Primary Care",
    "FAMILY PRACTICE":                       "Primary Care",
    "Family Medicine w/ OB":                 "Primary Care",
    "Family Practice/Palliative Care":       "Primary Care",
    "PCP":                                   "Primary Care",
    "Sports Medicine (Family Practice)":     "Primary Care",
    "D.O":                                   "Primary Care",
    "DO":                                    "Primary Care",
    "Summit Pacific Mark Reed Healthcare Clinic": "Primary Care",
    "Military Health Care":                  "Primary Care",
    # Internal Medicine
    "Family Practice/Internal Medicine":     "Internal Medicine",
    "Endocrinology/Internal Medicine":       "Internal Medicine",
    "Internal Medicine/Nephrology":          "Nephrology",
    "Endocrinology, Diabetes, and Metabolism": "Endocrinology",
    "Internal Medicine/Pediatrics":          "Internal Medicine",
    "Geriatric Medicine":                    "Internal Medicine",
    # Surgery
    "Gerneral Surgery":                      "General Surgery",
    "Surgery":                               "General Surgery",
    "Surgeon":                               "General Surgery",
    "Surgery- Surgical Oncology":            "Surgical Oncology",
    "Surgery, Surgical Oncology":            "Surgical Oncology",
    "General and Minimally Invasive Surgery": "General Surgery",
    # ENT
    "Otolaryngology, Facial plastic reconstructive surgery": "Otolaryngology",
    "ENT/Otolaryngology":                    "Otolaryngology",
    "ENT/Aberdeen":                          "Otolaryngology",
    "ENT- Group Health":                     "Otolaryngology",
    "Otology/Neurotology":                   "Otolaryngology",
    "Head and Neck Surgery":                 "Otolaryngology",
    "ENT":                                   "Otolaryngology",
    "Otalaryngology":                        "Otolaryngology",
    "Otolaryngology/Facial Plastic Surgery": "Otolaryngology",
    # GYN
    "GYN Oncologist":                        "Gynecologic Oncology",
    "Gyn Onc":                               "Gynecologic Oncology",
    "Gynecologic Oncology, Obstetrics and Gynecology": "Gynecologic Oncology",
    "General/GYN":                           "OB/GYN",
    "GYN":                                   "OB/GYN",
    "GYN Oncology":                          "Gynecologic Oncology",
    # Colorectal
    "Colon & rectal surgery":                "Colorectal Surgery",
    "Colon Rectal Surgeon":                  "Colorectal Surgery",
    "Colorectal surgery":                    "Colorectal Surgery",
    "Colon and Rectal Surgery":              "Colorectal Surgery",
    # Dermatology
    "Derm":                                  "Dermatology",
    "Dermatopathology (Pathology)":          "Dermatology",
    "Dermatology and Skin Oncology":         "Dermatology",
    "Surgery, Dermatology - MOHS - Micrographic Surgery": "Dermatology",
    "MOHS - Micrographic Surgery":           "Dermatology",
    # Neurology
    "Nuerology":                             "Neurology",
    # Neurosurgery
    "Neurosurgery (UWMC)":                   "Neurosurgery",
    "Neurolosurgery":                        "Neurosurgery",
    # Cardiology
    "cardiology":                            "Cardiology",
    "Cardiologist":                          "Cardiology",
    # Orthopedics
    "Orthopeadic":                           "Orthopedics",
    "Orthopaedics":                          "Orthopedics",
    "Orthopeadic Surgeon":                   "Orthopedics",
    # Ophthalmology
    "Ophthalmoogy":                          "Ophthalmology",
    "Ophthalomology":                        "Ophthalmology",
    # PA / NP / Resident
    "physician Assistant":                   "PA/NP",
    "Physician assistant":                   "PA/NP",
    "Physician Assitant":                    "PA/NP",
    "PA":                                    "PA/NP",
    "PA-C":                                  "PA/NP",
    "Nurse Practioner":                      "PA/NP",
    "ARNP":                                  "PA/NP",
    "Resident with the VA":                  "Resident",
    # Misc
    "Pediatric Hematology Oncology":         "Pediatric Oncology",
    "Emergency":                             "Emergency Medicine",
    "Emergency medicine":                    "Emergency Medicine",
    "Palliative Medicine":                   "Palliative Care",
    "GASTROENTEROLOGY":                      "Gastroenterology",
    "Unspecified":                           "Unknown",
    "MD":                                    "Unknown",
    "Acute Care":                            "Hospital Medicine",
    "Critical Care Medicine":                "Hospital Medicine",
    "Spinal Cord Injury Medicine (Physical Medicine and Rehab.)": "PM&R",
    "Vascular and interventional Radiology": "Radiology",
    "Acupuncture":                           "Alternative Medicine",
    "Occupational Therapy":                  "Unknown",
    "Anesthesiology":                        "Unknown",
    "Breast Cancer Surgeon":                 "Breast Surgery",
    "Dentistry and Maxillofacial Surgery":   "Oral Surgery",
    "Dentistry (Periodontics)":              "Oral Surgery",
    "Oral Surgeon":                          "Oral Surgery",
    # Catch-all stragglers seen in production data
    "Pain Management":                       "PM&R",
    "Palliative/Pulmonary Disease":          "Palliative Care",
    "Podiatry":                              "Unknown",
}

# ---------------------------------------------------------------------------
# Regex fallback for variants not in the exact-match table.
# Patterns are anchored where appropriate to avoid over-matching.
# All replacement values MUST be in ABMS_SPECIALTIES.
# ---------------------------------------------------------------------------
SPECIALTY_VARIANT_REGEX: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)^medical\s*onc"),                                  "Medical Oncology"),
    (re.compile(r"(?i)^radiation\s*onc"),                                "Radiation Oncology"),
    (re.compile(r"(?i)^urol"),                                           "Urology"),
    (re.compile(r"(?i)^gynecol.*onc"),                                   "Gynecologic Oncology"),
    (re.compile(r"(?i)^obstetrics|^ob/?gyn"),                            "OB/GYN"),
    (re.compile(r"(?i)^neuro.*surg|^neurological\s*surg"),               "Neurosurgery"),
    (re.compile(r"(?i)^cardiothoracic"),                                 "Thoracic Surgery"),
    (re.compile(r"(?i)^vascular\s*surg"),                                "Vascular Surgery"),
    # Resident with anything → just Resident (DEPT_BUCKETS later folds → Unknown)
    (re.compile(r"(?i)^resident\b"),                                     "Resident"),
    # Dermatology subspecialty variants
    (re.compile(r"(?i)\bMOHS\b|\bdermatopathology\b|^surgery,\s*dermatology"), "Dermatology"),
]

# ---------------------------------------------------------------------------
# Department-name patterns — used when DoctorSpecialty is null.
# Source string is the "Referred by Department" value (often all-caps).
# Patterns are case-insensitive and applied in order — first match wins.
# All replacement values MUST be in ABMS_SPECIALTIES.
# ---------------------------------------------------------------------------
DEPARTMENT_NAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Oncology subspecialties (keep granular)
    (re.compile(r"(?i)MED(?:ICAL)?\s*ONC|PROVIDER ONCOLOGY|ONCOLOGY(?!.*RADIAT)"), "Medical Oncology"),
    (re.compile(r"(?i)RADIATION|RADIOSURGERY|RADIANTCARE"),                        "Radiation Oncology"),
    (re.compile(r"(?i)PRCS\s+(?:LACEY|CENTRALIA|ABERDEEN)\b"),                     "Medical Oncology"),
    (re.compile(r"(?i)GYN ONCOLOGY"),                                              "Gynecologic Oncology"),
    (re.compile(r"(?i)BREAST SURGERY"),                                            "Breast Surgery"),
    # Surgical specialties
    (re.compile(r"(?i)GEN SURG"),                                                  "General Surgery"),
    (re.compile(r"(?i)CARDIAC SURGERY"),                                           "Thoracic Surgery"),
    (re.compile(r"(?i)THORACIC"),                                                  "Thoracic Surgery"),
    (re.compile(r"(?i)COLORECTAL|COLON AND RECTAL"),                               "Colorectal Surgery"),
    (re.compile(r"(?i)NEUROSURGERY"),                                              "Neurosurgery"),
    (re.compile(r"(?i)PROVIDER SURGICAL|INTRA OP"),                                "General Surgery"),
    # Medical specialties
    (re.compile(r"(?i)UROLOGY"),                                                   "Urology"),
    (re.compile(r"(?i)PULMONARY|LUNG NODULE|PULMONOLOGY"),                         "Pulmonary Medicine"),
    (re.compile(r"(?i)NEUROLOGY|NEURO TRAUMA"),                                    "Neurology"),
    (re.compile(r"(?i)GASTROENTEROLOGY"),                                          "Gastroenterology"),
    (re.compile(r"(?i)ENDOCRINE"),                                                 "Endocrinology"),
    (re.compile(r"(?i)CARDIO(?!.*SURG)"),                                          "Cardiology"),
    (re.compile(r"(?i)ORTHOPEDICS"),                                               "Orthopedics"),
    (re.compile(r"(?i)OPHTHALMOLOGY"),                                             "Ophthalmology"),
    (re.compile(r"(?i)HEAD AND NECK"),                                             "Otolaryngology"),
    # OB/GYN
    (re.compile(r"(?i)OBGYN|WOMEN CTR"),                                           "OB/GYN"),
    # Primary Care / FM / IM
    (re.compile(r"(?i)FAM MED|FAMILY MED|FAMILY MEDICINE"),                        "Primary Care"),
    (re.compile(r"(?i)PRIMARY CARE|WELLNESS CLINIC"),                              "Primary Care"),
    (re.compile(r"(?i)PRCS\s"),                                                    "Primary Care"),
    (re.compile(r"(?i)INT MED"),                                                   "Internal Medicine"),
    (re.compile(r"(?i)65 PLUS"),                                                   "Internal Medicine"),
    # Hospital-based
    (re.compile(r"(?i)EMERGENCY"),                                                 "Emergency Medicine"),
    (re.compile(r"(?i)IMMEDIATE CARE"),                                            "Emergency Medicine"),
    (re.compile(r"(?i)PALLIATIVE"),                                                "Palliative Care"),
    (re.compile(r"(?i)PROGRESSIVE CARE|MEDICAL TELEMETRY|ICU"),                    "Hospital Medicine"),
    (re.compile(r"(?i)INFUSION"),                                                  "Infusion Services"),
    (re.compile(r"(?i)CENTRALIZED CARE"),                                          "Internal Medicine"),
    (re.compile(r"(?i)RADIOLOGY"),                                                 "Radiology"),
    (re.compile(r"(?i)PROVIDER MED SURG"),                                         "Hospital Medicine"),
    (re.compile(r"(?i)HAWKS PRAIRIE"),                                             "Primary Care"),
    (re.compile(r"(?i)PANORAMA"),                                                  "Internal Medicine"),
    (re.compile(r"(?i)PHY MED"),                                                   "PM&R"),
]

# ---------------------------------------------------------------------------
# Coarse roll-ups for slicing. After variant normalization, these collapse
# fine-grained specialties into a smaller set for chart readability.
#
# Preserves the historical behavior of the loader's _DOC_TO_DEPT map
# (e.g. Vascular/Plastic/Surgical Oncology → General Surgery, Residents and
# mid-levels → Unknown). All keys and values are ABMS canonical.
#
# Applied to BOTH DoctorSpecialty and DeptSpecialty, matching prior behavior.
# To preserve subspecialty granularity in the future, remove entries here.
# ---------------------------------------------------------------------------
DEPT_BUCKETS: dict[str, str] = {
    # Surgical subspecialties rolled into General Surgery
    "Vascular Surgery":     "General Surgery",
    "Surgical Oncology":    "General Surgery",
    "Plastic Surgery":      "General Surgery",
    # Mid-levels and trainees folded into Unknown
    "PA/NP":                "Unknown",
    "Resident":             "Unknown",
    # Neurology subspecialty rollup
    "Neuro-Oncology":       "Neurology",
    # Internal medicine subspecialty rollup
    "Nephrology":           "Internal Medicine",
    "Hepatology":           "Internal Medicine",
    # Orthopedic Oncology folded into Orthopedics
    "Orthopedic Oncology":  "Orthopedics",
    # Otolaryngology umbrella (oral surgery currently bucketed here)
    "Oral Surgery":         "Otolaryngology",
}


def normalize_specialty(raw: str) -> str:
    """Map a raw specialty string (NPI taxonomy or ARIA free text) to the
    ABMS canonical name. Returns the raw string unchanged if no mapping
    applies. Empty / None input returns "".

    NOTE: this does NOT apply DEPT_BUCKETS. That coarsening is applied
    separately at load time so DoctorSpecialty and DeptSpecialty share
    behavior with the historical implementation.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if raw in _ABMS_SET:
        return raw
    if raw in SPECIALTY_VARIANTS:
        return SPECIALTY_VARIANTS[raw]
    # Case-insensitive exact-match fallback
    raw_lower = raw.lower()
    for canonical in ABMS_SPECIALTIES:
        if canonical.lower() == raw_lower:
            return canonical
    for variant, canonical in SPECIALTY_VARIANTS.items():
        if variant.lower() == raw_lower:
            return canonical
    # Regex fallback
    for pattern, canonical in SPECIALTY_VARIANT_REGEX:
        if pattern.match(raw):
            return canonical
    return raw


def infer_from_department(dept_name: str) -> str | None:
    """Infer the canonical specialty from a department-name string.

    Returns None when no pattern matches.
    """
    if not dept_name:
        return None
    for pattern, canonical in DEPARTMENT_NAME_PATTERNS:
        if pattern.search(dept_name):
            return canonical
    return None


def bucket_to_dept(spec: str) -> str:
    """Apply DEPT_BUCKETS roll-ups for chart/filter slicing."""
    if not spec:
        return spec
    return DEPT_BUCKETS.get(spec, spec)


# Legacy alias preserved for back-compat with config.settings imports.
# Existing call sites: utils/institution_inference.py, pages/referrals.py,
# pages/mappings_mobile.py.
NPI_SPECIALTY_MAP = SPECIALTY_VARIANTS
